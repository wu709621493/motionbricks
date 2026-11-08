"""Orthographic CPU rasterizer using CpuBlockRuntime for every scene vertex.

NumPy + standard library only. The image depicts verified logical RAM shards,
not physical DIMMs, a motherboard photograph, or measured GPU performance.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import struct
import time
import zlib

import numpy as np

from motionbricks.memory_lab import integer


# A tiny original 5x7 bitmap alphabet keeps rendering independent of system fonts.
_FONT_ROWS = {
    'A':'01110 10001 10001 11111 10001 10001 10001',
    'B':'11110 10001 10001 11110 10001 10001 11110',
    'C':'01111 10000 10000 10000 10000 10000 01111',
    'D':'11110 10001 10001 10001 10001 10001 11110',
    'E':'11111 10000 10000 11110 10000 10000 11111',
    'F':'11111 10000 10000 11110 10000 10000 10000',
    'G':'01111 10000 10000 10111 10001 10001 01111',
    'H':'10001 10001 10001 11111 10001 10001 10001',
    'I':'11111 00100 00100 00100 00100 00100 11111',
    'J':'00111 00010 00010 00010 10010 10010 01100',
    'K':'10001 10010 10100 11000 10100 10010 10001',
    'L':'10000 10000 10000 10000 10000 10000 11111',
    'M':'10001 11011 10101 10101 10001 10001 10001',
    'N':'10001 11001 11001 10101 10011 10011 10001',
    'O':'01110 10001 10001 10001 10001 10001 01110',
    'P':'11110 10001 10001 11110 10000 10000 10000',
    'Q':'01110 10001 10001 10001 10101 10010 01101',
    'R':'11110 10001 10001 11110 10100 10010 10001',
    'S':'01111 10000 10000 01110 00001 00001 11110',
    'T':'11111 00100 00100 00100 00100 00100 00100',
    'U':'10001 10001 10001 10001 10001 10001 01110',
    'V':'10001 10001 10001 10001 10001 01010 00100',
    'W':'10001 10001 10001 10101 10101 10101 01010',
    'X':'10001 10001 01010 00100 01010 10001 10001',
    'Y':'10001 10001 01010 00100 00100 00100 00100',
    'Z':'11111 00001 00010 00100 01000 10000 11111',
    '0':'01110 10001 10011 10101 11001 10001 01110',
    '1':'00100 01100 00100 00100 00100 00100 01110',
    '2':'01110 10001 00001 00010 00100 01000 11111',
    '3':'11110 00001 00001 01110 00001 00001 11110',
    '4':'00010 00110 01010 10010 11111 00010 00010',
    '5':'11111 10000 10000 11110 00001 00001 11110',
    '6':'01110 10000 10000 11110 10001 10001 01110',
    '7':'11111 00001 00010 00100 01000 01000 01000',
    '8':'01110 10001 10001 01110 10001 10001 01110',
    '9':'01110 10001 10001 01111 00001 00001 01110',
    '-':'00000 00000 00000 11111 00000 00000 00000',
    '/':'00001 00001 00010 00100 01000 10000 10000',
    '.':'00000 00000 00000 00000 00000 00110 00110',
    ':':'00000 00110 00110 00000 00110 00110 00000',
}


def text(image, x, y, value, color, scale=2):
    for char in value.upper():
        for row, bits in enumerate(_FONT_ROWS.get(char, '').split()):
            for col, bit in enumerate(bits):
                if bit == '1':
                    xx, yy = x + col * scale, y + row * scale
                    image[max(0, yy):max(0, yy + scale),
                          max(0, xx):max(0, xx + scale)] = color
        x += 6 * scale


def png_bytes(image):
    """Lossless RGB PNG; each row uses the standard no-filter encoding."""
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError('uint8 RGB image required')
    height, width, _ = image.shape
    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))
    scanlines = b''.join(b'\0' + row.tobytes() for row in image)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(scanlines, 6)) + chunk(b'IEND', b''))


def transform(runtime, vertices, matrix):
    """4 vertices/launch through the same tiled CPU pseudo-GPU kernel."""
    result = np.empty_like(vertices)
    for start in range(0, len(vertices), 4):
        batch = vertices[start:start + 4]
        padded = np.zeros((4, 4), dtype=np.float64)
        padded[:len(batch)] = batch
        out = np.empty_like(padded)
        runtime.launch(padded, matrix, out)
        # Independent scalar oracle checks each transformed coordinate.
        expected = np.array([[math.fsum(float(batch[i, k]) * float(matrix[k, j])
                                       for k in range(4)) for j in range(4)]
                             for i in range(len(batch))])
        if not np.allclose(out[:len(batch)], expected, rtol=1e-12, atol=1e-12):
            raise RuntimeError('vertex transform verification failed')
        result[start:start + len(batch)] = out[:len(batch)]
    return result


class Rasterizer:
    """Pixel-centre barycentric rasterization, 16x16 tiles and a float64 Z buffer.

    Smaller depth wins. Equal-depth ties use stable primitive IDs, making draw
    order deterministic even on shared edges. Orthographic projection only.
    """
    def __init__(self, width, height):
        integer(width, 'width', 1, 1920)
        integer(height, 'height', 1, 1440)
        self.image = np.empty((height, width, 3), dtype=np.uint8)
        self.image[:] = (11, 19, 31)
        self.depth = np.full((height, width), np.inf, dtype=np.float64)
        self.owner = np.full((height, width), np.iinfo(np.int32).max, dtype=np.int32)
        self.objects = np.full((height, width), -1, dtype=np.int32)
        self.triangles = self.fragments = self.tiles = 0

    def triangle(self, vertices, color, primitive_id, object_id):
        p = np.asarray(vertices, dtype=np.float64)
        if p.shape != (3, 3) or not np.isfinite(p).all():
            raise ValueError('three finite XYZ vertices required')
        self.triangles += 1
        a, b, c = p
        denominator = ((b[1] - c[1]) * (a[0] - c[0])
                       + (c[0] - b[0]) * (a[1] - c[1]))
        if abs(denominator) < 1e-12:
            return
        height, width = self.depth.shape
        lo = np.maximum(np.floor(p[:, :2].min(axis=0)), 0).astype(int)
        hi = np.minimum(np.ceil(p[:, :2].max(axis=0)), [width, height]).astype(int)
        for y in range(lo[1], hi[1], 16):
            for x in range(lo[0], hi[0], 16):
                endx, endy = min(x + 16, hi[0]), min(y + 16, hi[1])
                xx, yy = np.meshgrid(np.arange(x, endx) + .5, np.arange(y, endy) + .5)
                w0 = ((b[1] - c[1]) * (xx - c[0]) + (c[0] - b[0]) * (yy - c[1])) / denominator
                w1 = ((c[1] - a[1]) * (xx - c[0]) + (a[0] - c[0]) * (yy - c[1])) / denominator
                w2 = 1 - w0 - w1
                inside = (w0 >= -1e-12) & (w1 >= -1e-12) & (w2 >= -1e-12)
                z = w0 * a[2] + w1 * b[2] + w2 * c[2]
                depth, owner = self.depth[y:endy, x:endx], self.owner[y:endy, x:endx]
                visible = inside & ((z < depth) | ((z == depth) & (primitive_id < owner)))
                depth[visible], owner[visible] = z[visible], primitive_id
                self.objects[y:endy, x:endx][visible] = object_id
                self.image[y:endy, x:endx][visible] = color
                self.fragments += int(np.count_nonzero(visible))
                self.tiles += 1


FACES = ((0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5),
         (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7))
SHADE = (.30, .48, .65, .75, .50, 1.0)


def render_shards(config, runtime, pool, bounds, states):
    """Render only after the matrices have passed; heights encode mean |C|."""
    begin = time.perf_counter()
    if len(bounds) != config.logical_shards or any(s != 'VERIFIED' for s in states):
        raise ValueError('all scene shards must have verified matrix outputs')
    width, height = config.render_width, config.render_height
    raster = Rasterizer(width, height)
    columns = math.ceil(math.sqrt(len(bounds) * 1.6))
    rows = math.ceil(len(bounds) / columns)
    # Row-vector orthographic camera. Translation/scaling applied after projection.
    matrix = np.array([[.866, .35, -.5, 0], [-.866, .35, -.5, 0],
                       [0, -.94, -.707, 0], [0, 0, 0, 1]], dtype=np.float64)
    scene_top = 190.0 if height >= 600 else 160.0
    scale = min((width - 80) / (.866 * (columns + rows)),
                (height - 140 - scene_top) / (.35 * (columns + rows) + 1.5))
    offset = np.array([(width - .866 * (columns - rows) * scale) / 2, scene_top, 0, 0])
    launches_before = runtime.launches
    n, cells = config.matrix_size, config.matrix_size**2
    submitted_vertices = 0
    for index, (lo, hi) in enumerate(bounds):
        c = pool[lo + 2 * cells:lo + 3 * cells].view(np.float64).reshape(n, n)
        signal = min(1.0, float(np.abs(c).mean()) / max(1, n))
        z = .22 + .45 * signal
        x, y = index % columns, index // columns
        vertices = np.array([[x, y, 0, 1], [x + .82, y, 0, 1],
                             [x + .82, y + .82, 0, 1], [x, y + .82, 0, 1],
                             [x, y, z, 1], [x + .82, y, z, 1],
                             [x + .82, y + .82, z, 1], [x, y + .82, z, 1]], dtype=np.float64)
        projected = transform(runtime, vertices, matrix)
        projected[:, :2] *= scale
        projected += offset
        submitted_vertices += len(vertices)
        # Teal indicates verified state. Cyan variation reflects |C|, not temperature.
        base = np.array([45 + 50 * signal, 190 + 40 * signal, 170 + 65 * signal])
        for face_index, face in enumerate(FACES):
            color = np.round(base * SHADE[face_index]).astype(np.uint8)
            for half, tri in enumerate(((face[0], face[1], face[2]), (face[0], face[2], face[3]))):
                raster.triangle(projected[list(tri), :3], color,
                                index * 12 + face_index * 2 + half, index)
    visible = len(np.unique(raster.objects[raster.objects >= 0]))
    covered = int(np.count_nonzero(np.isfinite(raster.depth)))
    if covered == 0 or visible == 0:
        raise RuntimeError('render produced no visible geometry')
    scene_hash = hashlib.sha256(memoryview(raster.image)).hexdigest()
    # Labels are CPU bitmap overlays; all 3D geometry above passes through the kernel.
    image = raster.image
    image[34:38, 40:95] = (58, 221, 196)
    text(image, 110, 33, 'MOTIONBRICKS / CPU RENDER LAB', (117, 151, 177), 2)
    title_scale = 4 if width >= 1100 else (3 if width >= 800 else 1)
    text(image, 40, 70, f'{len(bounds)} LOGICAL MEMORY SHARDS', (232, 242, 249), title_scale)
    text(image, 40, 120, 'SOFTWARE SCENE / NO PHYSICAL DIMM OR GPU CLAIM', (122, 158, 180),
         2 if width >= 800 else 1)
    footer = height - 100
    image[footer - 20:footer - 19, 40:width - 40] = (37, 59, 75)
    if width >= 800:
        for x, label, value in ((40, 'VERIFIED SHARDS', str(len(bounds))),
                                (width // 3, 'TRIANGLES', str(raster.triangles)),
                                (2 * width // 3, 'BACKEND', 'CPU FLOAT64')):
            text(image, x, footer, label, (116, 154, 177), 2)
            text(image, x, footer + 25, value, (64, 222, 199), 3)
    else:
        text(image, 20, footer, f'CPU / {len(bounds)} VERIFIED SHARDS', (64, 222, 199), 1)
    encoded = png_bytes(image)
    target = Path(config.render_path)
    # Exclusive creation prevents silently replacing an earlier experiment artifact.
    with target.open('xb') as handle:
        handle.write(encoded)
    return {'status': 'RENDERED', 'path': str(target), 'width': width, 'height': height,
            'scene_objects': len(bounds), 'visible_objects': visible,
            'vertices_transformed_and_checked': submitted_vertices,
            'vertex_kernel_launches': runtime.launches - launches_before,
            'triangles_submitted': raster.triangles, 'raster_tiles_visited': raster.tiles,
            'depth_test_passes': raster.fragments, 'covered_pixels': covered,
            'projection': 'orthographic', 'rasterizer': 'CPU barycentric Z-buffer',
            'height_and_color': 'verified matrix C mean absolute value; not temperature',
            'image_sha256': hashlib.sha256(encoded).hexdigest(),
            'scene_rgb_sha256_before_labels': scene_hash,
            'render_s': time.perf_counter() - begin, 'gpu_used': False}
