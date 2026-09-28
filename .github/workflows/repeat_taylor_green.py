"""Run unchanged Taylor-Green assertions repeatedly for diagnostic evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys

phase = sys.argv[1]
out = Path('../../../diagnostic-results')
out.mkdir(exist_ok=True)
results = []
for threads in (1, 2, 4):
    for iteration in range(15):
        env = dict(os.environ, OMP_NUM_THREADS=str(threads))
        result = subprocess.run(
            [sys.executable, '-m', 'pytest', '-q',
             'physics/test_taylor_green_2d.py::test_taylor_green_p2[True]'],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            timeout=180,
        )
        filename = '{}-threads{}-run{}.log'.format(phase, threads, iteration)
        (out / filename).write_text(result.stdout)
        results.append({'phase': phase, 'threads': threads, 'run': iteration, 'exit': result.returncode})
        print(results[-1], flush=True)
(out / (phase + '-summary.json')).write_text(json.dumps(results, indent=2))
print('Failures:', sum(r['exit'] != 0 for r in results), 'of', len(results), flush=True)
# Baseline failures are data; continue to the experimental fix for comparison.
if phase != 'baseline' and any(r['exit'] != 0 for r in results):
    raise SystemExit(1)
