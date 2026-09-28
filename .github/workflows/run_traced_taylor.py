# SPDX-License-Identifier: LGPL-3.0-only
"""Run the existing Taylor-Green assertions while draining verbose solver output."""
import math
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path.cwd()))
import test_taylor_green_2d as case


def run_traced(command, nproc, timeout):
    """Stream the serial executable output to the collecting parent process.

    @param command Existing test executable command
    @param nproc Number of MPI processes, restricted to one for this diagnostic
    @param timeout Timeout in seconds
    @result Whether the executable exited successfully
    """
    assert nproc == 1
    result = subprocess.run(command, shell=True, timeout=timeout)
    return result.returncode == 0


case.run_OFT = run_traced
if os.environ.get('TRACE_VERBOSE', '1') == '1':
    case.oft_in_template = case.oft_in_template.replace('pm=F', 'pm=T')
case.test_taylor_green_p2(True)
errors = [float(value) for value in Path('taylor_green_2d.results').read_text().split()]
assert len(errors) == 3 and all(math.isfinite(value) for value in errors)
