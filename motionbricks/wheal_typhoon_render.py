"""Reproducible scientific schematic using the PR #50 software rasterizer."""
import hashlib
import math

import numpy as np

from motionbricks.memory_lab_render import Rasterizer, png_bytes, text, transform

WHITE = (232, 241, 248)
MUTED = (145, 169, 187)
PINK = (248, 146, 156)
CYAN = (80, 218, 211)


def line(image, a, b, color, width=1):
    points = np.linspace(a, b, max(2, math.ceil(np.linalg.norm(np.array(b) - a)) + 1))
    for xx, yy in np.rint(points).astype(int):
        if 0 <= xx < image.shape[1] and 0 <= yy < image.shape[0]:
            image[max(0, yy-width):yy+width+1, max(0, xx-width):xx+width+1] = color


def color(value, maximum, stops):
    t = np.clip(np.asarray(value) / maximum, 0, 1)
    return np.stack([np.interp(t, np.linspace(0, 1, len(stops)), np.array(stops)[:, k])
                     for k in range(3)], axis=-1).astype(np.uint8)


SKIN_COLORS = [(75, 65, 91), (190, 93, 124), (247, 171, 161), (255, 230, 197)]
WIND_COLORS = [(20, 44, 75), (31, 122, 149), (74, 212, 200), (249, 209, 113)]


def mesh(raster, runtime, vertices, values, matrix, offset, scale, palette, maximum, object_id):
    n = values.shape[0]
    screen = transform(runtime, vertices, matrix)
    screen[:, :2] = screen[:, :2] * scale + offset
    colors = color(values.ravel(), maximum, palette)
    for j in range(n - 1):
        for i in range(n - 1):
            a = j * n + i
            for tri in ((a, a+1, a+n), (a+1, a+n+1, a+n)):
                raster.triangle(screen[list(tri), :3], np.mean(colors[list(tri)], axis=0).astype(np.uint8),
                                raster.triangles, object_id)


def chart(image, x, y, width, height, xs, ys, xmax, ymax, tint, xlabel, ylabel):
    text(image, x, y - 30, ylabel, MUTED, 2)
    for f in (0, .5, 1):
        yy = y + height * (1-f)
        line(image, (x, yy), (x+width, yy), (38, 57, 76))
        text(image, x - 50, int(yy)-6, f'{f*ymax:.1f}', MUTED, 1)
    coords = np.column_stack((x + width*np.asarray(xs)/xmax, y + height*(1-np.asarray(ys)/ymax)))
    for a, b in zip(coords, coords[1:]):
        line(image, a, b, tint)
    for f in (0, .5, 1):
        text(image, int(x+f*width)-8, y+height+12, f'{f*xmax:.0f}', MUTED, 1)
    text(image, x + 140, y+height+33, xlabel, MUTED, 2)


def render(path, skin, storm, runtime):
    raster = Rasterizer(1600, 1200)
    im = raster.image
    text(im, 50, 35, 'MOTIONBRICKS / PR 50 CPU FIELD LAB', MUTED, 2)
    text(im, 50, 82, 'ONE WORD. TWO PHYSICAL SYSTEMS.', WHITE, 4)
    line(im, (800, 170), (800, 1060), (43, 63, 82))
    text(im, 50, 170, '01 / WHEAL', PINK, 3)
    text(im, 850, 170, '02 / TYPHOON-SCALE VORTEX', CYAN, 3)
    text(im, 50, 215, 'LOCAL FLUID INPUT / SPREAD / DRAINAGE', MUTED, 2)
    text(im, 850, 215, 'ROTATION / PRESSURE GRADIENT / AIR LOAD', MUTED, 2)

    x, y = np.meshgrid(skin['axis_mm']/20, skin['axis_mm']/20)
    height = skin['height_mm']
    vertices = np.column_stack((x.ravel(), y.ravel(), height.ravel(), np.ones(height.size)))
    camera = np.array([[.866, .32, -.4, 0], [-.5, .55, -.5, 0],
                       [0, -1, -.7, 0], [0, 0, 0, 1]], dtype=float)
    mesh(raster, runtime, vertices, height, camera, [405, 490], 235,
         SKIN_COLORS, .6, 0)
    x, y = np.meshgrid(storm['axis_m']/150000, storm['axis_m']/150000)
    speed = storm['speed_m_s']
    vertices = np.column_stack((x.ravel(), y.ravel(), np.zeros(speed.size), np.ones(speed.size)))
    mesh(raster, runtime, vertices, speed, np.diag([1., -1., 1., 1.]), [1200, 490], 215,
         WIND_COLORS, 45, 1)
    # Vector arrows are diagram overlays; physical fields/mesh vertices are separate.
    n = len(storm['axis_m'])
    for j in range(3, n, max(4, n//9)):
        for i in range(3, n, max(4, n//9)):
            start = np.array([1200+215*x[j, i], 490-215*y[j, i]])
            delta = np.array([storm['u_m_s'][j, i], -storm['v_m_s'][j, i]]) * .55
            end = start + delta
            line(im, start, end, WHITE)
            if np.linalg.norm(delta) > 0:
                unit = delta / np.linalg.norm(delta)
                for sign in (-1, 1):
                    tip = end - 5*unit + sign*3*np.array([-unit[1], unit[0]])
                    line(im, end, tip, WHITE)
    text(im, 65, 705, '40 MM PATCH / VERTICAL SCALE 20X', MUTED, 2)
    text(im, 920, 720, 'X AND Y: -150 TO 150 KM', MUTED, 2)
    text(im, 920, 745, 'ARROWS: DIRECTION AND SPEED', MUTED, 2)
    for left, palette, maximum, label in ((65, SKIN_COLORS, .6, 'EQUIVALENT FLUID THICKNESS / MM'),
                                           (850, WIND_COLORS, 45, 'TANGENTIAL WIND SPEED / M/S')):
        im[790:806, left:left+600] = color(np.linspace(0, maximum, 600), maximum, palette)
        text(im, left, 817, '0', MUTED, 1)
        text(im, left+555, 817, f'{maximum:.1f}', MUTED, 1)
        text(im, left, 845, label, MUTED, 2)
    history = skin['history']
    chart(im, 105, 925, 565, 110, history[:, 0]/60, history[:, 1], 30, .6, PINK,
          'TIME / MIN', 'PEAK THICKNESS / MM')
    from motionbricks.wheal_typhoon import vortex_profile
    radius = np.linspace(0, 150000, 151)
    velocity, _ = vortex_profile(radius)
    chart(im, 900, 925, 565, 110, radius/1000, velocity, 150, 45, CYAN,
          'RADIUS / KM', 'WIND SPEED / M/S')
    line(im, (50, 1110), (1550, 1110), (43, 63, 82))
    text(im, 50, 1132, 'SYNTHETIC MODELS / NO CLINICAL OR FORECAST VALIDATION / NO GPU', MUTED, 2)
    encoded = png_bytes(im)
    visible = len(np.unique(raster.objects[raster.objects >= 0]))
    if visible != 2:
        raise RuntimeError('both physical field meshes must be visible')
    with path.open('xb') as f:
        f.write(encoded)
    return {'path': path.name, 'width': 1600, 'height': 1200,
            'triangles': raster.triangles, 'vertices_transformed_and_checked': 2*height.size,
            'visible_field_meshes': visible,
            'image_sha256': hashlib.sha256(encoded).hexdigest(),
            'skin_vertical_exaggeration': 20, 'skin_color_max_mm': .6,
            'wind_color_max_m_s': 45, 'gpu_used': False}
