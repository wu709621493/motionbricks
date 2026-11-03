"""Synthetic shallow-slope screening; not a site safety or earthquake model."""
from dataclasses import dataclass
from math import cos, sin, tan, radians, isfinite

G = 9.80665


@dataclass(frozen=True)
class Plane:
    """Planar block; area is slip-plane area, thickness is normal to plane."""
    label: str
    slope_deg: float
    thickness_m: float
    density_kg_m3: float
    cohesion_pa: float
    friction_deg: float
    pore_pressure_pa: float
    root_cohesion_pa: float = 0.0
    area_m2: float = 1.0

    def __post_init__(self):
        values = [v for k, v in vars(self).items() if k != 'label']
        if not self.label or not all(isfinite(v) for v in values):
            raise ValueError('label and finite parameters required')
        if not (0 < self.slope_deg < 90 and 0 <= self.friction_deg < 90):
            raise ValueError('invalid angles')
        if min(self.thickness_m, self.density_kg_m3, self.area_m2) <= 0:
            raise ValueError('positive dimensions and density required')
        if min(self.cohesion_pa, self.pore_pressure_pa, self.root_cohesion_pa) < 0:
            raise ValueError('negative strength or pore pressure unsupported')
        if self.pore_pressure_pa >= self.weight_pa * cos(radians(self.slope_deg)):
            raise ValueError('nonpositive effective normal stress is out of scope')

    @property
    def weight_pa(self):
        return self.density_kg_m3 * self.thickness_m * G

    def threshold(self):
        """Horizontal adverse inertia a=kh*g; N=W(cos(theta)-kh*sin(theta))."""
        theta, phi = radians(self.slope_deg), radians(self.friction_deg)
        w = self.weight_pa
        margin = (self.cohesion_pa + self.root_cohesion_pa
                  + (w*cos(theta)-self.pore_pressure_pa)*tan(phi)
                  - w*sin(theta))
        kh = margin / (w*(cos(theta)+sin(theta)*tan(phi)))
        contact_kh = (w*cos(theta)-self.pore_pressure_pa)/(w*sin(theta))
        status = 'static_failure' if kh <= 0 else 'yield'
        if kh >= contact_kh:
            status = 'effective_contact_limit_before_yield'
        return {'label': self.label, 'status': status,
                'critical_kh': max(0.0, kh) if status != 'effective_contact_limit_before_yield' else None,
                'effective_contact_limit_kh': contact_kh,
                'static_margin_pa': margin,
                'static_margin_n': margin*self.area_m2}


def displacement(plane, horizontal_accel_m_s2, dt_s):
    """One-way rigid block; input is piecewise-constant signed adverse inertia.

    Constant strength/pressure, no cyclic damage or evolving roots. Exact stop
    event within each sample; return displacement including post-record runout.
    """
    if not isfinite(dt_s) or dt_s <= 0:
        raise ValueError('positive finite dt required')
    result = plane.threshold()
    if result['status'] != 'yield':
        raise ValueError('requires statically stable, contact-valid yield model')
    theta, phi = radians(plane.slope_deg), radians(plane.friction_deg)
    factor = cos(theta)+sin(theta)*tan(phi)
    ay = result['critical_kh']*G
    v = x = 0.0
    for a in horizontal_accel_m_s2:
        if not isfinite(a):
            raise ValueError('nonfinite acceleration')
        if a/G >= result['effective_contact_limit_kh']:
            raise ValueError('effective contact lost; model invalid')
        acc = factor*(a-ay)
        if v == 0 and acc <= 0:
            continue
        duration = min(dt_s, v/-acc) if acc < 0 else dt_s
        x += v*duration + 0.5*acc*duration*duration
        v = max(0.0, v+acc*duration)
    record_x, record_v = x, v
    x += v*v/(2*factor*ay)
    return {'record_displacement_m': record_x, 'record_end_velocity_m_s': record_v,
            'residual_displacement_m': x}


def screen(planes):
    """Rank only supplied independent planes, not a spatial failure simulation."""
    planes = list(planes)
    if not planes or len({p.label for p in planes}) != len(planes):
        raise ValueError('nonempty, uniquely labelled candidates required')
    results = [p.threshold() for p in planes]
    # Do not silently rank an unmodelled contact failure as stable.
    if any(r['critical_kh'] is None for r in results):
        return {'weakest_candidates': None, 'status': 'incomplete', 'planes': results}
    minimum = min(r['critical_kh'] for r in results)
    return {'weakest_candidates': [r['label'] for r in results if abs(r['critical_kh']-minimum) < 1e-12],
            'status': 'screened_candidates_only', 'planes': results}
