# SPDX-License-Identifier: LGPL-3.0-only
"""Capture matched baseline/candidate results without relaxing assertions."""
import json
from pathlib import Path
import subprocess
import sys

phase = sys.argv[1]
root = Path.cwd()
results = root / 'diagnostic-results' / phase
results.mkdir(parents=True, exist_ok=True)
records = []
for repetition in range(1, 3):
    junit = results / ('ilu-{}.xml'.format(repetition))
    args = [sys.executable, '-m', 'pytest', '-q',
            'test_native_bjacobi.py::test_ILU_mpi4_nlocal2[0]',
            'test_native_bjacobi.py::test_ILU_mpi4_nlocal2_part[0]',
            '--junitxml=' + str(junit)]
    run = subprocess.run(args, cwd=root / 'builds/build_release/tests/lin_alg',
                         text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (results / ('ilu-{}.log'.format(repetition))).write_text(run.stdout)
    print(run.stdout, flush=True)
    records.append({'case': 'ilu', 'run': repetition, 'status': run.returncode})
run = subprocess.run([sys.executable, '-m', 'pytest', '-q', 'test_ThinCurr.py',
                      '-k', 'test_torus_fourier_sensor', '--junitxml=' + str(results / 'sensor.xml')],
                     cwd=root / 'builds/build_release/tests/physics', text=True,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
(results / 'sensor.log').write_text(run.stdout)
print(run.stdout, flush=True)
records.append({'case': 'sensor', 'status': run.returncode})
(results / 'summary.json').write_text(json.dumps(records, indent=2))
assert run.returncode == 0, 'Sensor checks must pass from the correct working directory'
assert all(record['status'] in (0, 1) for record in records), 'Unexpected pytest setup error'
