#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""M8: bounded, continuously sampled sessions; no automated physical actions."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
from dwc2_diag.evidence import write_manifest
from dwc2_diag.identification import load_database
from dwc2_diag.observer import ObservationError,command_json,read_snapshot
from dwc2_diag.privacy import public_errors
from dwc2_diag.recording import read_events
from dwc2_diag.timeline import analyze,validate_session


def markdown(analysis):
    lines=['# M8 single-session timeline','',f"Outcome: **{analysis.get('outcome','INVALID')}**",'',
           'Operator annotations are statements; polling windows are not electrical timestamps.','',
           '| Event | Port | Identity before → after | Conservative monotonic bounds (ns) |',
           '| --- | --- | --- | --- |']
    for row in analysis.get('timeline',[]):
        old,new=row['previous_identity'],row['new_identity']
        lines.append(f"| {row['kind']} | {row['port']} | {old['vendor_id']:04x}:{old['product_id']:04x} → {new['vendor_id']:04x}:{new['product_id']:04x} | {row['timing_bounds_mono_ns']} |")
    if not analysis.get('timeline'):lines.append('| No sampled transition | — | Stable identity or no confirmed change | See sample windows in timeline.json |')
    lines += ['','## Confirmed observations','','| Position | Port | VID:PID / address | Sample read window (monotonic ns) |',
              '| --- | --- | --- | --- |']
    for label,items in (('First',analysis.get('initial_observations',[])),('Last',analysis.get('final_checkpoints',[]))):
        for item in items:
            identity=item.get('identity',item.get('last_confirmed_identity'));window=item['sample']
            lines.append(f"| {label} | {item['port']} | {identity['vendor_id']:04x}:{identity['product_id']:04x} / {identity['address']} | [{window['started_mono_ns']}, {window['completed_mono_ns']}] |")
    lines += ['','## Uncertainties','']+[f'- {item}' for item in analysis.get('uncertainties',[])]
    lines += ['','## Operator statements','']
    for row in analysis.get('operator_statements',[]):
        statement=row['statement'];lines.append(f"- {statement['action']}: report received {statement['report_time_utc']}; physical action time unmeasured.")
    if not analysis.get('operator_statements'):lines.append('No operator statement was recorded.')
    return '\n'.join(lines)+'\n'


def preflight(args):
    available=shutil.disk_usage(args.out.parent).free
    if available < 128*1024*1024:raise ValueError('at least 128 MiB free evidence storage required')
    reads=[]
    for _ in range(2):
        inventory=command_json([args.bin/'usb-discover','--json'],3)
        selected=[item for item in inventory.get('devices',[]) if item.get('sysfs_name')==args.port]
        if len(selected)!=1:raise ValueError('exactly one current device at the selected topology slot is required')
        snapshot=read_snapshot(selected[0],Path('/sys/bus/usb/devices'),load_database())
        if snapshot['controller']!='dwc2':raise ValueError('physical Pi preflight requires the observed DWC2 controller')
        reads.append(snapshot);time.sleep(.1)
    if reads[0]!=reads[1]:raise ValueError('cached identity was not stable during preflight')
    return {'status':'PASS','free_bytes':available,'cached_reads':2,'snapshot':reads[-1],
            'serial_policy':'not_read','controller_verified':'dwc2','procedure_status':'PENDING_VERIFIED_PROCEDURE'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='operation',required=True)
    record=commands.add_parser('record')
    record.add_argument('--bin',type=Path,required=True);record.add_argument('--hostlab',type=Path,required=True)
    record.add_argument('--out',type=Path,required=True);record.add_argument('--port',default='1-1')
    record.add_argument('--duration',type=float,default=30);record.add_argument('--interval',type=float,default=.5)
    export=commands.add_parser('export');export.add_argument('--raw',type=Path,required=True);export.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.operation=='export':
        errors=validate_session(args.raw)
        if errors:raise ValueError('; '.join(errors))
        if args.out.resolve()==args.raw.resolve() or args.raw.resolve() in args.out.resolve().parents or args.out.resolve() in args.raw.resolve().parents:
            raise ValueError('raw and public session paths must not overlap')
        args.out.mkdir(parents=True,exist_ok=False)
        for name in ('metadata.json','preflight.json','session.json','observer-0.jsonl','timeline.json','timeline.md','result.json'):
            shutil.copy2(args.raw/name,args.out/name)
        references=[{'path':str(path.relative_to(args.raw)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
                    for path in sorted(args.raw.rglob('*')) if path.is_file()]
        (args.out/'raw-references.json').write_text(json.dumps({'storage':'local-only','files':references},indent=2)+'\n')
        write_manifest(args.out)
        errors=validate_session(args.out)+public_errors(args.out)
        print(json.dumps({'valid':not errors,'errors':errors}));return bool(errors)
    if not 0<args.duration<=3600 or not .05<=args.interval<=60 or args.duration/args.interval>10000:
        parser.error('bounded duration/interval with at most 10000 samples required')
    args.out.mkdir(parents=True,exist_ok=False)
    args.session_id=str(uuid.uuid4());args.test='M8';args.iterations=1
    args.probe_on_connect=True;args.record_samples=True;args.max_output_bytes=64*1024*1024
    session={'schema':1,'session_id':args.session_id,'annotation_file':'operator-input.jsonl'}
    (args.out/'session.json').write_text(json.dumps(session,indent=2)+'\n')
    (args.out/'operator-input.jsonl').touch(mode=0o600,exist_ok=False)
    spec=importlib.util.spec_from_file_location('m7_capture',Path(__file__).with_name('m7-validate.py'))
    capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
    collector_error=None
    try:
        flight=preflight(args)
        (args.out/'preflight.json').write_text(json.dumps(flight,indent=2)+'\n')
        metadata=capture.metadata(args);metadata['session_id']=args.session_id
        metadata['parameters'].update(record_samples=True,probe_on_connect=True,kernel_errors=True,
                                      session_id=args.session_id,max_output_bytes=args.max_output_bytes,
                                      procedure_status='PENDING_VERIFIED_PROCEDURE')
        metadata['application_sha256']['scripts/pi/m8-validate.py']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        (args.out/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
        code=capture.run_observer(args,0)
        analysis=analyze(read_events(args.out/'observer-0.jsonl'))
    except (ObservationError,OSError,ValueError,KeyError,TypeError) as error:
        code=1;analysis={'schema':1,'valid':False,'errors':['collector or preflight failed: '+type(error).__name__]}
        collector_error=error.record() if isinstance(error,ObservationError) else {'status':'collector_error','exception':type(error).__name__}
    (args.out/'timeline.json').write_text(json.dumps(analysis,indent=2)+'\n')
    (args.out/'timeline.md').write_text(markdown(analysis))
    result={'schema':1,'milestone':'M8','status':'PASS' if code==0 and analysis['valid'] else 'FAIL',
            'returncode':code,'identity_change_captured':analysis.get('identity_change_captured',False),
            'procedure_status':'PENDING_VERIFIED_PROCEDURE','children_reaped':True,
            'outcome':analysis.get('outcome','INVALID')}
    if collector_error is not None:result['collector_error']=collector_error
    (args.out/'result.json').write_text(json.dumps(result,indent=2)+'\n');write_manifest(args.out)
    errors=validate_session(args.out)
    print(json.dumps({'result':result,'validation_errors':errors},indent=2),flush=True)
    return bool(errors)


if __name__=='__main__':raise SystemExit(main())
