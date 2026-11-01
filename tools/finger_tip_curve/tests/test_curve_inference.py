import json
from pathlib import Path
import numpy as np
import pytest
from curve_inference import infer_curve
from synthetic import cases


@pytest.mark.parametrize('name', list(cases()))
def test_fixtures(name):
    case = cases()[name]
    result = infer_curve(case['request'])
    assert result['status'] == case['expected_status'], result
    assert result['model_family'] == case['expected_model']
    assert result['prediction_probability'] is None
    assert result['probability_calibrated'] is False
    json.dumps(result, allow_nan=False)


def test_parameter_recovery():
    for name, target in [('circle', dict(h=1,k=-1,r=2)), ('quadratic', dict(a=.8,b=-.3,c=.2))]:
        result = infer_curve(cases()[name]['request'])
        for k,v in target.items():
            assert result['parameters'][k] == pytest.approx(v, abs=.015)
    result = infer_curve(cases()['vertical']['request'])
    assert result['parameters']['A'] == pytest.approx(1, abs=.01)
    assert result['parameters']['C'] == pytest.approx(-3, abs=.02)


def test_unreferenced_and_intent():
    request = cases()['circle']['request']
    request.pop('frame')
    result = infer_curve(request)
    assert result['status'] == 'needs_reference'
    assert result['equation_identified'] is False
    assert result['parameter_frame'] == 'normalized_local'
    request.pop('mode')
    assert infer_curve(request)['status'] == 'rejected'


@pytest.mark.parametrize('points', [[], [[1,2]], [[1,2,3]]*20, [[float('nan'),2]]*20, [[float('inf'),2]]*20, 'bad', None])
def test_invalid(points):
    assert infer_curve(dict(mode='curve', points=points))['status'] == 'rejected'


@pytest.mark.parametrize('factor', [1e-5, 1e5])
def test_similarity(factor):
    request = cases()['circle']['request']
    request['points'] = (np.array(request['points'])*factor + [4*factor,-8*factor]).tolist()
    result = infer_curve(request)
    assert result['status'] == 'accepted'
    assert result['parameters']['r'] == pytest.approx(2*factor, rel=.01)


def test_determinism_order_and_duplicates():
    request = cases()['quadratic']['request']
    first = infer_curve(request)
    request['points'] = request['points'][::-1]*2
    second = infer_curve(request)
    assert first['parameters'] == second['parameters']
    assert first['candidates'] == second['candidates']


def test_near_line_does_not_claim_quadratic():
    x = np.linspace(-2,2,80)
    result = infer_curve(dict(mode='curve', frame='referenced', units='u', points=np.c_[x,1e-5*x*x]))
    assert result['model_family'] != 'quadratic'
    assert result['status'] in ('accepted', 'ambiguous', 'rejected')


def test_saved_fixture_reproducibility():
    saved = json.loads(Path(__file__).resolve().parents[1].joinpath('synthetic_cases.json').read_text())
    assert saved == cases()
