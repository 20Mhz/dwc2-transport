#!/usr/bin/env python3
"""Bounded Apple USB descriptor diagnostics using the installed SDK.

Reads public descriptors through the Apple TV profile; does not switch modes,
reset, claim interfaces, or invoke restoration/firmware tools. Mode/VID alone
cannot establish the physical Apple TV model.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))
from dwc2_diag.evidence import trace_report



def verify_trace(out, expected):
    """Use the shared strict evidence validator."""
    return trace_report(out, expected)['passed']


def capture(bin_dir, out, wait_seconds=0, device=None, hostlab=None):
    bin_dir = Path(bin_dir).resolve()
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    results = []
    deadline = time.monotonic() + wait_seconds
    prefix = ['--profile', 'apple-tv-a1427']

    def run(name, command, timeout=20):
        try:
            process = subprocess.run(command, capture_output=True, timeout=timeout)
            stdout, stderr, code = process.stdout, process.stderr, process.returncode
        except subprocess.TimeoutExpired as error:
            stdout, stderr, code = error.stdout or b'', error.stderr or b'', None
        (out / f'{name}.stdout').write_bytes(stdout)
        (out / f'{name}.stderr').write_bytes(stderr)
        results.append({'name': name, 'returncode': code, 'command': [str(x) for x in command]})
        try:
            return code, json.loads(stdout)
        except (ValueError, UnicodeDecodeError):
            return code, None

    model = Path('/proc/device-tree/model')
    revision = bin_dir.parent / 'REVISION'
    metadata = {
        'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'capture_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'kernel': platform.release(), 'machine': platform.machine(),
        'host_model': model.read_bytes().rstrip(b'\0').decode() if model.exists() else None,
        'sdk_revision': revision.read_text().strip() if revision.exists() else 'unknown',
        'application_revision': (bin_dir.parent/'APPLICATION_REVISION').read_text().strip() if (bin_dir.parent/'APPLICATION_REVISION').exists() else 'unknown',
        'target_model': 'A1427 requested by owner; not independently verified',
        'binary_sha256': {name: hashlib.sha256((bin_dir / name).read_bytes()).hexdigest()
                          for name in ('usb-discover', 'usb-inspect', 'usb-diagnostics')},
        'parameters': {'wait_seconds': wait_seconds, 'device': device, 'repeat': 25,
                       'process_restarts': 5, 'trace_repeat': 10},
    }
    (out / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    attempt = 0
    selected = None
    state = 'unavailable'
    detail = 'No Apple USB device discovered'
    while True:
        code, inventory = run(f'discovery-{attempt:03}',
                              [str(bin_dir / 'usb-discover'), *prefix, '--json'])
        if code != 0 or not isinstance(inventory, dict):
            state, detail = 'failed', 'SDK discovery failed'
            break
        devices = inventory.get('devices', [])
        if device:
            devices = [item for item in devices if item.get('path') == device]
        if len(devices) > 1:
            state, detail = 'needs_selection', 'Multiple Apple devices; select exact --device path'
            break
        if devices:
            selected = devices[0]
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(min(2, max(0, deadline - time.monotonic())))
        attempt += 1
    if selected:
        path = selected['path']
        metadata['discovered_device'] = selected
        (out / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
        print(json.dumps({'event': 'apple_detected', 'path': path,
                          'usb_mode': selected.get('usb_mode')}), flush=True)
        selector = [*prefix, '--device', path]
        code, inspection = run('inspection',
                               [str(bin_dir / 'usb-inspect'), *selector, '--json'])
        descriptor = (inspection or {}).get('device_descriptor', {})
        inspect_ok = (code == 0 and len(descriptor.get('raw', '')) == 36
                      and bool((inspection or {}).get('configurations'))
                      and all(item.get('status') == 'ok'
                              for item in (inspection or {}).get('configurations', [])))
        code, diagnostic = run('diagnostics',
                               [str(bin_dir / 'usb-diagnostics'), *selector,
                                '--repeat', '25', '--json'], timeout=40)
        transfers = (diagnostic or {}).get('transfers', {})
        diagnostics_ok = code == 0 and transfers.get('ok') == 25 and transfers.get('errors') == 0
        restarts_ok = True
        for index in range(5):
            code, diagnostic = run(f'start-stop-{index:02}',
                                   [str(bin_dir / 'usb-diagnostics'), *selector,
                                    '--repeat', '1', '--json'])
            transfers = (diagnostic or {}).get('transfers', {})
            restarts_ok &= code == 0 and transfers.get('ok') == 1 and transfers.get('errors') == 0
        trace_ok = None
        if hostlab:
            hostlab = Path(hostlab).resolve()
            trace = out / 'hostlab-session'
            run('hostlab', [str(hostlab / 'bin/hostlab-session'), 'run', '--out', str(trace),
                            '--bindir', str(hostlab / 'bin'), '--profile', 'fast', '--',
                            str(bin_dir / 'usb-diagnostics'), *selector,
                            '--repeat', '10', '--jsonl'], timeout=35)
            run('hostlab-analysis', [str(hostlab / 'bin/hostlab-analyze'), str(trace),
                                     '--json', str(out / 'hostlab-analysis.json')])
            trace_ok = verify_trace(out, 10)
        code, after = run('post-discovery', [str(bin_dir / 'usb-discover'), *prefix, '--json'])
        same_device = any(item.get('path') == path and item.get('vendor_id') == selected['vendor_id']
                          and item.get('product_id') == selected['product_id']
                          for item in (after or {}).get('devices', []))
        passed = inspect_ok and diagnostics_ok and restarts_ok and code == 0 and same_device
        passed &= all(item['returncode'] == 0 for item in results)
        if hostlab:
            passed &= trace_ok is True
        state = 'passed' if passed else 'failed'
        detail = {'inspection_ok': inspect_ok, 'diagnostics_ok': diagnostics_ok,
                  'process_restarts_ok': restarts_ok, 'post_discovery_identity_match': same_device,
                  'hostlab_trace_ok': trace_ok}
    summary = {'state': state, 'detail': detail, 'results': results,
               'physical_model_verified': False, 'device': selected,
               'physical_reconnect_tested': False}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    paths = sorted(p for p in out.rglob('*') if p.is_file())
    (out / 'SHA256SUMS').write_text(''.join(
        f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}\n' for p in paths))
    print(json.dumps({'state': state, 'detail': detail, 'evidence': str(out)}), flush=True)
    return 0 if state == 'passed' else 2 if state in ('unavailable', 'needs_selection') else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--device', help='Exact path if multiple Apple devices are attached')
    parser.add_argument('--wait-seconds', type=int, default=0, choices=range(0, 121))
    parser.add_argument('--hostlab', type=Path)
    args = parser.parse_args()
    return capture(args.bin, args.out, args.wait_seconds, args.device, args.hostlab)


if __name__ == '__main__':
    raise SystemExit(main())
