# SPDX-License-Identifier: MIT
"""Single-session correlation. Polling bounds are not electrical timestamps."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import time
import uuid

from .privacy import object_errors
from .recording import event_errors, provenance_errors, read_events
from .evidence import verify_manifest

ACTIONS = ('cable_disconnected', 'cable_reconnected', 'power_changed', 'manual_restart',
           'procedure_started', 'procedure_completed')


def annotation_valid(item, session_id):
    try:
        return (set(item) <= {'schema','session_id','action','report_mono_ns','report_time_utc','claimed_time_utc'}
                and item['schema'] == 1 and item['session_id'] == session_id
                and item['action'] in ACTIONS and type(item['report_mono_ns']) is int and item['report_mono_ns'] > 0
                and datetime.datetime.fromisoformat(item['report_time_utc']).utcoffset() == datetime.timedelta(0)
                and ('claimed_time_utc' not in item or datetime.datetime.fromisoformat(item['claimed_time_utc']).utcoffset() == datetime.timedelta(0)))
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


class AnnotationReader:
    def __init__(self, path, session_id):
        self.path, self.session_id = Path(path), session_id
        self.offset, self.pending, self.count, self.inode, self.disabled = 0, b'', 0, None, False

    def read(self, final=False):
        if self.disabled:
            return []
        try:
            stat = self.path.stat()
            if stat.st_size > 262144 or stat.st_size < self.offset or self.inode not in (None, (stat.st_dev, stat.st_ino)):
                raise ValueError('input limit or replacement')
            self.inode = stat.st_dev, stat.st_ino
            with self.path.open('rb') as stream:
                stream.seek(self.offset);data = stream.read(32768)
            self.offset += len(data);self.pending += data
            events = []
            while b'\n' in self.pending:
                line, self.pending = self.pending.split(b'\n', 1)
                self.count += 1
                if len(line) > 4096 or self.count > 256:
                    raise ValueError('annotation bounds')
                try:item = json.loads(line)
                except (ValueError, UnicodeDecodeError):item = None
                if not isinstance(item, dict) or not annotation_valid(item, self.session_id):
                    events.append({'event':'annotation_error','status':'invalid_or_wrong_session'})
                else:
                    events.append({'event':'operator_annotation','evidence_kind':'operator_statement',
                                   'independently_verified':False,'statement':item})
            if len(self.pending) > 4096 or final and (self.pending or self.offset != stat.st_size):
                raise ValueError('incomplete annotation input')
            return events
        except (OSError, ValueError):
            self.disabled = True
            return [{'event':'annotation_error','status':'input_unavailable_incomplete_or_limit'}]


def annotate_main():
    parser = argparse.ArgumentParser(description='Record an operator statement; never perform a device action')
    parser.add_argument('--session', type=Path, required=True, help='session.json written by the M8 collector')
    parser.add_argument('--action', choices=ACTIONS, required=True)
    parser.add_argument('--claimed-time-utc', help='Optional operator-claimed UTC time; not a hardware measurement')
    args = parser.parse_args()
    session = json.loads(args.session.read_text())
    uuid.UUID(session['session_id'])
    item = {'schema':1,'session_id':session['session_id'],'action':args.action,
            'report_mono_ns':time.monotonic_ns(),'report_time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    if args.claimed_time_utc:item['claimed_time_utc'] = args.claimed_time_utc
    if not annotation_valid(item, session['session_id']):parser.error('invalid operator timestamp')
    path = args.session.parent/'operator-input.jsonl'
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CLOEXEC)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        data = (json.dumps(item,separators=(',',':'))+'\n').encode()
        if os.write(descriptor,data) != len(data):raise OSError('incomplete annotation write')
        os.fsync(descriptor)
    finally:os.close(descriptor)
    print(json.dumps({'recorded':True,'evidence_kind':'operator_statement','action':args.action,
                      'time_accuracy':'report receipt; physical action time unmeasured'}))
    return 0


def sample_errors(rows):
    errors = event_errors(rows)
    if errors:return errors
    if object_errors(rows):return ['sensitive fields in session']
    samples, current, uncertain = [], {}, set()
    discovery_ok = True
    previous_end = -1
    try:
        session_id = rows[0]['session_id'];uuid.UUID(session_id)
        if rows[0].get('record_samples') is not True:errors.append('per-poll sampling was not enabled')
        for row in rows:
            kind, port = row['event'], row.get('port')
            if 'snapshot' in row:current[port] = row
            if kind == 'disconnected':current.pop(port,None);uncertain.discard(port)
            if kind == 'device_error':uncertain.add(port)
            if kind == 'diagnostics_recovered':uncertain.discard(port)
            if kind == 'discovery_error':discovery_ok = False
            if kind == 'discovery_recovered':discovery_ok = True
            if kind == 'annotation_error':errors.append('operator annotation input was incomplete or rejected')
            if kind == 'operator_annotation':
                if (row.get('evidence_kind') != 'operator_statement' or row.get('independently_verified') is not False
                        or not annotation_valid(row['statement'],session_id) or row['statement']['report_mono_ns'] > row['mono_ns']):
                    errors.append('invalid operator statement attribution')
            if kind != 'sample':continue
            samples.append(row)
            start,end = row['started_mono_ns'],row['completed_mono_ns']
            if (type(start) is not int or type(end) is not int or not previous_end <= start <= end <= row['mono_ns']
                    or type(row['poll']) is not int or row['poll'] != len(samples) or row['discovery_ok'] is not discovery_ok):
                errors.append('invalid or missing sample window')
            previous_end = end
            if not isinstance(row['ports'],dict) or not row['ports']:errors.append('missing sampled topology')
            for name,value in row['ports'].items():
                if not discovery_ok or name in uncertain:
                    if value['status'] != 'unknown':errors.append('failed reads misreported as presence or absence')
                elif name not in current:
                    if value['status'] != 'absent':errors.append('absence contradicts connection history')
                else:
                    snapshot = current[name]['snapshot']
                    expected = {'status':'present','snapshot_sequence':current[name]['sequence'],
                                'presence_generation':current[name]['presence_generation'],
                                **{key:snapshot[key] for key in ('vendor_id','product_id','address')}}
                    if value != expected:errors.append('sample contradicts its full snapshot')
        if len(samples) != rows[-1]['polls'] or not samples:errors.append('incomplete per-poll history')
    except (KeyError, TypeError, ValueError, AttributeError):
        errors.append('malformed sample or session identifier')
    return sorted(set(errors))


def analyze(rows):
    errors = sample_errors(rows)
    if errors:return {'schema':1,'valid':False,'errors':errors}
    snapshots = {row['sequence']:row['snapshot'] for row in rows if 'snapshot' in row}
    transitions, previous, gaps, identities, checkpoints, initial = [], {}, {}, set(), [], {}
    samples = [row for row in rows if row['event']=='sample']
    def window(row):
        return {key:row[key] for key in ('sequence','poll','started_mono_ns','completed_mono_ns','time_utc')}
    for sample in samples:
        for port,value in sorted(sample['ports'].items()):
            if value['status'] != 'present':
                if port in previous:gaps.setdefault(port,[]).append(sample)
                continue
            state = snapshots[value['snapshot_sequence']]
            identity = state['vendor_id'],state['product_id']
            identities.add(identity)
            initial.setdefault(port,{'port':port,'identity':{'vendor_id':state['vendor_id'],'product_id':state['product_id'],'address':state['address']},'sample':window(sample)})
            before = previous.get(port)
            if before:
                old_sample,old = before
                changed_identity = identity != (old['vendor_id'],old['product_id'])
                changes = {key:{'before':old.get(key),'after':state.get(key)} for key in
                           ('vendor_id','product_id','address','speed','active_configuration','driver_bindings','device_descriptor','configurations')
                           if old.get(key) != state.get(key)}
                absent = [row for row in gaps.get(port,[]) if row['ports'][port]['status']=='absent']
                if changed_identity or changes or absent:
                    transitions.append({'kind':'identity_change' if changed_identity else 'disconnect_reconnect_same_identity' if absent else 'state_change_without_observed_absence',
                        'port':port,'previous_identity':{'vendor_id':old['vendor_id'],'product_id':old['product_id'],'address':old['address']},
                        'new_identity':{'vendor_id':state['vendor_id'],'product_id':state['product_id'],'address':state['address']},
                        'last_confirmed_previous':window(old_sample),'first_observed_absence':window(absent[0]) if absent else None,
                        'first_confirmed_new':window(sample),'timing_bounds_mono_ns':[old_sample['started_mono_ns'],sample['completed_mono_ns']],
                        'uncertain_samples':len(gaps.get(port,[]))-len(absent),'descriptor_differences':changes,
                        'cause':'unknown','physical_identity_verified':False})
            previous[port] = sample,state
            gaps.pop(port,None)
    for port,(last,state) in sorted(previous.items()):
        checkpoints.append({'port':port,'last_confirmed_identity':{'vendor_id':state['vendor_id'],'product_id':state['product_id'],'address':state['address']},
                            'sample':window(last),'unresolved_gap_samples':len(gaps.get(port,[])),
                            'first_unresolved_absence':next((window(row) for row in gaps.get(port,[]) if row['ports'][port]['status']=='absent'),None)})
    origin = datetime.datetime.fromisoformat(rows[0]['time_utc'])
    wall_deviations = []
    for row in rows[1:]:
        elapsed = (datetime.datetime.fromisoformat(row['time_utc'])-origin).total_seconds()*1e9
        if abs(elapsed-(row['mono_ns']-rows[0]['mono_ns'])) > 1e9:wall_deviations.append(row['sequence'])
    captured = any(row['kind']=='identity_change' for row in transitions)
    return {'schema':1,'valid':True,'errors':[], 'session_id':rows[0]['session_id'],
            'outcome':'IDENTITY_CHANGE_OBSERVED' if captured else 'NO_IDENTITY_CHANGE_OBSERVED',
            'identity_change_captured':captured,'observed_identities':[{'vendor_id':v,'product_id':p} for v,p in sorted(identities)],
            'timeline':transitions,'initial_observations':list(initial.values()),'final_checkpoints':checkpoints,
            'operator_statements':[row for row in rows if row['event']=='operator_annotation'],
            'diagnostic_errors':[row for row in rows if row['event'] in ('device_error','discovery_error','descriptor_probe_error','kernel_enumeration_error')],
            'warnings':[row for row in rows if row['event']=='facility_unavailable'],
            'sampling':{'polls':len(samples),'nominal_interval_seconds':rows[0]['interval_seconds'],
                        'maximum_start_gap_ns':max((b['started_mono_ns']-a['started_mono_ns'] for a,b in zip(samples,samples[1:])),default=0)},
            'uncertainties':['Bounds span cached-read windows; electrical transition time is not measured.',
                             'Operator report receipt is not the measured physical action time.',
                             'Events within one sample cannot be totally ordered from polling.',
                             'Topology does not authenticate the physical unit.'],
            'wall_clock_deviation_sequences':wall_deviations}


def validate_session(root):
    root = Path(root)
    errors = verify_manifest(root)
    try:
        metadata = json.loads((root/'metadata.json').read_text());errors.extend(provenance_errors(metadata))
        flight = json.loads((root/'preflight.json').read_text())
        if (flight.get('status')!='PASS' or flight.get('cached_reads',0)<2 or flight.get('free_bytes',0)<128*1024*1024
                or flight.get('serial_policy')!='not_read' or flight.get('snapshot',{}).get('controller')!=metadata.get('controller')):
            errors.append('preflight does not support pass claim')
        session = json.loads((root/'session.json').read_text())
        if session.get('session_id')!=metadata.get('session_id') or session.get('annotation_file')!='operator-input.jsonl':
            errors.append('annotation session metadata mismatch')
        rows = read_events(root/'observer-0.jsonl');analysis = analyze(rows)
        parameters=metadata['parameters']
        if (parameters.get('test')!='M8' or parameters.get('record_samples') is not True
                or parameters.get('probe_on_connect') is not True
                or parameters.get('duration_seconds')!=rows[0].get('duration_seconds')
                or parameters.get('interval_seconds')!=rows[0].get('interval_seconds')
                or any(set(row['ports'])!={parameters.get('port')} for row in rows if row['event']=='sample')):
            errors.append('recorded parameters contradict the observation session')
        if not analysis['valid']:errors.extend(analysis['errors'])
        if json.loads((root/'timeline.json').read_text()) != analysis:errors.append('timeline contradicts continuous recording')
        result = json.loads((root/'result.json').read_text())
        if (result.get('milestone') != 'M8' or result.get('schema') != 1 or result.get('returncode') != 0
                or result.get('status') != 'PASS' or not analysis['valid']
                or result.get('identity_change_captured') != analysis.get('identity_change_captured')
                or result.get('outcome') != analysis.get('outcome') or result.get('children_reaped') is not True):
            errors.append('recording does not support completion claim')
        if result.get('procedure_status') not in ('PENDING_VERIFIED_PROCEDURE','VERIFIED_PROCEDURE_NOT_RUN'):
            errors.append('unsupported procedure claim')
        if result.get('procedure_status')!=parameters.get('procedure_status') or result.get('procedure_status')!=flight.get('procedure_status'):
            errors.append('inconsistent procedure status')
        if object_errors(metadata) or object_errors(result) or object_errors(flight) or object_errors(session):errors.append('sensitive session metadata')
        if metadata['session_id'] != rows[0]['session_id']:errors.append('session identifier mismatch')
        if not any(row['event']=='descriptor_probe_ok' for row in rows):errors.append('standard descriptor probe was not verified')
        if any(row['snapshot'].get('controller')!=metadata['controller'] for row in rows if 'snapshot' in row):errors.append('controller provenance mismatch')
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError):errors.append('missing or malformed M8 evidence')
    return sorted(set(errors))
