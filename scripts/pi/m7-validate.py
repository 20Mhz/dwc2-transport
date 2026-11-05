#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bounded M7 observations. Operators move cables; this collector only reads."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import selectors
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'python'))
from dwc2_diag.evidence import write_manifest
from dwc2_diag.recording import (create_release_evidence, read_events, recording_errors,
                                 test_outcome, validate_release_evidence)


def metadata(args):
    package = args.bin.resolve().parent
    def revision(name):
        path = package/name
        return path.read_text().strip() if path.is_file() else 'unknown'
    installed_revision = args.hostlab/'REVISION'
    if installed_revision.is_file():
        hostlab_revision = installed_revision.read_text().strip()
    else:
        try:
            hostlab = subprocess.run(['git', '-C', str(args.hostlab), 'rev-parse', 'HEAD'], capture_output=True, text=True, timeout=5)
            hostlab_revision = hostlab.stdout.strip() if hostlab.returncode == 0 else 'unknown'
        except (OSError, subprocess.TimeoutExpired):
            hostlab_revision = 'unknown'
    model = Path('/proc/device-tree/model')
    cpuinfo = Path('/proc/cpuinfo').read_text()
    hardware = next((line.split(':', 1)[1].strip() for line in cpuinfo.splitlines() if line.startswith('Revision')), 'unknown')
    binaries = {name: hashlib.sha256((args.bin/name).read_bytes()).hexdigest() for name in ('usb-discover', 'usb-inspect')}
    applications = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in sorted((ROOT/'python/dwc2_diag').glob('*.py'))}
    applications['scripts/pi/m7-validate.py'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return {'schema': 1, 'evidence_kind': 'physical_observation',
            'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'sdk_revision': revision('REVISION'), 'application_revision': revision('APPLICATION_REVISION'),
            'hostlab_revision': hostlab_revision,
            'hostlab_revision_basis': 'installed REVISION manifest' if installed_revision.is_file() else 'Git checkout',
            'hostlab_binary_sha256': {name: hashlib.sha256((args.hostlab/'bin'/name).read_bytes()).hexdigest()
                                     for name in ('hostlab-session','hostlab-analyze')},
            'kernel': platform.release(), 'machine': platform.machine(),
            'host_model': model.read_bytes().rstrip(b'\0').decode() if model.exists() else 'unknown',
            'hardware_revision': hardware, 'controller': 'dwc2',
            'controller_verification': 'checked against observed snapshots',
            'binary_sha256': binaries, 'application_sha256': applications,
            'parameters': {'test': args.test, 'duration_seconds': args.duration, 'interval_seconds': args.interval,
                           'iterations': args.iterations, 'port': args.port, 'probe_attempts': 3,
                           'probe_on_connect': args.test in ('D1', 'D2', 'D3'),
                           'operator_action': 'manual cable reconnection' if args.test == 'D2' else 'none requested',
                           'physical_model': 'owner-identified A1427; unverified'}}


def run_observer(args, index):
    wrapper = args.bin/'usb-observe'
    command = [sys.executable, str(wrapper), '--bin', str(args.bin), '--port', args.port,
               '--duration', str(args.duration), '--interval', str(args.interval), '--kernel-errors']
    if args.test in ('D1', 'D2', 'D3'):
        command.append('--probe-on-connect')
    elif getattr(args,'probe_on_connect',False):
        command.append('--probe-on-connect')
    if getattr(args,'record_samples',False):command.append('--record-samples')
    if getattr(args,'session_id',None):
        command += ['--session-id',args.session_id,'--annotations',str(args.out/'operator-input.jsonl')]
    if args.test == 'D2':
        command.append('--stop-after-reconnect')
    logfile = args.out/f'observer-{index}.jsonl'
    pending = bytearray()
    ready = False
    stop = [False]
    def request_stop(_signal, _frame):
        stop[0] = True
    old = {sig: signal.signal(sig, request_stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    with logfile.open('wb') as output, (args.out/f'observer-{index}.stderr').open('wb') as stderr:
        child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=stderr, start_new_session=True)
        selector = selectors.DefaultSelector(); selector.register(child.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + args.duration + 20
        signal_at = None
        output_bytes = 0
        try:
            while child.poll() is None:
                for key, _ in selector.select(.1):
                    data = os.read(key.fd, 65536)
                    output_bytes += len(data)
                    if output_bytes > getattr(args,'max_output_bytes',64*1024*1024):
                        os.killpg(child.pid,signal.SIGKILL)
                        continue
                    output.write(data); output.flush(); pending.extend(data)
                    while b'\n' in pending:
                        line, _, tail = pending.partition(b'\n'); pending = bytearray(tail)
                        row = json.loads(line)
                        ready_event = 'connected' if args.test == 'D4' else 'descriptor_probe_ok'
                        if not ready and row.get('event') == ready_event:
                            ready = True
                            print(json.dumps({'event': 'ready', 'test': args.test, 'iteration': index,
                                              'address': row.get('address', row.get('snapshot', {}).get('address'))}), flush=True)
                            if args.test == 'D4':
                                child.send_signal(signal.SIGTERM); signal_at = time.monotonic()
                if stop[0] and signal_at is None:
                    child.send_signal(signal.SIGTERM); signal_at = time.monotonic()
                if time.monotonic() > deadline or signal_at is not None and time.monotonic() - signal_at > 18:
                    os.killpg(child.pid, signal.SIGKILL)
                    break
            tail = child.stdout.read(); output.write(tail)
            child.wait(timeout=5)
        finally:
            selector.close(); child.stdout.close()
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL); child.wait()
            for sig, handler in old.items():
                signal.signal(sig, handler)
    return child.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    collect = commands.add_parser('record')
    collect.add_argument('--bin', type=Path, required=True)
    collect.add_argument('--hostlab', type=Path, required=True)
    collect.add_argument('--out', type=Path, required=True)
    collect.add_argument('--test', choices=('D1', 'D2', 'D3', 'D4'), required=True)
    collect.add_argument('--duration', type=float, default=10)
    collect.add_argument('--interval', type=float, default=.5)
    collect.add_argument('--iterations', type=int, default=3)
    collect.add_argument('--port', default='1-1')
    assemble = commands.add_parser('assemble')
    assemble.add_argument('--out', type=Path, required=True)
    assemble.add_argument('--recording', type=Path, action='append', default=[])
    assemble.add_argument('--pending-reason', required=True)
    assemble.add_argument('--operator-context', type=Path, help='JSON operator report; D2 cable-only pass requires explicit power/reboot conditions')
    args = parser.parse_args()
    if args.operation == 'assemble':
        context = json.loads(args.operator_context.read_text()) if args.operator_context else {}
        result = create_release_evidence(args.out, args.recording, args.pending_reason, context)
        errors = validate_release_evidence(args.out)
        print(json.dumps({'result': result, 'validation_errors': errors}, indent=2))
        return bool(errors)
    if not 2 <= args.iterations <= 10 or not 0 < args.duration <= 3600 or not .05 <= args.interval <= 60 or args.duration/args.interval > 10000:
        parser.error('bounded duration/interval and 2..10 lifecycle iterations required')
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out/'metadata.json').write_text(json.dumps(metadata(args), indent=2)+'\n')
    codes = [run_observer(args, index) for index in range(args.iterations if args.test == 'D4' else 1)]
    reports = [test_outcome(args.test, read_events(args.out/f'observer-{index}.jsonl'), code) for index, code in enumerate(codes)]
    result = {'schema': 1, 'test': args.test, 'returncodes': codes, 'runs': reports,
              'children_reaped': True, 'status': 'PASS' if all(report['status'] == 'PASS' for report in reports) else 'FAIL'}
    (args.out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    write_manifest(args.out)
    errors = recording_errors(args.out)
    print(json.dumps({'result': result, 'validation_errors': errors}, indent=2), flush=True)
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
