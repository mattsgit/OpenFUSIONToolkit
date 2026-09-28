# SPDX-License-Identifier: LGPL-3.0-only
"""Repeat the unchanged Taylor-Green assertions and preserve the solver trace."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

root = Path.cwd()
results = root / 'diagnostic-results' / os.environ.get('TRACE_PHASE', 'traced')
results.mkdir(parents=True, exist_ok=True)
records = []
for threads in (2, 1, 4):
    for iteration in range(1, int(os.environ.get('TRACE_REPEATS', '15')) + 1):
        env = dict(os.environ, OMP_NUM_THREADS=str(threads))
        try:
            process = subprocess.Popen(
                [sys.executable, str(root / '.github/workflows/run_traced_taylor.py')],
                cwd=root / 'builds/build_release/tests/physics',
                env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, start_new_session=True)
            output, _ = process.communicate(timeout=180)
            status = process.returncode
            if 'ERROR:' in output or 'WARNING:' in output:
                status = status or 1
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            output, _ = process.communicate()
            output = 'Diagnostic timed out\n' + output
            status = 124
        log = results / 'threads{}-run{}.log'.format(threads, iteration)
        log.write_text(output)
        record = {'threads': threads, 'run': iteration, 'status': status, 'log': log.name}
        records.append(record)
        print(json.dumps(record), flush=True)
        (results / 'summary.json').write_text(json.dumps(records, indent=2))
        if status:
            print('\n'.join(output.splitlines()[-100:]), flush=True)
            break
print('Failures: {}'.format(sum(record['status'] != 0 for record in records)), flush=True)
