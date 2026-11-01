"""Seeded fixtures; coordinates are synthetic, never camera measurements."""
import json
from pathlib import Path
import numpy as np


def cases(seed=42):
    rng = np.random.default_rng(seed)
    x = np.linspace(-2, 2, 80)
    t = np.linspace(0, 2*np.pi, 80, endpoint=False)
    arc = np.linspace(-0.25, 0.25, 80)
    line = np.c_[x, 0.7*x+0.4]
    circle = np.c_[1+2*np.cos(t), -1+2*np.sin(t)]
    quadratic = np.c_[x, 0.8*x*x-0.3*x+0.2]
    noisy = lambda p: p+rng.normal(0, 0.005, p.shape)
    values = {
        'line': (noisy(line), 'accepted', 'line'),
        'vertical': (noisy(np.c_[np.full(80, 3.), x]), 'accepted', 'line'),
        'circle': (noisy(circle), 'accepted', 'circle'),
        'quadratic': (noisy(quadratic), 'accepted', 'quadratic'),
        'outliers': (np.r_[noisy(circle), [[12,12],[-8,9],[7,-9],[9,9]]], 'accepted', 'circle'),
        'duplicates': (np.repeat(circle, 3, axis=0), 'accepted', 'circle'),
        'few_unique': (np.repeat(line[:4], 20, axis=0), 'rejected', None),
        'short_arc': (np.c_[np.sin(arc), np.cos(arc)], 'ambiguous', None),
        'ellipse': (np.c_[3*np.cos(t), np.sin(t)], 'rejected', None),
        'sine': (np.c_[x, np.sin(4*x)], 'rejected', None),
        'cloud': (rng.uniform(-2,2,(80,2)), 'rejected', None),
        'two_strokes': (np.r_[line, np.c_[x, -0.7*x-0.7]], 'rejected', None),
        'point': (np.zeros((30,2)), 'rejected', None),
        'heavy_noise': (circle+rng.normal(0,0.3,circle.shape), 'rejected', None),
    }
    return {name: dict(request=dict(mode='curve', frame='referenced', units='synthetic_unit', points=p.tolist()), expected_status=status, expected_model=model) for name,(p,status,model) in values.items()}


if __name__ == '__main__':
    path = Path(__file__).with_name('synthetic_cases.json')
    path.write_text(json.dumps(cases(), indent=2)+'\n', encoding='utf-8')
