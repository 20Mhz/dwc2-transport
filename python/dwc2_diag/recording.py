# SPDX-License-Identifier: MIT
"""M7 recordings: strict completion and observation claims, separate from M6."""
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil

from .descriptors import cached_descriptors
from .evidence import verify_manifest, write_manifest
from .privacy import object_errors


def read_events(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def event_errors(rows):
    errors = []
    if len(rows) < 2 or any(not isinstance(row, dict) for row in rows):
        return ['missing event history']
    kinds = [row.get('event') for row in rows]
    if kinds[0] != 'meta' or kinds[-1] != 'summary' or kinds.count('meta') != 1 or kinds.count('summary') != 1:
        return ['incomplete event history']
    previous = -1
    origin = rows[0].get('mono_ns', 0) - rows[0].get('elapsed_ns', 0) if type(rows[0].get('mono_ns')) is int and type(rows[0].get('elapsed_ns')) is int else None
    states, generations = {}, {}
    for sequence, row in enumerate(rows, 1):
        if (row.get('schema') != 2 or row.get('sequence') != sequence
                or type(row.get('mono_ns')) is not int or row['mono_ns'] < previous
                or type(row.get('elapsed_ns')) is not int or row['elapsed_ns'] < 0
                or row['mono_ns'] - row['elapsed_ns'] != origin):
            errors.append('invalid event ordering or timestamp')
            break
        try:
            stamp = datetime.datetime.fromisoformat(row['time_utc'])
            if stamp.utcoffset() != datetime.timedelta(0):
                raise ValueError('UTC required')
        except (KeyError, TypeError, ValueError):
            errors.append('invalid UTC timestamp')
        previous = row['mono_ns']
        kind, port = row.get('event'), row.get('port')
        if kind in ('connected', 'reconnected', 'state_changed'):
            snapshot = row.get('snapshot', {})
            try:
                raw = bytes.fromhex(snapshot['device_descriptor']['raw'])
                raw += b''.join(bytes.fromhex(config['raw']) for config in snapshot['configurations'])
                parsed = cached_descriptors(raw)
                device = parsed['device_descriptor']
                if (device['vendor_id'], device['product_id']) != (snapshot['vendor_id'], snapshot['product_id']):
                    raise ValueError('identity mismatch')
                if snapshot.get('serial_policy') != 'not_read' or snapshot.get('port') != port:
                    raise ValueError('privacy/topology missing')
                if 'serial' in snapshot or 'strings' in snapshot:
                    raise ValueError('uncached identity data')
                generation = row['presence_generation']
                if kind == 'state_changed':
                    if port not in states or generations[port] != generation:
                        raise ValueError('change without presence')
                else:
                    if port in states or generation != generations.get(port, 0) + 1:
                        raise ValueError('invalid presence generation')
                    if kind == 'reconnected' and port not in generations:
                        raise ValueError('reconnect without prior presence')
                if row.get('cause') != 'unknown':
                    raise ValueError('unsupported transition cause')
                states[port], generations[port] = snapshot, generation
            except (KeyError, ValueError, TypeError, AttributeError):
                errors.append('invalid snapshot, generation or transition claim')
        elif kind == 'disconnected':
            if port not in states or row.get('presence_generation') != generations.get(port):
                errors.append('disconnect without observed presence')
            states.pop(port, None)
        elif kind == 'descriptor_probe_ok':
            if (port not in states or row.get('presence_generation') != generations.get(port)
                    or row.get('address') != states.get(port, {}).get('address') or row.get('serial_policy') != 'redacted'):
                errors.append('probe does not match current observed presence')
    summary = rows[-1]
    counts = {'connected': kinds.count('connected'), 'disconnected': kinds.count('disconnected'),
              'reconnected': kinds.count('reconnected'), 'probes_ok': kinds.count('descriptor_probe_ok'),
              'probes_failed': kinds.count('descriptor_probe_error'),
              'errors': kinds.count('device_error') + kinds.count('discovery_error')}
    if any(summary.get(key) != count for key, count in counts.items()):
        errors.append('summary contradicts event history')
    if (type(summary.get('polls')) is not int or summary['polls'] < 1
            or summary.get('completion_status') != 'complete' or summary.get('probes_pending') != 0
            or summary.get('reason') not in ('duration', 'signal', 'reconnected')):
        errors.append('recording is incomplete')
    return sorted(set(errors))


def test_outcome(name, rows, returncode):
    errors = event_errors(rows)
    if any(not isinstance(row, dict) for row in rows):
        return {'test': name, 'status': 'FAIL', 'errors': errors, 'summary': None}
    if returncode != 0:
        errors.append('observer process did not exit successfully')
    kinds = [row.get('event') for row in rows if isinstance(row, dict)]
    if name == 'D1':
        if (kinds.count('connected') != 1 or 'disconnected' in kinds or 'state_changed' in kinds
                or 'descriptor_probe_ok' not in kinds or 'descriptor_probe_error' in kinds
                or (rows[-1] if rows else {}).get('polls', 0) < 3):
            errors.append('stable descriptor baseline not demonstrated')
    elif name == 'D2':
        reconnects = [row for row in rows if row.get('event') == 'reconnected']
        probes = [row for row in rows if row.get('event') == 'descriptor_probe_ok']
        if not any(probe['mono_ns'] > reconnect['mono_ns'] and probe.get('port') == reconnect.get('port')
                   and probe.get('presence_generation') == reconnect.get('presence_generation')
                   and probe.get('address') == reconnect.get('snapshot', {}).get('address')
                   for reconnect in reconnects for probe in probes):
            errors.append('no descriptor recovery for a recorded reconnect')
    elif name == 'D4':
        if 'connected' not in kinds or (rows[-1] if rows else {}).get('reason') != 'signal':
            errors.append('startup and signal termination not demonstrated')
    elif name == 'D3':
        errors.append('no verified non-destructive recovery-entry procedure; manual review required')
    else:
        errors.append('unsupported physical test')
    return {'test': name, 'status': 'PASS' if not errors else 'FAIL', 'errors': sorted(set(errors)),
            'summary': rows[-1] if rows and isinstance(rows[-1], dict) else None}


def provenance_errors(metadata):
    errors = []
    for key in ('sdk_revision', 'application_revision', 'hostlab_revision'):
        if not re.fullmatch(r'[0-9a-f]{40}', metadata.get(key, '')):
            errors.append('missing exact ' + key)
    for key in ('kernel', 'host_model', 'hardware_revision', 'controller', 'parameters', 'binary_sha256', 'application_sha256'):
        if not metadata.get(key) or metadata.get(key) == 'unknown':
            errors.append('missing ' + key)
    for key in ('binary_sha256', 'application_sha256'):
        values = metadata.get(key)
        if not isinstance(values, dict) or not values or any(not re.fullmatch(r'[0-9a-f]{64}', value) for value in values.values()):
            errors.append('invalid ' + key)
    if metadata.get('evidence_kind') != 'physical_observation':
        errors.append('recording is not physical evidence')
    return errors


def recording_errors(root):
    root = Path(root)
    errors = verify_manifest(root)
    try:
        metadata = json.loads((root/'metadata.json').read_text())
        result = json.loads((root/'result.json').read_text())
        if object_errors(metadata) or object_errors(result):
            errors.append('sensitive fields in public recording')
        errors.extend(provenance_errors(metadata))
        files = sorted(root.glob('observer-*.jsonl'))
        for path in files:
            rows = read_events(path)
            if object_errors(rows):
                errors.append('sensitive fields in observer history')
            snapshots = [row['snapshot'] for row in rows if 'snapshot' in row]
            if not snapshots or any(snapshot.get('controller') != metadata.get('controller') for snapshot in snapshots):
                errors.append('controller provenance does not match observed snapshots')
        reports = [test_outcome(result['test'], read_events(path), result['returncodes'][index]) for index, path in enumerate(files)]
        if (not reports or len(files) != len(result['returncodes']) or reports != result.get('runs')
                or any(report['status'] != 'PASS' for report in reports) or result.get('status') != 'PASS'):
            errors.append('actual recording does not support pass claim')
        if result['test'] == 'D4' and (not 2 <= len(reports) <= 10 or result.get('children_reaped') is not True):
            errors.append('bounded independent lifecycle cleanup not demonstrated')
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError):
        errors.append('missing or malformed recording')
    return sorted(set(errors))


def cable_conditions_verified(context):
    return (context.get('source') == 'operator_report' and context.get('cable_reconnected') is True
            and context.get('power_maintained') is True and context.get('reboot_reported') is False)


def create_release_evidence(destination, recordings, pending, operator_context=None):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    operator_context = operator_context or {}
    if object_errors(operator_context):
        raise ValueError('sensitive fields in operator context')
    (destination/'operator-context.json').write_text(json.dumps(operator_context, indent=2)+'\n')
    tests = {}
    for path in recordings:
        root = Path(path)
        errors = recording_errors(root)
        if errors:
            raise ValueError('invalid recording: ' + '; '.join(errors))
        result = json.loads((root/'result.json').read_text())
        name = result['test']
        if name in tests:
            raise ValueError('duplicate test recording')
        public = destination/name
        public.mkdir()
        for source in [root/'metadata.json', root/'result.json', *sorted(root.glob('observer-*.jsonl'))]:
            shutil.copy2(source, public/source.name)
        (public/'raw-references.json').write_text(json.dumps({'storage': 'local-only', 'files': [
            {'path': str(path.relative_to(root)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in sorted(root.rglob('*')) if path.is_file()]}, indent=2)+'\n')
        write_manifest(public)
        tests[name] = {'status': 'PASS', 'evidence_kind': 'physical_observation', 'path': name}
        if name == 'D2':
            context = operator_context.get('D2', {})
            tests[name]['descriptor_recovery_observed'] = True
            if not cable_conditions_verified(context):
                tests[name]['status'] = ('INCONCLUSIVE_OPERATOR_REBOOT' if context.get('reboot_reported')
                                         else 'PENDING_OPERATOR_CONFIRMATION')
                tests[name]['reason'] = 'Re-enumeration and descriptor recovery observed; uninterrupted target power was not verified.'
    for name in ('D1', 'D2', 'D3', 'D4'):
        if name not in tests:
            tests[name] = {'status': 'PENDING_OPERATOR' if name != 'D3' else 'NOT_RUN_NO_VERIFIED_PROCEDURE',
                           'reason': pending, 'evidence_kind': 'not_observed'}
    report = {'schema': 1, 'milestone': 'M7', 'tests': tests,
              'physical_validation_complete': all(tests[name]['status'] == 'PASS' for name in ('D1', 'D2', 'D4')),
              'manual_state_transition_complete': tests['D3']['status'] == 'PASS',
              'cause_assessment': 'unknown; USB timing alone does not establish the cause of M6 transient errors',
              'firmware_or_security_changes': False, 'public_release_status': 'local_release_candidate'}
    (destination/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    write_manifest(destination)
    return report


def validate_release_evidence(root):
    root = Path(root)
    errors = verify_manifest(root)
    try:
        result = json.loads((root/'result.json').read_text())
        operator_context = json.loads((root/'operator-context.json').read_text())
        if object_errors(operator_context):
            errors.append('sensitive fields in operator context')
        if result.get('schema') != 1 or result.get('milestone') != 'M7':
            errors.append('unsupported release evidence')
        for name in ('D1', 'D2', 'D3', 'D4'):
            test = result['tests'][name]
            if test.get('path'):
                if test.get('path') != name:
                    errors.append('invalid test evidence path')
                    continue
                errors.extend(name + ': ' + error for error in recording_errors(root/name))
                if json.loads((root/name/'result.json').read_text())['test'] != name:
                    errors.append('test recording label mismatch')
            if test['status'] == 'PASS':
                if not test.get('path'):
                    errors.append('missing physical evidence for pass claim')
                if name == 'D2' and not cable_conditions_verified(operator_context.get('D2', {})):
                    errors.append('cable-only conditions were not confirmed')
            elif test['status'] not in ('PENDING_OPERATOR', 'NOT_RUN_NO_VERIFIED_PROCEDURE',
                                       'PENDING_OPERATOR_CONFIRMATION', 'INCONCLUSIVE_OPERATOR_REBOOT') or not test.get('reason'):
                errors.append('unexplained physical coverage gap')
        complete = all(result['tests'][name]['status'] == 'PASS' for name in ('D1', 'D2', 'D4'))
        if result.get('physical_validation_complete') is not complete or result.get('manual_state_transition_complete') is not (result['tests']['D3']['status'] == 'PASS'):
            errors.append('overstated physical completion')
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        errors.append('missing or malformed M7 release evidence')
    return sorted(set(errors))
