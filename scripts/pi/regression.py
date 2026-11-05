#!/usr/bin/env python3
"""Run bounded USB SDK validation on Linux and preserve actual process results."""
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
import time


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--bin', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--device', required=True)
    ap.add_argument('--ch340-in', action='store_true')
    ap.add_argument('--reset', action='store_true')
    ap.add_argument('--hostlab', type=Path)
    args = ap.parse_args()
    args.bin = args.bin.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    results = []
    model_path = Path('/proc/device-tree/model')
    meta = {'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'kernel': platform.release(), 'machine': platform.machine(),
            'model': model_path.read_bytes().rstrip(b'\0').decode() if model_path.exists() else None,
            'device': args.device, 'ch340_in': args.ch340_in, 'reset': args.reset,
            'revision': (args.bin.parent / 'REVISION').read_text().strip(),
            'sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in args.bin.iterdir() if p.is_file()}}
    (args.out / 'metadata.json').write_text(json.dumps(meta, indent=2) + '\n')

    def run(name, command, timeout=45):
        try:
            p = subprocess.run(command, capture_output=True, timeout=timeout)
            (args.out / f'{name}.stdout').write_bytes(p.stdout)
            (args.out / f'{name}.stderr').write_bytes(p.stderr)
            results.append({'name': name, 'returncode': p.returncode})
            return p
        except subprocess.TimeoutExpired as e:
            (args.out / f'{name}.stdout').write_bytes(e.stdout or b'')
            (args.out / f'{name}.stderr').write_bytes(e.stderr or b'')
            results.append({'name': name, 'timeout': True, 'returncode': None})
            return None

    run('discovery', [str(args.bin / 'usb-discover'), '--json'])
    run('inspection', [str(args.bin / 'usb-inspect'), '--device', args.device, '--json'])
    run('diagnostics', [str(args.bin / 'usb-diagnostics'), '--device', args.device, '--repeat', '50', '--json'])
    command = [str(args.bin / 'test-hardware'), args.device]
    if args.ch340_in:
        command.append('--ch340-in')
    if args.reset:
        command.append('--reset')
    run('regression', command)
    if args.ch340_in:
        # A signal handler only sets a flag; normal code closes pending work.
        p = subprocess.Popen(command + ['--hold'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        selector = selectors.DefaultSelector()
        selector.register(p.stdout, selectors.EVENT_READ)
        output = bytearray()
        deadline = time.monotonic() + 20
        sent = False
        try:
            while p.poll() is None and time.monotonic() < deadline:
                for key, _ in selector.select(0.1):
                    block = os.read(key.fd, 65536)
                    output.extend(block)
                    if not sent and b'"signal_ready"' in output:
                        p.send_signal(signal.SIGTERM)
                        sent = True
            if p.poll() is None:
                p.kill()
            tail, err = p.communicate(timeout=5)
            output.extend(tail)
            (args.out / 'termination.stdout').write_bytes(output)
            (args.out / 'termination.stderr').write_bytes(err)
            results.append({'name': 'termination', 'returncode': p.returncode, 'signal_sent': sent})
        finally:
            selector.close()
            if p.poll() is None:
                p.kill()
                p.wait()
    # Repeated separate processes exercise kernel fd/URB cleanup across exit.
    for i in range(20):
        run(f'start-stop-{i:02}', [str(args.bin / 'usb-diagnostics'), '--device', args.device, '--repeat', '1', '--json'])
    if args.hostlab:
        trace = args.out / 'hostlab-session'
        run('hostlab', [str(args.hostlab / 'bin/hostlab-session'), 'run', '--out', str(trace),
                        '--bindir', str(args.hostlab / 'bin'), '--profile', 'fast', '--',
                        str(args.bin / 'usb-diagnostics'), '--device', args.device,
                        '--repeat', '30', '--jsonl'])
        run('hostlab-analysis', [str(args.hostlab / 'bin/hostlab-analyze'), str(trace),
                                 '--json', str(args.out / 'hostlab-analysis.json')])
    run('post-discovery', [str(args.bin / 'usb-discover'), '--json'])
    failures = [r for r in results if r['returncode'] != 0]
    summary = {'results': results, 'failed_processes': len(failures),
               'physical_disconnect_reconnect': 'SKIP: requires physical cable operation',
               'apple_tv_a1427': 'not validated; no attached device in this run'}
    (args.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
