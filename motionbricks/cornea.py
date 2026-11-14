"""Synthetic corneal shells, not a patient fit or biomechanical simulation.

Standard library only: python -S -m motionbricks.cornea --out-dir /tmp/cornea
Coordinates are millimetres; +y superior, +z anterior. Thickness is axial.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path

VERSION = "cornea-0.1"


@dataclass(frozen=True)
class Cornea:
    name: str = "healthy"
    aperture_mm: float = 5.0  # model radius: central 10 mm diameter
    radius_mm: float = 7.8
    q: float = -0.25
    central_thickness_mm: float = 0.55
    peripheral_increment_mm: float = 0.12
    cone_x_mm: float = 0.5
    cone_y_mm: float = -0.9
    cone_width_mm: float = 1.1
    protrusion_mm: float = 0.0
    thinning_mm: float = 0.0

    def __post_init__(self):
        numbers = [v for k, v in asdict(self).items() if k != "name"]
        if any(isinstance(v, bool) or not isinstance(v, (float, int))
               or not math.isfinite(v) for v in numbers):
            raise ValueError("parameters must be finite real numbers")
        if not isinstance(self.name, str) or not self.name or len(self.name) > 80:
            raise ValueError("name must be 1..80 characters")
        if not 1 <= self.aperture_mm <= 6 or not 6 <= self.radius_mm <= 10:
            raise ValueError("unsupported aperture or radius")
        if not -1 <= self.q <= 0 or not 0.3 <= self.central_thickness_mm <= 0.8:
            raise ValueError("unsupported asphericity or thickness")
        if not 0 <= self.peripheral_increment_mm <= 0.3:
            raise ValueError("invalid peripheral thickening")
        if math.hypot(self.cone_x_mm, self.cone_y_mm) > self.aperture_mm / 2:
            raise ValueError("cone center must be within half-aperture")
        if not 0.6 <= self.cone_width_mm <= 2 or not 0 <= self.protrusion_mm <= 0.5:
            raise ValueError("unsupported cone width or protrusion")
        # Bump <= 1 / taper(center); this conservative bound ensures no crossing.
        if not 0 <= self.thinning_mm <= 0.25 or (
            self.central_thickness_mm - self.thinning_mm / self._center_taper() <= 0.1
        ):
            raise ValueError("thinning could create an invalid shell")

    def _center_taper(self):
        return (1 - (self.cone_x_mm**2 + self.cone_y_mm**2) / self.aperture_mm**2)**2

    def sag(self, r):
        return r*r / (self.radius_mm + math.sqrt(
            self.radius_mm**2 - (1 + self.q)*r*r))

    def sample(self, x, y):
        """Return anterior z, posterior z, axial thickness in mm."""
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (x, y)):
            raise ValueError("coordinates must be finite")
        r2 = x*x + y*y
        if r2 > self.aperture_mm**2 + 1e-10:
            raise ValueError("sample outside aperture")
        taper = max(0.0, 1 - r2 / self.aperture_mm**2)**2
        bump = math.exp(-((x-self.cone_x_mm)**2 + (y-self.cone_y_mm)**2)
                        / (2*self.cone_width_mm**2)) * taper / self._center_taper()
        front = self.sag(self.aperture_mm) - self.sag(math.sqrt(r2)) + self.protrusion_mm*bump
        thickness = self.central_thickness_mm + self.peripheral_increment_mm*r2/self.aperture_mm**2 - self.thinning_mm*bump
        return front, front-thickness, thickness


HEALTHY = Cornea()
KERATOCONUS = Cornea(name="keratoconus", protrusion_mm=0.28, thinning_mm=0.20)


def make_mesh(model: Cornea, rings=24, sectors=72):
    """Closed oriented triangular shell, one center per surface (no pole duplicates)."""
    if type(rings) is not int or type(sectors) is not int or not (4 <= rings <= 100 and 12 <= sectors <= 256):
        raise ValueError("resolution: 4..100 rings, 12..256 sectors")
    xy = [(0.0, 0.0)] + [
        (model.aperture_mm*i/rings*math.cos(2*math.pi*j/sectors),
         model.aperture_mm*i/rings*math.sin(2*math.pi*j/sectors))
        for i in range(1, rings+1) for j in range(sectors)]
    samples = [model.sample(x, y) for x, y in xy]
    n = len(xy)
    vertices = [[x, y, samples[i][side]] for side in (0, 1) for i, (x, y) in enumerate(xy)]
    top = [[0, 1+j, 1+(j+1) % sectors] for j in range(sectors)]
    for ring in range(1, rings):
        for j in range(sectors):
            a, b = 1+(ring-1)*sectors+j, 1+(ring-1)*sectors+(j+1) % sectors
            c, d = a+sectors, b+sectors
            top.extend(([a, c, d], [a, d, b]))
    faces = top + [[c+n, b+n, a+n] for a, b, c in top]
    for j in range(sectors):
        a = 1+(rings-1)*sectors+j
        b = 1+(rings-1)*sectors+(j+1) % sectors
        faces.extend(([a, a+n, b+n], [a, b+n, b]))
    return {"name": model.name, "parameters": asdict(model), "vertices_mm": vertices,
            "faces": faces, "surface_vertex_count": n, "rings": rings, "sectors": sectors,
            "axial_thickness_um": [t*1000 for _, _, t in samples],
            "minimum_sampled_axial_thickness_um": min(t*1000 for _, _, t in samples)}


def validate_mesh(mesh):
    """Check closed oriented edges, finite vertices, nonzero faces, positive volume."""
    vertices, faces = mesh["vertices_mm"], mesh["faces"]
    if any(not math.isfinite(v) for p in vertices for v in p):
        raise ValueError("nonfinite vertex")
    edges, directed = Counter(), Counter()
    volume = 0.0
    for face in faces:
        if len(set(face)) != 3 or any(type(i) is not int or not 0 <= i < len(vertices) for i in face):
            raise ValueError("invalid face")
        a, b, c = [vertices[i] for i in face]
        u, v = [b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)]
        cross = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
        if sum(x*x for x in cross) < 1e-20:
            raise ValueError("degenerate triangle")
        volume += (a[0]*(b[1]*c[2]-b[2]*c[1]) + a[1]*(b[2]*c[0]-b[0]*c[2]) + a[2]*(b[0]*c[1]-b[1]*c[0]))/6
        for i, j in zip(face, face[1:]+face[:1]):
            edges[tuple(sorted((i, j)))] += 1
            directed[(i, j)] += 1
    if any(v != 2 for v in edges.values()) or any(directed[(i, j)] != directed[(j, i)] for i, j in edges):
        raise ValueError("mesh is not an oriented closed manifold")
    if volume <= 0:
        raise ValueError("nonpositive volume")
    return {"vertices": len(vertices), "triangles": len(faces), "closed_oriented": True,
            "signed_volume_mm3": volume}


def write_obj(mesh, path):
    lines = ["# Synthetic cornea; units mm; axial thickness; not a patient model"]
    lines += ["v " + " ".join(f"{v:.9f}" for v in p) for p in mesh["vertices_mm"]]
    lines += ["f " + " ".join(str(i+1) for i in f) for f in mesh["faces"]]
    path.write_text("\n".join(lines)+"\n", encoding="utf-8")


def export(out_dir, template=None):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    models = [make_mesh(m) for m in (HEALTHY, KERATOCONUS)]
    checks = {m["name"]: validate_mesh(m) for m in models}
    payload = {"version": VERSION, "synthetic": True, "units": "mm", "thickness_definition": "axial z separation",
               "coordinate_system": "+y superior; +z anterior; illustrative eye, no laterality",
               "models": models, "validation": checks}
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    (out/"models.json").write_text(raw+"\n", encoding="utf-8")
    for mesh in models:
        write_obj(mesh, out/(mesh["name"]+".obj"))
    if template:
        source = Path(template).read_text(encoding="utf-8")
        if source.count("__CORNEA_DATA__") != 1:
            raise ValueError("template must have exactly one data placeholder")
        (out/"index.html").write_text(source.replace("__CORNEA_DATA__", raw.replace("<", "\\u003c")), encoding="utf-8")
    names = ["models.json", "healthy.obj", "keratoconus.obj"] + (["index.html"] if template else [])
    manifest = {"version": VERSION, "synthetic": True, "files": {
        name: hashlib.sha256((out/name).read_bytes()).hexdigest() for name in names}, "validation": checks}
    (out/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--template", type=Path, help="HTML template for a self-contained viewer")
    args = parser.parse_args()
    print(json.dumps(export(args.out_dir, args.template), indent=2))


if __name__ == "__main__":
    main()
