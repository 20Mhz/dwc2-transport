# SPDX-License-Identifier: MIT
"""Redacted, versioned evidence bundles. Raw recordings stay in local-only storage."""
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from .descriptors import DescriptorError, device_descriptor, configuration_descriptor


def redact_inspection(document):
    value = copy.deepcopy(document)
    descriptor = value.get('device_descriptor', {})
    serial = descriptor.get('serial_index')
    if serial is None:
        raw = bytes.fromhex(descriptor.get('raw', ''))
        serial = raw[16] if len(raw) == 18 else 0
    for index, item in enumerate(value.get('strings', [])):
        if serial and item.get('index') == serial or item.get('roles_mask', 0) & 4:
            value['strings'][index] = {'index': item['index'], 'status': 'redacted', 'redacted': True}
    value['serial_policy'] = 'redacted'
    return value


def privacy_errors(document):
    if not isinstance(document, dict):
        return ['inspection is not an object']
    errors = []
    if document.get('serial_policy') != 'redacted':
        errors.append('missing default redaction policy')
    descriptor = document.get('device_descriptor', {})
    try:
        serial = descriptor.get('serial_index')
        raw = bytes.fromhex(descriptor.get('raw', ''))
        if len(raw) != 18:
            errors.append('missing valid device descriptor')
        if serial is None:
            serial = raw[16] if len(raw) == 18 else 0
        for item in document.get('strings', []):
            if serial and item.get('index') == serial or item.get('roles_mask', 0) & 4:
                if not item.get('redacted') or 'raw' in item or 'text' in item:
                    errors.append('serial descriptor content present')
    except (TypeError, ValueError, AttributeError):
        errors.append('malformed inspection structure')
    return errors



def inspection_errors(document):
    errors = privacy_errors(document)
    try:
        descriptor = device_descriptor(bytes.fromhex(document['device_descriptor']['raw']))
        configs = document['configurations']
        if len(configs) != descriptor['configurations']:
            errors.append('configuration count mismatch')
        for config in configs:
            if config.get('status') != 'ok':
                errors.append('configuration read failed')
            else:
                configuration_descriptor(bytes.fromhex(config['raw']), descriptor['usb_bcd'])
        identity = document['device']
        if (identity['vendor_id'], identity['product_id']) != (descriptor['vendor_id'], descriptor['product_id']):
            errors.append('device/descriptor identity mismatch')
    except (KeyError, ValueError, TypeError, AttributeError, DescriptorError):
        errors.append('missing or malformed descriptor characterization')
    return errors


def trace_report(root, expected=10):
    root = Path(root)
    problems = []
    result = {'expected_control_urbs': expected, 'profile': 'fast',
              'direct_urb_pointer_correlation': False, 'passed': False, 'errors': problems}
    try:
        session = json.loads((root/'hostlab-session/session.json').read_text())
        analysis = json.loads((root/'hostlab-analysis.json').read_text())
        rows = [json.loads(line) for line in (root/'hostlab-session/usbmon.jsonl').read_text().splitlines()]
        user = [json.loads(line) for line in (root/'hostlab-session/user.jsonl').read_text().splitlines()]
        if not all(isinstance(x, dict) for x in [session, analysis, *rows, *user]):
            raise ValueError('invalid record types')
        result['profile'] = session.get('profile', 'unknown')
        consistency, channels = analysis['consistency'], analysis['channel_events']
        if not isinstance(consistency, dict) or not isinstance(channels, dict):
            raise ValueError('missing analysis objects')
        stats = [row for row in rows if row.get('ev') == 'stats']
        transfers = [row for row in user if row.get('ev') == 'xfer']
        checks = {
            'capture command failed': session.get('command_exit') == 0,
            'session warnings present': session.get('warnings') == [],
            'teardown errors or missing teardown': session.get('teardown', {}).get('errors') == [],
            'missing or dropped usbmon data': bool(stats) and all(row.get('queued') == 0 and row.get('dropped') == 0 for row in stats),
            'userspace transfer evidence incomplete': len(transfers) == expected and all(row.get('status') == 'ok' and row.get('actual') == 18 for row in transfers),
            'kernel URB evidence incomplete': consistency.get('ctrl_urbs_ok', 0) >= expected,
            'phase reconstruction incomplete': consistency.get('ctrl_urbs_phases_exact', 0) >= expected,
            'unattributed/ambiguous channels': channels.get('unattributed') == 0 and channels.get('ambiguous') == 0,
        }
        problems.extend(name for name, passed in checks.items() if not passed)
        result.update({'control_urbs_ok': consistency.get('ctrl_urbs_ok'),
                       'complete_phase_urbs': consistency.get('ctrl_urbs_phases_exact'),
                       'channel_starts': channels.get('total'), 'usbmon_stats': stats,
                       'session_warnings': session.get('warnings'), 'teardown': session.get('teardown'),
                       'usbmon_unpaired_with_kprobes': consistency.get('usbmon_unpaired_with_kprobes')})
        result['passed'] = not problems
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        problems.append('empty, malformed or missing trace evidence')
    return result


def write_manifest(root):
    root = Path(root)
    files = sorted(path for path in root.rglob('*') if path.is_file() and path != root/'SHA256SUMS')
    (root/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}\n' for path in files))


def verify_manifest(root):
    root = Path(root).resolve()
    listed = set()
    try:
        lines = (root/'SHA256SUMS').read_text().splitlines()
        if not lines:
            return ['empty manifest']
        for line in lines:
            digest, name = line.split('  ', 1)
            relative = PurePosixPath(name)
            if (not re.fullmatch(r'[0-9a-f]{64}', digest) or relative.is_absolute()
                    or '..' in relative.parts or name in listed or name == 'SHA256SUMS'):
                return ['invalid manifest entry']
            path = (root/name).resolve()
            if root not in path.parents or not path.is_file():
                return ['missing file or path outside evidence bundle']
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                return ['evidence checksum mismatch: ' + name]
            listed.add(name)
        actual = {path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file() and path != root/'SHA256SUMS'}
        if actual != listed:
            return ['manifest does not cover all files']
    except (OSError, ValueError):
        return ['missing or malformed manifest']
    return []


def observer_report(rows):
    if not rows or any(not isinstance(row, dict) for row in rows):
        return {'valid': False, 'physical_reconnect_observed': False}
    summaries = [row for row in rows if row.get('event') == 'summary']
    kinds = [row.get('event') for row in rows]
    reconnects = [row for row in rows if row.get('event') == 'reconnected']
    probes = [row for row in rows if row.get('event') == 'descriptor_probe_ok']
    return {'valid': len(summaries) == 1 and rows[-1].get('event') == 'summary',
            'physical_reconnect_observed': 'disconnected' in kinds and bool(reconnects),
            'probe_after_reconnect': any(probe.get('mono_ns', 0) > reconnect.get('mono_ns', 0)
                                         and probe.get('port') == reconnect.get('port')
                                         for probe in probes for reconnect in reconnects),
            'summary': summaries[-1] if summaries else None,
            'disconnected_events': kinds.count('disconnected'), 'reconnected_events': len(reconnects),
            'probes_ok': len(probes)}


def create_bundle(raw_root, destination, database, observer_logs=(), termination=None):
    raw_root, destination = Path(raw_root), Path(destination)
    if raw_root.resolve() == destination.resolve() or raw_root.resolve() in destination.resolve().parents or destination.resolve() in raw_root.resolve().parents:
        raise ValueError('raw and redacted evidence directories must not overlap')
    raw_errors = verify_manifest(raw_root)
    if raw_errors:
        raise ValueError('raw evidence integrity: ' + '; '.join(raw_errors))
    destination.mkdir(parents=True, exist_ok=False)
    metadata = json.loads((raw_root/'metadata.json').read_text())
    summary = json.loads((raw_root/'summary.json').read_text())
    inspection = redact_inspection(json.loads((raw_root/'inspection.stdout').read_text()))
    diagnostics = json.loads((raw_root/'diagnostics.stdout').read_text())
    trace = trace_report(raw_root)
    reports = []
    for number, path in enumerate(observer_logs):
        rows = [json.loads(line) for line in Path(path).read_text().splitlines()]
        report = observer_report(rows)
        reports.append(report)
        # Observer snapshots never read serials; do not copy raw strings/log messages.
        for row in rows:
            if row.get('event') == 'kernel_enumeration_error' and 'message' in row:
                raise ValueError('raw kernel messages are not publishable')
        (destination/f'observer-{number}.jsonl').write_text(''.join(json.dumps(row, sort_keys=True)+'\n' for row in rows))
    checks = {'device_capture': summary.get('state') == 'passed',
              'descriptor_characterization': not inspection_errors(inspection),
              'serial_redacted': not privacy_errors(inspection), 'trace_complete': trace['passed'],
              'standard_transfers': diagnostics.get('transfers', {}).get('ok') == 25 and diagnostics.get('transfers', {}).get('errors') == 0,
              'observer_evidence_complete': bool(reports) and all(item['valid'] for item in reports)}
    if termination is not None:
        checks['process_termination'] = (termination.get('returncode') == 0
                                         and termination.get('summary', {}).get('reason') == 'signal')
    references = [{'path': path.relative_to(raw_root).as_posix(),
                   'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                  for path in sorted(raw_root.rglob('*')) if path.is_file()]
    documents = {'metadata.json': metadata, 'inspection.json': inspection,
                 'diagnostics.json': diagnostics, 'identification-database.json': database,
                 'trace-summary.json': trace, 'raw-references.json': {'storage': 'local-only; not included', 'files': references},
                 'result.json': {'schema': 1, 'milestone': 'M6', 'passed': all(checks.values()),
                                 'checks': checks, 'observers': reports,
                                 'inspection_warnings': [{'index':item.get('index'), 'status':item.get('status')} for item in inspection.get('strings', []) if item.get('status') not in ('ok', 'redacted')],
                                 'physical_reconnect_observed': any(r['physical_reconnect_observed'] for r in reports),
                                 'probe_after_reconnect': any(r.get('probe_after_reconnect') for r in reports),
                                 'physical_model_verified': False, 'firmware_or_security_changes': False}}
    if termination is not None:
        documents['termination.json'] = termination
    for name, value in documents.items():
        (destination/name).write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')
    write_manifest(destination)
    return documents['result.json']


def validate_bundle(root):
    root = Path(root)
    errors = verify_manifest(root)
    try:
        result = json.loads((root/'result.json').read_text())
        inspection = json.loads((root/'inspection.json').read_text())
        errors.extend(inspection_errors(inspection))
        if result.get('schema') != 1 or result.get('milestone') != 'M6':
            errors.append('unsupported evidence schema')
        if not result.get('passed') or not result.get('checks') or not all(result['checks'].values()):
            errors.append('evidence does not report all requested checks passing')
        diagnostic = json.loads((root/'diagnostics.json').read_text())
        if diagnostic.get('transfers', {}).get('ok') != 25 or diagnostic.get('transfers', {}).get('errors') != 0:
            errors.append('actual transfer results do not support pass claim')
        trace = json.loads((root/'trace-summary.json').read_text())
        if not trace.get('passed') or trace.get('direct_urb_pointer_correlation') is not False:
            errors.append('trace result missing or overstated')
        if (trace.get('control_urbs_ok', 0) < 10 or trace.get('complete_phase_urbs', 0) < 10
                or not trace.get('usbmon_stats') or trace.get('session_warnings') != []
                or trace.get('teardown', {}).get('errors') != []
                or any(row.get('queued') != 0 or row.get('dropped') != 0 for row in trace['usbmon_stats'])):
            errors.append('actual trace summary does not support pass claim')
        reports = [observer_report([json.loads(line) for line in path.read_text().splitlines()])
                   for path in sorted(root.glob('observer-*.jsonl'), key=lambda p: int(p.stem.split('-')[-1]))]
        if not reports or not all(report['valid'] for report in reports) or reports != result.get('observers'):
            errors.append('observer records do not support reported results')
        if (result.get('physical_reconnect_observed') != any(report['physical_reconnect_observed'] for report in reports)
                or result.get('probe_after_reconnect') != any(report.get('probe_after_reconnect', False) for report in reports)):
            errors.append('observer records do not support reconnect claims')
        if result.get('checks', {}).get('process_termination'):
            termination = json.loads((root/'termination.json').read_text())
            if termination.get('returncode') != 0 or termination.get('summary', {}).get('reason') != 'signal':
                errors.append('actual process termination does not support pass claim')
        meta = json.loads((root/'metadata.json').read_text())
        if not re.fullmatch(r'[0-9a-f]{40}', meta.get('sdk_revision', '')) or not meta.get('kernel'):
            errors.append('missing source/kernel provenance')
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        errors.append('missing or malformed evidence report')
    return errors
