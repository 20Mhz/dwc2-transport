# SPDX-License-Identifier: MIT
"""Passive cached-state observer with bounded optional SDK read-only probes."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

from .descriptors import DescriptorError, cached_descriptors
from .identification import identify, load_database
from .evidence import inspection_errors


class ObservationError(Exception):
    def __init__(self, status, operation, message, system_errno=None, returncode=None):
        self.status, self.operation, self.message = status, operation, message
        self.system_errno = system_errno
        self.returncode = returncode
        super().__init__(message)

    def record(self):
        domain = ('observer' if self.operation in ('subprocess', 'json', 'discovery', 'privacy', 'topology')
                  else 'device')
        return {'status': self.status, 'operation': self.operation, 'message': self.message,
                'system_errno': self.system_errno, 'returncode': self.returncode, 'domain': domain}


def command_json(command, timeout):
    try:
        process = subprocess.run([str(x) for x in command], capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise ObservationError('timeout', 'subprocess', 'read-only command exceeded its budget') from error
    except OSError as error:
        raise ObservationError('io', 'subprocess', 'could not execute diagnostic command', error.errno) from error
    try:
        result = json.loads(process.stdout)
    except (ValueError, UnicodeDecodeError) as error:
        raise ObservationError('protocol', 'json', 'empty or invalid diagnostic output', returncode=process.returncode) from error
    if not isinstance(result, dict):
        raise ObservationError('protocol', 'json', 'expected diagnostic object', returncode=process.returncode)
    if process.returncode:
        detail = result.get('error', {})
        if not isinstance(detail, dict):
            raise ObservationError('protocol', 'json', 'invalid diagnostic error object', returncode=process.returncode)
        raise ObservationError(detail.get('status', 'io'), detail.get('operation', 'diagnostic'),
                               'read-only diagnostic command failed',
                               detail.get('errno') if type(detail.get('errno')) is int else None, process.returncode)
    return result


def read_number(path, base=10):
    text = path.read_text().strip()
    if len(text) > 32:
        raise ValueError('oversized numeric attribute')
    return int(text, base)


def read_snapshot(info, sysfs_root, database):
    """Only cached sysfs metadata/descriptors; never read the serial attribute."""
    name = info.get('sysfs_name', '')
    if (any(type(info.get(key)) is not int for key in ('bus', 'address', 'vendor_id', 'product_id'))
            or any(not isinstance(info.get(key), str) for key in ('path', 'speed'))):
        raise ObservationError('protocol', 'discovery', 'missing or malformed inventory fields')
    if not re.fullmatch(r'\d+-\d+(?:\.\d+)*', name):
        raise ObservationError('invalid', 'topology', 'exact non-hub sysfs port name required')
    root = Path(sysfs_root) / name
    try:
        address = read_number(root / 'devnum')
        vendor, product = read_number(root / 'idVendor', 16), read_number(root / 'idProduct', 16)
        if (address, vendor, product) != (info['address'], info['vendor_id'], info['product_id']):
            raise ObservationError('again', 'snapshot', 'discovery identity changed during sampling')
        with (root / 'descriptors').open('rb') as stream:
            raw = stream.read(1024 * 1024 + 1)
        parsed = cached_descriptors(raw)
        descriptor = parsed['device_descriptor']
        if (descriptor['vendor_id'], descriptor['product_id']) != (vendor, product):
            raise ObservationError('again', 'snapshot', 'cached descriptor identity changed')
        active = read_number(root / 'bConfigurationValue')
        bindings = []
        for item in sorted(Path(sysfs_root).glob(name + ':*')):
            if not item.name.startswith(name + ':'):
                continue
            driver = ''
            try:
                driver = os.path.basename(os.readlink(item / 'driver'))
            except FileNotFoundError:
                pass
            bindings.append({'interface_path': item.name, 'driver': driver,
                             'number': read_number(item / 'bInterfaceNumber', 16),
                             'alternate': read_number(item / 'bAlternateSetting'),
                             'class': read_number(item / 'bInterfaceClass', 16),
                             'subclass': read_number(item / 'bInterfaceSubClass', 16),
                             'protocol': read_number(item / 'bInterfaceProtocol', 16)})
        # A disconnect/re-enumeration midway through reads must not create a hybrid snapshot.
        if read_number(root / 'devnum') != address:
            raise ObservationError('again', 'snapshot', 'device address changed during sampling')
        return {'port': name, 'bus': info['bus'], 'address': address, 'vendor_id': vendor,
                'product_id': product, 'path': info['path'], 'speed': info['speed'],
                'ports': info.get('ports', []), 'controller': info.get('controller', ''),
                'active_configuration': active, 'driver_bindings': bindings,
                'device_descriptor': descriptor, 'configurations': parsed['configurations'],
                'identification': identify(vendor, product, database), 'serial_policy': 'not_read',
                'cached_descriptor_sha256': hashlib.sha256(raw).hexdigest()}
    except FileNotFoundError as error:
        raise ObservationError('no_device', 'sysfs', 'device disappeared during cached reads', error.errno) from error
    except PermissionError as error:
        raise ObservationError('access', 'sysfs', 'cached state is not readable', error.errno) from error
    except (DescriptorError, ValueError, KeyError) as error:
        raise ObservationError('protocol', 'cached_descriptors', str(error)) from error
    except OSError as error:
        raise ObservationError('io', 'sysfs', 'cached state could not be read', error.errno) from error


class StateObserver:
    """A topology slot is an observation key, never proof of physical identity."""
    def __init__(self):
        self.states, self.seen, self.errors = {}, set(), {}
        self.discovery_error = None
        self.generations, self.transitions, self.absences, self.previous = {}, {}, {}, {}

    def update(self, states, errors=None, discovery_ok=True, now_ns=None):
        now_ns = time.monotonic_ns() if now_ns is None else now_ns
        errors = errors or {}
        events = []
        # Failed discovery is missing knowledge, not proof of disconnection.
        if not discovery_ok:
            error = errors.get('*', {'status': 'io'})
            self.discovery_error = error
            return [{'event': 'discovery_error', 'error': error}]
        if self.discovery_error is not None:
            events.append({'event': 'discovery_recovered'})
            self.discovery_error = None
        for port in sorted(set(self.states) - set(states) - set(errors)):
            old = self.states.pop(port)
            self.previous[port] = old
            self.absences[port] = now_ns
            events.append({'event': 'disconnected', 'port': port,
                           'previous_identity': {key: old[key] for key in ('vendor_id', 'product_id', 'address')},
                           'transition_duration_ns': now_ns - self.transitions[port],
                           'presence_generation': self.generations[port], 'cause': 'unknown'})
            self.transitions[port] = now_ns
            self.errors.pop(port, None)
        for port, error in sorted(errors.items()):
            events.append({'event': 'device_error', 'port': port, 'error': error})
            self.errors[port] = error
        for port, state in sorted(states.items()):
            if port not in self.states:
                self.generations[port] = self.generations.get(port, 0) + 1
                events.append({'event': 'reconnected' if port in self.seen else 'connected',
                               'port': port, 'snapshot': state, 'same_physical_device_verified': False,
                               'presence_generation': self.generations[port], 'cause': 'unknown',
                               'absence_duration_ns': now_ns - self.absences[port] if port in self.absences else None,
                               'previous_address': self.previous.get(port, {}).get('address')})
                self.transitions[port] = now_ns
            else:
                before = self.states[port]
                changed = sorted(key for key in set(before) | set(state) if before.get(key) != state.get(key))
                if changed:
                    events.append({'event': 'state_changed', 'port': port, 'changed': changed,
                                   'snapshot': state, 'same_physical_device_verified': False,
                                   'transition_duration_ns': now_ns - self.transitions[port],
                                   'previous_identity': {key: before[key] for key in ('vendor_id', 'product_id', 'address')},
                                   'presence_generation': self.generations[port], 'cause': 'unknown'})
                    self.transitions[port] = now_ns
            if port in self.errors:
                events.append({'event': 'diagnostics_recovered', 'port': port})
                self.errors.pop(port)
            self.states[port] = state
            self.seen.add(port)
        return events


def kernel_errors(text):
    """Extract only fixed error categories/codes; never emit raw kernel strings."""
    categories = {'device descriptor read': 'descriptor_error', 'device not accepting address': 'address_error',
                  'unable to enumerate': 'enumeration_error', 'over-current': 'over_current'}
    result = []
    for line in text.splitlines():
        if len(line) > 4096:
            continue
        lower = line.lower()
        kind = next((value for key, value in categories.items() if key in lower), None)
        if not kind or 'usb' not in lower:
            continue
        port = re.search(r'\busb\s+([0-9]+-[0-9.]+):', line)
        code = re.search(r'\berror\s+(-?[0-9]+)', lower)
        result.append({'event': 'kernel_enumeration_error', 'category': kind,
                       'port': port.group(1) if port else 'unknown',
                       'kernel_errno': int(code.group(1)) if code else None,
                       'record_key': hashlib.sha256(line.encode()).hexdigest()})
    return result


def observe(bin_dir, sysfs_root, duration, interval, port=None, probe=False,
            log_kernel=False, emit=None, stopped=None, database=None, stop_after_reconnect=False,
            probe_attempts=3, retry_delay=1, record_samples=False, annotations=None, session_id=None):
    database = database or load_database()
    emit = emit or (lambda event: print(json.dumps(event, separators=(',', ':')), flush=True))
    stopped = stopped or (lambda: False)
    observer = StateObserver()
    followed = {port} if port else set()
    totals = {'polls': 0, 'connected': 0, 'reconnected': 0, 'disconnected': 0,
              'errors': 0, 'probes_ok': 0, 'probes_failed': 0, 'discovery_successes': 0}
    origin = time.monotonic_ns()
    deadline = time.monotonic() + duration
    retry, attempts, needs_probe, seen_kernel = {}, {}, set(), set()
    reconnected_ports, completed_reconnect = set(), False
    sequence = 0
    snapshot_sequences = {}
    annotation_reader = None
    if annotations is not None:
        from .timeline import AnnotationReader
        annotation_reader = AnnotationReader(annotations, session_id)

    def publish(event):
        nonlocal sequence
        sequence += 1
        stamp = time.monotonic_ns()
        event = {**event, 'schema': 2, 'sequence': sequence, 'mono_ns': stamp, 'elapsed_ns': stamp - origin,
                 'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        emit(event)
        return sequence

    publish({'event': 'meta', 'observer_version': '1.2.0', 'database_version': database['version'],
             'passive': not probe, 'duration_seconds': duration, 'interval_seconds': interval,
             'serial_policy': 'not_read', 'kernel_errors_enabled': log_kernel,
             'probe_attempt_limit': probe_attempts, 'retry_delay_seconds': retry_delay,
             'cause_policy': 'unknown unless independently evidenced',
             'record_samples': record_samples, 'session_id': session_id})
    if log_kernel:
        try:
            initial = subprocess.run(['dmesg', '--raw'], capture_output=True, text=True, timeout=3)
            if initial.returncode:
                raise OSError('kernel log access unavailable')
            seen_kernel = {item['record_key'] for item in kernel_errors(initial.stdout)}
        except (OSError, subprocess.TimeoutExpired):
            publish({'event': 'facility_unavailable', 'facility': 'kernel_errors'})
            log_kernel = False
    while not stopped() and time.monotonic() < deadline:
        start = time.monotonic()
        sample_start = time.monotonic_ns()
        states, errors = {}, {}
        discovery_ok = True
        try:
            inventory = command_json([Path(bin_dir) / 'usb-discover', '--json'], min(3, max(0.01, deadline - time.monotonic())))
            if not isinstance(inventory.get('devices'), list):
                raise ObservationError('protocol', 'discovery', 'missing device list')
            for info in inventory['devices']:
                if not isinstance(info, dict):
                    raise ObservationError('protocol', 'discovery', 'invalid inventory entry')
                name = info.get('sysfs_name', '')
                if info.get('class') == 9:
                    continue
                if not port and info.get('vendor_id') == 0x05ac:
                    followed.add(name)
                if name not in followed:
                    continue
                try:
                    states[name] = read_snapshot(info, sysfs_root, database)
                except ObservationError as error:
                    errors[name] = error.record()
            totals['discovery_successes'] += 1
        except ObservationError as error:
            discovery_ok = False
            errors['*'] = error.record()
        totals['polls'] += 1
        sample_end = time.monotonic_ns()
        events = observer.update(states, errors, discovery_ok)
        for event in events:
            name = event.get('port')
            kind = event['event']
            if kind in totals:
                totals[kind] += 1
            if kind in ('device_error', 'discovery_error'):
                totals['errors'] += 1
            if kind == 'reconnected':
                reconnected_ports.add(name)
            if kind in ('connected', 'reconnected', 'state_changed', 'diagnostics_recovered'):
                needs_probe.add(name)
                attempts[name] = 0
                retry.pop(name, None)
            if kind == 'disconnected':
                needs_probe.discard(name)
                retry.pop(name, None)
                attempts.pop(name, None)
            published = publish(event)
            if 'snapshot' in event:
                snapshot_sequences[name] = published
        if record_samples:
            observed = {}
            for name in sorted(followed):
                if not discovery_ok or name in errors:
                    observed[name] = {'status': 'unknown'}
                elif name not in states:
                    observed[name] = {'status': 'absent'}
                else:
                    snapshot = states[name]
                    observed[name] = {'status': 'present', 'snapshot_sequence': snapshot_sequences[name],
                                      'presence_generation': observer.generations[name],
                                      **{key:snapshot[key] for key in ('vendor_id','product_id','address')}}
            publish({'event': 'sample', 'poll': totals['polls'], 'started_mono_ns': sample_start,
                     'completed_mono_ns': sample_end, 'discovery_ok': discovery_ok, 'ports': observed})
        if annotation_reader:
            for annotation in annotation_reader.read():
                publish(annotation)
        if probe:
            for name in sorted(needs_probe & set(states)):
                if attempts.get(name, 0) >= probe_attempts or time.monotonic() < retry.get(name, 0) or stopped() or time.monotonic() >= deadline:
                    continue
                snapshot = states[name]
                attempts[name] = attempts.get(name, 0) + 1
                probe_context = {'port': name, 'address': snapshot['address'], 'path': snapshot['path'],
                                 'attempt': attempts[name], 'presence_generation': observer.generations[name]}
                try:
                    inspection = command_json([Path(bin_dir) / 'usb-inspect', '--device', snapshot['path'], '--json'], min(15, max(0.01, deadline - time.monotonic())))
                    # New inspector guarantees default privacy. Reject older/raw output.
                    if inspection_errors(inspection):
                        raise ObservationError('protocol', 'privacy', 'inspector returned incomplete or unredacted characterization')
                    if any(inspection.get('device', {}).get(key) != snapshot[key] for key in ('vendor_id', 'product_id', 'address')):
                        raise ObservationError('again', 'snapshot', 'probe identity changed; rediscovery required')
                    totals['probes_ok'] += 1
                    publish({'event': 'descriptor_probe_ok', **probe_context, 'serial_policy': 'redacted'})
                    needs_probe.discard(name)
                except ObservationError as error:
                    totals['probes_failed'] += 1
                    publish({'event': 'descriptor_probe_error', **probe_context, 'error': error.record()})
                    retryable = error.status in ('timeout', 'no_device', 'io', 'protocol', 'again') and error.operation != 'privacy'
                    if retryable and attempts[name] < probe_attempts:
                        delay = min(30, retry_delay * 2 ** (attempts[name] - 1))
                        retry[name] = time.monotonic() + delay
                        publish({'event': 'probe_retry_scheduled', **probe_context, 'delay_seconds': delay})
                    else:
                        attempts[name] = probe_attempts
                        publish({'event': 'descriptor_probe_exhausted', **probe_context, 'retryable': retryable})
        if stop_after_reconnect and any(name in states and (not probe or name not in needs_probe) for name in reconnected_ports):
            completed_reconnect = True
            break
        if log_kernel and time.monotonic() < deadline:
            try:
                logs = subprocess.run(['dmesg', '--raw'], capture_output=True, text=True, timeout=min(3, max(0.01, deadline-time.monotonic())))
                if logs.returncode:
                    raise OSError('kernel log unavailable')
                for event in kernel_errors(logs.stdout):
                    if event['record_key'] not in seen_kernel:
                        publish(event)
                        seen_kernel.add(event['record_key'])
                if len(seen_kernel) > 4096:
                    publish({'event': 'facility_unavailable', 'facility': 'kernel_errors', 'reason': 'deduplication_limit'})
                    log_kernel = False
            except (OSError, subprocess.TimeoutExpired):
                publish({'event': 'facility_unavailable', 'facility': 'kernel_errors'})
                log_kernel = False
        # Short slices keep SIGINT/SIGTERM responsive without handlers doing I/O.
        wake = min(deadline, start + interval)
        while not stopped() and time.monotonic() < wake:
            time.sleep(min(0.1, max(0, wake - time.monotonic())))
    if annotation_reader:
        for annotation in annotation_reader.read(final=True):
            publish(annotation)
    pending = len(needs_probe) if probe else 0
    totals['probes_pending'] = pending
    totals['completion_status'] = 'complete' if totals['discovery_successes'] and not observer.discovery_error and not observer.errors and not pending else 'incomplete'
    publish({'event': 'summary', **totals, 'reason': 'reconnected' if completed_reconnect else 'signal' if stopped() else 'duration',
             'physical_identity_verification': False})
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin', type=Path, required=True)
    parser.add_argument('--sysfs-root', type=Path, default=Path('/sys/bus/usb/devices'))
    parser.add_argument('--duration', type=float, default=30)
    parser.add_argument('--interval', type=float, default=0.5)
    parser.add_argument('--port', help='Physical sysfs topology slot, e.g. 1-1; tracks VID changes there')
    parser.add_argument('--stop-after-reconnect', action='store_true', help='Stop once a reconnected slot and any requested probe recover')
    parser.add_argument('--probe-on-connect', action='store_true', help='Opt in to standard read-only SDK descriptor reads')
    parser.add_argument('--kernel-errors', action='store_true', help='Read available kernel log error codes, omitting raw messages')
    parser.add_argument('--probe-attempts', type=int, default=3, help='Maximum probe attempts per observed state (1..10)')
    parser.add_argument('--retry-delay', type=float, default=1, help='Initial bounded exponential retry delay (0.05..30 seconds)')
    parser.add_argument('--record-samples', action='store_true', help='Record each bounded cached-read window for transition timing')
    parser.add_argument('--annotations', type=Path, help='Session-scoped operator annotation input (no device actions)')
    parser.add_argument('--session-id', help='UUID matching the session annotation input')
    args = parser.parse_args()
    if not 0 < args.duration <= 3600 or not 0.05 <= args.interval <= 60 or args.duration / args.interval > 10000:
        parser.error('bounded duration 0..3600s, interval .05..60s and <=10000 samples required')
    if args.port and not re.fullmatch(r'\d+-\d+(?:\.\d+)*', args.port):
        parser.error('invalid non-hub sysfs port name')
    if not 1 <= args.probe_attempts <= 10 or not .05 <= args.retry_delay <= 30:
        parser.error('probe-attempts must be 1..10 and retry-delay .05..30')
    if args.annotations:
        import uuid
        try:uuid.UUID(args.session_id or '')
        except ValueError:parser.error('annotations require a valid session-id UUID')
    stop = [False]
    def mark_stop(_signal, _frame):
        stop[0] = True
    signal.signal(signal.SIGTERM, mark_stop)
    signal.signal(signal.SIGINT, mark_stop)
    result = observe(args.bin, args.sysfs_root, args.duration, args.interval, args.port,
            args.probe_on_connect, args.kernel_errors, stopped=lambda: stop[0], stop_after_reconnect=args.stop_after_reconnect,
            probe_attempts=args.probe_attempts, retry_delay=args.retry_delay,
            record_samples=args.record_samples, annotations=args.annotations, session_id=args.session_id)
    return 0 if result['completion_status'] == 'complete' else 1
