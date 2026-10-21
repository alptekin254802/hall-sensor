"""Reproduce the post hoc three-point comparison from exported T summaries.

Run inside the snapshot: python reproduce_quadratic.py
No hardware access, model search, or modification of the frozen B model.
"""
from pathlib import Path
from data_access import raw_path, open_raw
import json
import numpy as np
from force_analysis.models import Calibrator

ROOT = Path(__file__).resolve().parent
G = 0.00980665
t = json.loads((ROOT / 'analysis/T.json').read_text(encoding='utf8'))
expected = json.loads((ROOT / 'analysis/T_quadratic.json').read_text(encoding='utf8'))
source = Calibrator.load(ROOT / 'models/S1_S2_S3_S4_interpolation.json')
out = {}
for result in expected['results']:
    color = result['spring']
    info = t[color]
    spec = info['models']['scratch_three_point']
    x = np.array(spec['target_response_adc'], dtype=float)
    y = np.array(spec['mass_g'], dtype=float)
    assert list(y) == [0, 1502, 5000]
    assert np.allclose(x, result['target_response_adc'], atol=1e-12, rtol=0)
    u = x / x[-1]
    a, b = np.linalg.solve(np.column_stack((u[1:]**2, u[1:])), y[1:])
    assert min(b, 2*a+b) > 0
    errors = {k: [] for k in result['metrics']}
    for row, stored in zip(info['predictions']['scratch_three_point'], result['placements'], strict=True):
        assert row['capture_id'] == stored['capture_id']
        q, mass = row['feature_adc'], row['mass_g']
        assert x[0] <= q <= x[-1]
        mapped_q = float(np.interp(q, x, spec['green_response_adc']))
        transferred = source.predict([mapped_q])[0]
        assert transferred['status'] == 'ok'
        predictions = {
            'transfer': transferred['value_N'] / G,
            'direct_piecewise_linear': float(np.interp(q, x, y)),
            'direct_quadratic': a*(q/x[-1])**2 + b*(q/x[-1]),
        }
        for method, prediction in predictions.items():
            error = prediction - mass
            assert abs(error - stored['errors_g'][method]) < 1e-8
            errors[method].append(error)
    metrics = {}
    for method, values in errors.items():
        e = np.array(values) * G
        mae, rmse = float(abs(e).mean()), float(np.sqrt((e*e).mean()))
        assert abs(mae-result['metrics'][method]['mae_N']) < 1e-10
        assert abs(rmse-result['metrics'][method]['rmse_N']) < 1e-10
        metrics[method] = {'n': len(e), 'mae_N': mae, 'rmse_N': rmse}
    wins = {}
    for method in ['direct_piecewise_linear', 'direct_quadratic']:
        count = int(np.sum(abs(np.array(errors['transfer'])) < abs(np.array(errors[method]))-1e-9))
        assert count == result['paired_counts'][method]['transfer_smaller']
        wins[method] = count
    out[color] = {'metrics': metrics, 'transfer_lower_absolute_error': wins}
print(json.dumps(out, indent=2))
