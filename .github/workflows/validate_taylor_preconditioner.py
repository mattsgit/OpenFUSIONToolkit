# SPDX-License-Identifier: LGPL-3.0-only
"""Bounded fork-only validation of the Taylor-Green test preconditioner.

Run from the repository root after sourcing setup_env.sh. Native tests always
run in the configured build tree. This script changes no source or XML files.
"""
import argparse
import importlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


OLD_XML = 'oft_in_taylor_green.xml'
NEW_XML = 'oft_in_taylor_green_p2_mf.xml'
ACTIVE_PROCESS = None


def interrupted(signum, frame):
    """Terminate an active subprocess tree when this driver is interrupted."""
    if ACTIVE_PROCESS is not None and ACTIVE_PROCESS.poll() is None:
        os.killpg(ACTIVE_PROCESS.pid, signal.SIGKILL)
    raise SystemExit(128 + signum)


def save_json(path, value):
    """Persist a diagnostic record with ordinary JSON numeric values."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def capture(argv, cwd, env, timeout):
    """Drain both output streams and terminate the whole process group on timeout."""
    global ACTIVE_PROCESS
    started = time.monotonic()
    process = subprocess.Popen(
        argv, cwd=str(cwd), env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, universal_newlines=True, start_new_session=True)
    ACTIVE_PROCESS = process
    timed_out = False
    try:
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                output, _ = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                output, _ = process.communicate()
    finally:
        ACTIVE_PROCESS = None
    return output, 124 if timed_out else process.returncode, time.monotonic() - started


def finite_float(value):
    """Parse finite Fortran-style numeric output."""
    result = float(value.replace('D', 'E').replace('d', 'e'))
    if not math.isfinite(result):
        raise ValueError('Nonfinite value: ' + value)
    return result


class NativeRecorder:
    """Run the module's native commands with strict output and freshness checks."""

    def __init__(self, args, physics_dir):
        self.args = args
        self.physics_dir = physics_dir
        self.records = []
        self.case_id = args.kind

    def pytest_runtest_setup(self, item):
        """Attach pytest's complete case name to each native invocation."""
        self.case_id = item.nodeid

    def run(self, command, nproc, timeout):
        """Replace run_OFT while retaining its command and failure semantics."""
        if nproc > 1 and not self.args.mpi:
            import pytest
            pytest.skip('Not compiled with MPI')
        argv = shlex.split(command)
        if len(argv) != 3 or argv[0] != './test_taylor_green_2d':
            raise RuntimeError('Unexpected native command: ' + command)
        inputs = (self.physics_dir / argv[1]).read_text()
        order = int(re.search(r'^\s*order\s*=\s*(\d+)', inputs, re.M).group(1))
        mf = re.search(r'^\s*use_mfnk\s*=\s*([TF])', inputs, re.M).group(1) == 'T'
        expected_xml = NEW_XML if order == 2 and mf and nproc == 1 else OLD_XML
        if argv[2] != expected_xml:
            raise RuntimeError('Incorrect variant routing: ' + command)
        if self.args.kind == 'baseline':
            argv[2] = OLD_XML
        nlocal = int(ET.parse(str(self.physics_dir / argv[2])).findtext('.//nlocal'))
        expected_parts = 2 if argv[2] == NEW_XML else 1
        if nlocal != expected_parts:
            raise RuntimeError('Incorrect XML partition count')

        result_file = self.physics_dir / 'taylor_green_2d.results'
        history_file = self.physics_dir / 'xmhd_2d.hist'
        for path in (result_file, history_file):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        if nproc > 1:
            argv = ['mpirun', '--map-by', ':OVERSUBSCRIBE', '-np', str(nproc)] + argv
        output, status, elapsed = capture(
            argv, self.physics_dir, os.environ.copy(), min(timeout, self.args.timeout))
        print(output, end='', flush=True)
        record = {
            'case': self.case_id, 'command': argv, 'nproc': nproc,
            'threads': os.environ.get('OMP_NUM_THREADS'), 'xml_nlocal': nlocal,
            'status': status, 'elapsed_seconds': elapsed, 'checks': [],
        }
        checks = record['checks']
        if status:
            checks.append('Native exit status {}'.format(status))
        if any(marker in output for marker in ('ERROR:', 'WARNING:', 'SKIP TEST', 'Not compiled with PETSc')):
            checks.append('Native output contains an error, warning, or skip')
        if not re.search(r'Linear Algebra backend:\s*native\b', output):
            checks.append('Missing native linear algebra backend confirmation')
        actual_threads = [int(value) for value in re.findall(r'# of OpenMP threads\s*=\s*(\d+)', output)]
        record['actual_threads'] = actual_threads
        requested_threads = os.environ.get('OMP_NUM_THREADS')
        if not actual_threads or (requested_threads and any(
                value != int(requested_threads) for value in actual_threads)):
            checks.append('Native OpenMP thread count does not match the request')
        if ('Not compiled with MPI' in output) != (not self.args.mpi):
            checks.append('Native MPI build configuration does not match the request')
        try:
            values = [finite_float(value) for value in result_file.read_text().split()]
            if len(values) != 3:
                raise ValueError('Expected three current-run physics errors')
            record['errors'] = values
        except (OSError, ValueError) as error:
            checks.append(str(error))
        final_times = []
        try:
            final_times = [finite_float(value) for value in re.findall(r'Final time\s*=\s*(\S+)', output)]
            if len(final_times) != nproc or any(abs(value - 0.5) > 1.e-8 for value in final_times):
                raise ValueError('Expected final time 0.5 from each MPI rank')
        except ValueError as error:
            checks.append(str(error))
        record['final_times'] = final_times
        steps = re.findall(r'^\s*Timestep\s+(\d+)\s+(\S+)\s+(\d+)\s+(\d+)', output, re.M)
        try:
            progression = [
                {'step': int(step), 'time': finite_float(value),
                 'linear_iterations': int(linear), 'nonlinear_iterations': int(nonlinear)}
                for step, value, linear, nonlinear in steps]
            if [entry['step'] for entry in progression] != list(range(1, 21)):
                raise ValueError('Expected twenty completed timesteps')
            if any(abs(entry['time'] - entry['step'] * 0.025) > 1.e-8 for entry in progression):
                raise ValueError('Adaptive timestepping changed the simulated interval')
            record['timesteps'] = progression
        except ValueError as error:
            checks.append(str(error))
        if not history_file.is_file() or history_file.stat().st_size == 0:
            checks.append('Missing current-run history file')
        if self.args.debug and expected_parts == 2:
            if not re.search(r'- NLocal:\s*2\b', output):
                checks.append('Debug output did not confirm NLocal=2')
        index = len(self.records) + 1
        for path in (result_file, history_file):
            if path.is_file():
                shutil.copyfile(str(path), str(self.args.output_dir / '{}-{}'.format(index, path.name)))
        (self.args.output_dir / 'native-{}.log'.format(index)).write_text(output)
        self.records.append(record)
        save_json(self.args.output_dir / 'native-runs.json', self.records)
        print('DIAGNOSTIC_NATIVE ' + json.dumps(record, allow_nan=False), flush=True)
        return not checks


def child(args):
    """Invoke the real test module in a fresh process from the build tree."""
    physics_dir = args.build_dir / 'tests' / 'physics'
    os.chdir(str(physics_dir))
    sys.path.insert(0, str(physics_dir))
    case = importlib.import_module('test_taylor_green_2d')
    if args.debug:
        case.oft_in_template, count = re.subn(r'\bdebug\s*=\s*0\b', 'debug=1', case.oft_in_template)
        if count != 1:
            raise RuntimeError('Could not enable diagnostic setup output')
    recorder = NativeRecorder(args, physics_dir)
    case.run_OFT = recorder.run
    if args.mode == '_case':
        case.test_taylor_green_p2(True)
        if len(recorder.records) != 1:
            raise RuntimeError('No native case executed')
        return 0
    import pytest
    return pytest.main([
        'test_taylor_green_2d.py', '-s', '-v', '-x',
        '--junitxml=' + str(args.output_dir / 'suite.junit.xml'),
    ], plugins=[recorder])


def run_child(args, label, kind='candidate', debug=False, suite=False, threads=None):
    """Collect one isolated case or suite and retain its exit status and log."""
    destination = args.output_dir / label
    destination.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, str(Path(__file__).resolve()), '_suite' if suite else '_case',
            '--build-dir', str(args.build_dir), '--output-dir', str(destination),
            '--mpi', str(args.mpi), '--kind', kind, '--timeout', str(args.timeout)]
    if debug:
        argv.append('--debug')
    env = os.environ.copy()
    env['OFT_HAVE_MPI'] = str(args.mpi)
    env['OMP_DYNAMIC'] = 'FALSE'
    if threads is not None:
        env['OMP_NUM_THREADS'] = str(threads)
    output, status, elapsed = capture(
        argv, args.build_dir / 'tests' / 'physics', env,
        args.suite_timeout if suite else args.timeout + 60)
    (destination / 'run.log').write_text(output)
    result = {'label': label, 'status': status, 'elapsed_seconds': elapsed,
              'log': str(destination / 'run.log')}
    native_path = destination / 'native-runs.json'
    result['native_runs'] = json.loads(native_path.read_text()) if native_path.is_file() else []
    if status:
        print('\n'.join(output.splitlines()[-100:]), flush=True)
    print(json.dumps({key: value for key, value in result.items() if key != 'native_runs'}), flush=True)
    return result


def check_suite(result, args):
    """Require exactly the expected native/pure cases and permitted MPI skips."""
    path = args.output_dir / 'suite' / 'suite.junit.xml'
    if result['status'] or not path.is_file():
        return False
    cases = ET.parse(str(path)).findall('.//testcase')
    skipped = [case for case in cases if case.find('skipped') is not None]
    failed = [case for case in cases if case.find('failure') is not None or case.find('error') is not None]
    expected_skips = 0 if args.mpi else 6
    passed = len(cases) - len(skipped) - len(failed)
    result['junit'] = {'collected': len(cases), 'passed': passed,
                       'skipped': len(skipped), 'failed': len(failed)}
    return (len(cases) == 22 and passed == (22 if args.mpi else 16)
            and len(skipped) == expected_skips and not failed
            and all('_mpi[' in case.get('name', '') for case in skipped)
            and len(result['native_runs']) == (12 if args.mpi else 6)
            and all(not run['checks'] and run['status'] == 0 for run in result['native_runs']))


def main():
    """Run a bounded diagnostic phase and make every candidate failure fatal."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('smoke', 'suite', 'repeat', 'trace', '_case', '_suite'))
    parser.add_argument('--build-dir', type=Path, default=Path('builds/build_release'))
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--mpi', type=int, choices=(0, 1), default=int(os.environ.get('OFT_HAVE_MPI', '0')))
    parser.add_argument('--repetitions', type=int, default=30)
    parser.add_argument('--timeout', type=int, default=1000)
    parser.add_argument('--suite-timeout', type=int, default=7200)
    parser.add_argument('--kind', choices=('candidate', 'baseline'), default='candidate', help=argparse.SUPPRESS)
    parser.add_argument('--debug', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if min(args.repetitions, args.timeout, args.suite_timeout) < 1:
        parser.error('Counts and timeouts must be positive')
    args.build_dir = args.build_dir.resolve()
    if args.output_dir is None:
        args.output_dir = Path('diagnostic-results') / ('mpi{}'.format(args.mpi)) / args.mode
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    if args.mode.startswith('_'):
        return child(args)

    records = []
    success = True
    if args.mode == 'smoke':
        records.append(run_child(args, 'baseline', kind='baseline', threads=2))
        records.append(run_child(args, 'candidate', debug=True, threads=2))
        success = records[-1]['status'] == 0
    elif args.mode == 'trace':
        records.append(run_child(args, 'trace', debug=True, threads=2))
        success = records[-1]['status'] == 0
    elif args.mode == 'suite':
        records.append(run_child(args, 'suite', suite=True))
        success = check_suite(records[-1], args)
    else:
        for threads in (1, 2, 4):
            for iteration in range(1, args.repetitions + 1):
                record = run_child(args, 'threads{}-run{}'.format(threads, iteration), threads=threads)
                records.append(record)
                success = record['status'] == 0
                save_json(args.output_dir / 'summary.json', {'success': success, 'runs': records})
                if not success:
                    break
            if not success:
                break
    save_json(args.output_dir / 'summary.json', {'success': success, 'runs': records})
    print('Phase {}: {}'.format(args.mode, 'PASS' if success else 'FAIL'), flush=True)
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
