"""SR-71-inspired civil concept planform, not construction or certified CAD."""
import hashlib

import numpy as np

from motionbricks.memory_lab_render import Rasterizer, png_bytes, text, transform
from motionbricks.wheal_typhoon_render import CYAN, MUTED, PINK, WHITE, line


def render(path, aircraft, cases, runtime):
    from motionbricks.rs72 import wing_deflection
    raster = Rasterizer(1600, 1150)
    im = raster.image
    text(im, 50, 35, 'MOTIONBRICKS / CIVIL WEATHER RESEARCH CONCEPT', MUTED, 2)
    text(im, 50, 85, 'TAIQIANG RS-72', WHITE, 5)
    text(im, 50, 145, 'SR-71 INSPIRED / SUBSONIC / INTUITION AND EXPERIMENT', CYAN, 2)
    text(im, 50, 205, 'PLANFORM STUDY / 24 M SPAN', WHITE, 2)
    text(im, 850, 205, 'WING STIFFNESS / ELASTIC BEAM', WHITE, 2)
    # Coordinates in metres, span x and longitudinal station y; 24 m wing span,
    # 22 m body. Main trapezoid area is exactly 70 m^2 (body/chines separate).
    root_chord = 4.4
    tip_chord = 2 * aircraft.wing_area_m2 / aircraft.span_m - root_chord
    polygons = [([(-.7, 8), (-2.8, 1), (0, -1)], (90, 133, 149)),
                ([(.7, 8), (2.8, 1), (0, -1)], (90, 133, 149)),
                ([(0, 2), (-12, -1), (-12, -1-tip_chord), (0, 2-root_chord)], (69, 113, 132)),
                ([(0, 2), (12, -1), (12, -1-tip_chord), (0, 2-root_chord)], (69, 113, 132)),
                ([(-1, -5), (-5, -9), (-5, -10), (0, -8)], (78, 119, 138)),
                ([(1, -5), (5, -9), (5, -10), (0, -8)], (78, 119, 138)),
                ([(0, 12), (-.7, 8), (-1.3, 1), (-1, -7), (0, -10),
                  (1, -7), (1.3, 1), (.7, 8)], (144, 167, 177))]
    # Chines are illustration features, not extra computed lift.
    # Twin turboprop nacelle placeholders. Propulsion integration is not modelled.
    for side in (-1, 1):
        x = side * 4
        polygons.append(([(x-.55, 4), (x-.7, 1), (x-.5, -5), (x+.5, -5), (x+.7, 1), (x+.55, 4)], (186, 201, 205)))
    checked = 0
    for obj, (points, tint) in enumerate(polygons):
        vertices = np.array([[x, y, -obj*.01, 1] for x, y in points], dtype=float)
        projected = transform(runtime, vertices, np.diag([1., -1., 1., 1.]))
        checked += len(vertices)
        projected[:, :2] = projected[:, :2] * 20 + [405, 500]
        # Convex polygons in this schematic use a fan triangulation.
        for k in range(1, len(points)-1):
            raster.triangle(projected[[0, k, k+1], :3], tint, raster.triangles, obj)
    for side in (-1, 1):
        x = 405 + side*80
        line(im, (x-40, 415), (x+40, 415), CYAN, 2)
    text(im, 70, 755, 'CHINES / TWIN NACELLES / SENSOR NOSE', MUTED, 2)
    text(im, 70, 785, 'ILLUSTRATION ONLY / NO AERO VALIDATION', MUTED, 2)
    # Beam graph: actual units; no exaggerated aircraft deformation masquerading
    # as a solved airframe. Uniform load and rigid root are explicit assumptions.
    left, top, width, height = 910, 300, 550, 350
    for value in (0, .2, .4, .6):
        yy = top+height*(1-value/.6)
        line(im, (left, yy), (left+width, yy), (44, 62, 79))
        text(im, left-60, int(yy)-7, f'{value:.1f}', MUTED, 2)
    x = np.linspace(0, aircraft.span_m/2, 121)
    for n, tint in ((1, CYAN), (2.5, PINK)):
        d = wing_deflection(x, n, aircraft)
        points = np.column_stack((left+width*x/(aircraft.span_m/2), top+height*(1-d/.6)))
        for a, b in zip(points, points[1:]):
            line(im, a, b, tint)
    text(im, 910, 260, 'DEFLECTION / M', MUTED, 2)
    text(im, 910, 670, '0', MUTED, 2)
    text(im, 1435, 670, '12', MUTED, 2)
    text(im, 1040, 710, 'ROOT TO TIP / M', MUTED, 2)
    text(im, 910, 755, 'CYAN 1 G / PINK 2.5 G', MUTED, 2)
    text(im, 910, 785, 'STIFFNESS DOES NOT DEFINE TOUGHNESS', MUTED, 2)
    line(im, (50, 840), (1550, 840), (44, 62, 79))
    text(im, 50, 870, '100 M/S TAS / VERTICAL GUST SENSITIVITY', WHITE, 2)
    selected = [c for c in cases if c['tas_m_s'] == 100 and c['vertical_gust_m_s'] >= 0]
    for i, case in enumerate(selected):
        xx = 50 + i*385
        tint = CYAN if case['status'] == 'WITHIN_ASSUMED_SCREENS' else PINK
        text(im, xx, 915, f'GUST {case["vertical_gust_m_s"]:.1f} M/S', tint, 2)
        text(im, xx, 950, f'N {case["n"]:.2f} / TIP {case["tip_deflection_m"]:.2f} M', WHITE, 2)
        text(im, xx, 985, f'TRIAL STRESS {case["elastic_trial_stress_mpa"]:.0f} MPA', MUTED, 2)
    text(im, 50, 1025, '15 M/S COLUMN: OUTSIDE LINEAR ASSUMPTIONS / EXTRAPOLATED VALUES', PINK, 2)
    text(im, 50, 1065, 'BEAUFORT 12 IS NOT A GUST LOAD OR A FLIGHT CLEARANCE', MUTED, 2)
    text(im, 50, 1105, 'SYNTHETIC INPUTS / NO FLIGHT RELEASE / NO FATIGUE-LIFE CLAIM', MUTED, 2)
    encoded = png_bytes(im)
    with path.open('xb') as handle:
        handle.write(encoded)
    return {'path': path.name, 'image_sha256': hashlib.sha256(encoded).hexdigest(),
            'triangles': raster.triangles, 'vertices_transformed_and_checked': checked,
            'gpu_used': False, 'geometry_is_concept_only': True}
