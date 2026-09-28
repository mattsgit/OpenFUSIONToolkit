# SPDX-License-Identifier: LGPL-3.0-only
"""Require the new regression to expose the original owned-dot cancellation."""
from pathlib import Path
import subprocess
import sys

result = subprocess.run(
    [sys.executable, '-m', 'pytest', '-q', '-m', 'not mpi', 'base/test_stitching.py'],
    cwd='builds/build_release/tests', text=True, stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT)
Path('diagnostic-results/old-dot-regression.log').write_text(result.stdout)
print(result.stdout, flush=True)
assert result.returncode == 1
assert '2 failed' in result.stdout
assert 'owned real squared norm' in result.stdout
