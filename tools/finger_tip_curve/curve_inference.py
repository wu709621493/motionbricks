"""Conservative synthetic 2-D curve fitting. No calibrated probabilities."""
import argparse
import json
import numpy as np


FAMILIES = ('line', 'circle', 'quadratic')
TOLERANCE = 0.015  # Euclidean distance / robust trajectory scale


def _fit(family, p):
    x, y = p.T
    if family == 'line':
        center = p.mean(axis=0)
        _, singular, v = np.linalg.svd(p - center, full_matrices=False)
        if singular[0] < 1e-10:
            raise ValueError('degenerate line')
        normal = v[-1]
        if normal[np.argmax(abs(normal))] < 0:
            normal = -normal
        return np.r_[normal, -normal @ center]
    if family == 'circle':
        design = np.c_[2*x, 2*y, np.ones(len(p))]
        if np.linalg.cond(design) > 1e8:
            raise ValueError('ill-conditioned circle')
        h, k, d = np.linalg.lstsq(design, x*x + y*y, rcond=None)[0]
        r2 = d + h*h + k*k
        if r2 <= 0:
            raise ValueError('invalid radius')
        return np.array([h, k, np.sqrt(r2)])
    design = np.c_[x*x, x, np.ones(len(p))]
    if np.linalg.cond(design) > 1e6:
        raise ValueError('ill-conditioned quadratic')
    return np.linalg.lstsq(design, y, rcond=None)[0]


def _distance(family, q, p, exact=False):
    x, y = p.T
    if family == 'line':
        return abs(p @ q[:2] + q[2])
    if family == 'circle':
        return abs(np.linalg.norm(p-q[:2], axis=1)-q[2])
    a, b, c = q
    if not exact:
        return abs(a*x*x+b*x+c-y)/np.sqrt(1+(2*a*x+b)**2)
    # Stationary points of squared Euclidean distance to y=a*t^2+b*t+c.
    distances = []
    for px, py in p:
        roots = np.roots([2*a*a, 3*a*b, b*b+2*a*(c-py)+1, b*(c-py)-px])
        real = roots.real[abs(roots.imag) < 1e-7]
        distances.append(np.sqrt(np.min((real-px)**2+(a*real**2+b*real+c-py)**2)))
    return np.array(distances)


def _candidate(family, p, rng):
    best, key = None, None
    for i in range(129):
        sample = p if i == 0 else p[rng.choice(len(p), 2 if family == 'line' else 3, replace=False)]
        try:
            q = _fit(family, sample)
            d = _distance(family, q, p)
            current = (int((d <= TOLERANCE).sum()), -float(np.minimum(d, TOLERANCE).sum()))
            if key is None or current > key:
                best, key = q, current
        except (ValueError, np.linalg.LinAlgError, FloatingPointError):
            continue
    if best is None:
        return None
    for _ in range(3):
        mask = _distance(family, best, p, exact=True) <= TOLERANCE
        if mask.sum() < 12:
            return None
        try:
            best = _fit(family, p[mask])
        except (ValueError, np.linalg.LinAlgError):
            return None
    d = _distance(family, best, p, exact=True)
    mask = d <= TOLERANCE
    if mask.sum() < 12 or mask.mean() < 0.85:
        return None
    inliers = p[mask]
    coverage = None
    eligible = True
    if family == 'circle':
        angles = np.sort(np.mod(np.arctan2(*(inliers-best[:2]).T[::-1]), 2*np.pi))
        coverage = float(2*np.pi-np.diff(np.r_[angles, angles[0]+2*np.pi]).max())
        eligible = coverage >= np.pi
    if family == 'quadratic':
        # A near-zero quadratic term is nested in the line model, not evidence
        # for another family. Require curvature over the observed x domain.
        bend = abs(best[0])*np.ptp(inliers[:, 0])**2
        if bend < 0.06:
            return None
    return dict(model_family=family, parameters=best.tolist(),
                inlier_fraction=float(mask.mean()),
                normalized_inlier_rmse=float(np.sqrt(np.mean(d[mask]**2))),
                normalized_all_point_rmse=float(np.sqrt(np.mean(d*d))),
                coverage_radians=coverage, eligible=bool(eligible))


def infer_curve(request):
    """JSON-compatible request -> result. Invalid data rejects; never infers intent.

    frame='referenced': caller asserts orthogonal axes with equal known units.
    frame='unreferenced': only a local shape proposal; no intended equation.
    """
    result = dict(schema_version=1, status='rejected', reasons=[], model_family=None,
                  parameters=None, candidates=[], prediction_probability=None,
                  probability_calibrated=False, equation_identified=False)
    if not isinstance(request, dict):
        result['reasons'] = ['invalid_request']
        return result
    frame = request.get('frame', 'unreferenced')
    if request.get('mode') != 'curve' or frame not in ('referenced', 'unreferenced'):
        result['reasons'] = ['explicit_curve_mode_and_valid_frame_required']
        return result
    if frame == 'referenced' and not isinstance(request.get('units'), str):
        result['reasons'] = ['referenced_frame_requires_units']
        return result
    try:
        p = np.asarray(request.get('points'), dtype=float)
        if p.ndim != 2 or p.shape[1] != 2 or not np.isfinite(p).all() or len(p) > 5000:
            raise ValueError()
    except (TypeError, ValueError):
        result['reasons'] = ['invalid_points']
        return result
    original_n = len(p)
    p = np.unique(p, axis=0)
    result.update(input_count=original_n, unique_count=len(p), frame=frame)
    if len(p) < 12:
        result['reasons'] = ['insufficient_unique_points']
        return result
    center = np.median(p, axis=0)
    scale = float(np.quantile(np.linalg.norm(p-center, axis=1), 0.8))
    if not np.isfinite(scale) or scale <= np.finfo(float).eps*max(1, float(abs(p).max()))*100:
        result['reasons'] = ['unresolved_spatial_extent']
        return result
    p = (p-center)/scale
    result['normalization'] = dict(origin=center.tolist(), isotropic_scale=scale)
    rng = np.random.default_rng(20260322)
    candidates = [c for family in FAMILIES if (c := _candidate(family, p, rng)) is not None]
    candidates.sort(key=lambda c: c['normalized_inlier_rmse'])
    result['candidates'] = candidates
    if not candidates:
        result['reasons'] = ['no_reliable_supported_model']
        return result
    best = candidates[0]
    # Compare all plausible competitors, including undersampled circle arcs.
    if len(candidates) > 1 and candidates[1]['normalized_inlier_rmse'] <= max(0.003, 1.7*best['normalized_inlier_rmse']):
        result.update(status='ambiguous', reasons=['competing_models'])
        return result
    if not best['eligible']:
        result['reasons'] = ['insufficient_circle_coverage']
        return result
    family, q = best['model_family'], best['parameters']
    if frame == 'referenced':
        ox, oy = center
        if family == 'line':
            a, b, c = q
            params = dict(A=a, B=b, C=scale*c-a*ox-b*oy)
        elif family == 'circle':
            h, k, r = q
            params = dict(h=ox+scale*h, k=oy+scale*k, r=scale*r)
        else:
            a, b, c = q
            params = dict(a=a/scale, b=b-2*a*ox/scale, c=oy+scale*c-b*ox+a*ox*ox/scale)
    else:
        params = dict(zip({'line': ('A','B','C'), 'circle': ('h','k','r'), 'quadratic': ('a','b','c')}[family], q))
    result.update(status='accepted' if frame == 'referenced' else 'needs_reference',
                  reasons=[] if frame == 'referenced' else ['axes_origin_and_scale_unconfirmed'],
                  model_family=family, parameters={k: float(v) for k,v in params.items()},
                  equation_identified=frame == 'referenced',
                  parameter_frame='input' if frame == 'referenced' else 'normalized_local',
                  units=request.get('units') if frame == 'referenced' else None)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', help='JSON request file')
    args = parser.parse_args()
    with open(args.input, encoding='utf-8') as handle:
        request = json.load(handle)
    print(json.dumps(infer_curve(request), indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
