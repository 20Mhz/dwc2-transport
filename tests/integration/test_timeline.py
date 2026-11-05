#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Deterministic SIMULATION using two separate M7 snapshots, never transition evidence."""
import copy
import datetime
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
from dwc2_diag.observer import StateObserver,observe
from dwc2_diag.timeline import AnnotationReader,analyze,sample_errors,validate_session
from dwc2_diag.evidence import write_manifest
SESSION='00000000-0000-4000-8000-000000000001'


def snapshot(name):
    document=json.loads((ROOT/'tests/fixtures/m7-separate-state-snapshots.json').read_text())
    return copy.deepcopy(document['observations'][name]['snapshot'])


def fixture(steps):
    rows=[];watcher=StateObserver();refs={};origin=1_000_000_000
    def emit(event,stamp):
        wall=datetime.datetime(2026,11,4,tzinfo=datetime.timezone.utc)+datetime.timedelta(microseconds=(stamp-origin)/1000)
        rows.append({**event,'schema':2,'sequence':len(rows)+1,'mono_ns':stamp,'elapsed_ns':stamp-origin,'time_utc':wall.isoformat()})
        return len(rows)
    emit({'event':'meta','session_id':SESSION,'record_samples':True,'interval_seconds':1,
          'evidence_kind':'simulation','passive':True},origin)
    for poll,state in enumerate(steps,1):
        start=origin+poll*1_000_000_000;end=start+10000
        states={} if state in (None,'unknown') else {'1-1':state}
        errors={'1-1':{'status':'protocol','operation':'cached_descriptors'}} if state=='unknown' else {}
        for offset,event in enumerate(watcher.update(states,errors,now_ns=end),1):
            seq=emit(event,end+offset)
            if 'snapshot' in event:refs['1-1']=seq
        if state is None:value={'status':'absent'}
        elif state=='unknown':value={'status':'unknown'}
        else:value={'status':'present','snapshot_sequence':refs['1-1'],'presence_generation':watcher.generations['1-1'],
                    **{key:state[key] for key in ('vendor_id','product_id','address')}}
        emit({'event':'sample','poll':poll,'started_mono_ns':start,'completed_mono_ns':end,
              'discovery_ok':True,'ports':{'1-1':value}},end+100)
    kinds=[row['event'] for row in rows]
    emit({'event':'summary','polls':len(steps),'connected':kinds.count('connected'),'reconnected':kinds.count('reconnected'),
          'disconnected':kinds.count('disconnected'),'errors':kinds.count('device_error'),'probes_ok':0,'probes_failed':0,
          'completion_status':'complete','probes_pending':0,'reason':'duration'},end+1000)
    return rows


class TimelineTests(unittest.TestCase):
    def test_real_mock_loop_records_full_sampling_windows(self):
        import test_observer as fixtures
        with tempfile.TemporaryDirectory() as directory:
            root=fixtures.SnapshotTests().fixture(directory);rows=[]
            def command(command,timeout):
                return {'devices':[fixtures.INFO]} if str(command[0]).endswith('usb-discover') else fixtures.INSPECTION
            with patch('dwc2_diag.observer.command_json',side_effect=command):
                observe('/fake',root,.2,.05,probe=True,record_samples=True,session_id=SESSION,emit=rows.append)
            report=analyze(rows)
            self.assertTrue(report['valid'],report)
            self.assertEqual(report['outcome'],'NO_IDENTITY_CHANGE_OBSERVED')
            self.assertGreaterEqual(report['sampling']['polls'],3)

    def test_last_confirmed_identity_and_conservative_bounds(self):
        a,b=snapshot('A'),snapshot('B');rows=fixture([a,a,None,b,b]);report=analyze(rows)
        self.assertTrue(report['valid']);self.assertTrue(report['identity_change_captured'])
        event=report['timeline'][0]
        self.assertEqual(event['kind'],'identity_change')
        self.assertEqual(event['last_confirmed_previous']['poll'],2)
        self.assertEqual(event['first_observed_absence']['poll'],3)
        self.assertEqual(event['first_confirmed_new']['poll'],4)
        self.assertEqual(event['timing_bounds_mono_ns'],[3_000_000_000,5_000_010_000])
        self.assertIn('configurations',event['descriptor_differences'])
        self.assertFalse(event['physical_identity_verified'])

    def test_same_identity_reconnect_and_address_change_are_not_mode_transitions(self):
        a=snapshot('A');same=copy.deepcopy(a);same['address']+=1
        for steps,kind in (([a,None,a],'disconnect_reconnect_same_identity'),
                           ([a,same],'state_change_without_observed_absence')):
            report=analyze(fixture(steps));self.assertTrue(report['valid'])
            self.assertFalse(report['identity_change_captured']);self.assertEqual(report['timeline'][0]['kind'],kind)

    def test_unknown_samples_are_not_disconnects_and_stable_is_negative_result(self):
        a,b=snapshot('A'),snapshot('B')
        report=analyze(fixture([a,'unknown',b]));self.assertTrue(report['valid'])
        self.assertIsNone(report['timeline'][0]['first_observed_absence'])
        self.assertEqual(report['timeline'][0]['uncertain_samples'],1)
        stable=analyze(fixture([a,a,a]));self.assertEqual(stable['outcome'],'NO_IDENTITY_CHANGE_OBSERVED')
        self.assertFalse(stable['identity_change_captured'])
        last=analyze(fixture([a,None]));self.assertIsNotNone(last['final_checkpoints'][0]['first_unresolved_absence'])

    def test_missing_samples_stale_references_and_bad_windows_fail(self):
        original=fixture([snapshot('A'),snapshot('B')])
        for mutate in (lambda r:r.pop(2),
                       lambda r:next(x for x in r if x['event']=='sample')['ports']['1-1'].update(snapshot_sequence=999),
                       lambda r:next(x for x in r if x['event']=='sample').update(started_mono_ns=10**20),
                       lambda r:r[-1].update(polls=999),
                       lambda r:next(x for x in r if x['event']=='sample').update(discovery_ok=False)):
            rows=copy.deepcopy(original);mutate(rows);self.assertTrue(sample_errors(rows))
        self.assertTrue(sample_errors(original[:-1]))

    def test_operator_reports_are_session_scoped_and_partial_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'session.json').write_text(json.dumps({'schema':1,'session_id':SESSION}))
            path=root/'operator-input.jsonl';path.touch()
            process=subprocess.run([sys.executable,str(ROOT/'tools/usb-annotate'),'--session',str(root/'session.json'),
                                    '--action','power_changed'],capture_output=True,text=True,timeout=3)
            self.assertEqual(process.returncode,0)
            reader=AnnotationReader(path,SESSION);events=reader.read()
            self.assertEqual(events[0]['evidence_kind'],'operator_statement')
            self.assertFalse(events[0]['independently_verified'])
            wrong=AnnotationReader(path,'00000000-0000-4000-8000-000000000002')
            self.assertEqual(wrong.read()[0]['event'],'annotation_error')
            with path.open('ab') as stream:stream.write(b'{')
            self.assertEqual(reader.read(final=True)[0]['event'],'annotation_error')

    def test_separate_sessions_and_incomplete_evidence_cannot_be_joined(self):
        a=fixture([snapshot('A')]);b=fixture([snapshot('B')]);self.assertTrue(sample_errors(a+b))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'observer-0.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in a))
            (root/'timeline.json').write_text(json.dumps({'identity_change_captured':True}));write_manifest(root)
            self.assertTrue(validate_session(root))

    def test_complete_session_verifier_recomputes_timeline_and_checks_session_scope(self):
        import test_observer as fixtures
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);sysfs=root/'sysfs';sysfs.mkdir()
            fixtures.SnapshotTests().fixture(sysfs);rows=[]
            def command(command,timeout):
                return {'devices':[fixtures.INFO]} if str(command[0]).endswith('usb-discover') else fixtures.INSPECTION
            with patch('dwc2_diag.observer.command_json',side_effect=command):
                observe('/fake',sysfs,.15,.05,probe=True,record_samples=True,session_id=SESSION,emit=rows.append)
            public=root/'record';public.mkdir();analysis=analyze(rows)
            meta={'sdk_revision':'a'*40,'application_revision':'b'*40,'hostlab_revision':'c'*40,
                  'kernel':'fixture','host_model':'fixture','hardware_revision':'fixture','controller':'dwc2',
                  'parameters':{'test':'M8','duration_seconds':.15,'interval_seconds':.05,'record_samples':True,
                                'probe_on_connect':True,'port':'1-1','procedure_status':'PENDING_VERIFIED_PROCEDURE'},
                  'binary_sha256':{'fixture':'d'*64},'application_sha256':{'fixture':'e'*64},
                  'evidence_kind':'physical_observation','session_id':SESSION}
            # The temporary provenance shape is synthetic; no files from this test are physical evidence.
            docs={'metadata.json':meta,'session.json':{'session_id':SESSION,'annotation_file':'operator-input.jsonl'},
                  'preflight.json':{'status':'PASS','cached_reads':2,'free_bytes':256*1024*1024,'serial_policy':'not_read','snapshot':{'controller':'dwc2'},'procedure_status':'PENDING_VERIFIED_PROCEDURE'},
                  'timeline.json':analysis,'result.json':{'schema':1,'milestone':'M8','status':'PASS','returncode':0,
                      'children_reaped':True,'identity_change_captured':False,'outcome':'NO_IDENTITY_CHANGE_OBSERVED','procedure_status':'PENDING_VERIFIED_PROCEDURE'}}
            for name,value in docs.items():(public/name).write_text(json.dumps(value))
            (public/'observer-0.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows));write_manifest(public)
            self.assertEqual(validate_session(public),[])
            meta['parameters']['interval_seconds']=1
            (public/'metadata.json').write_text(json.dumps(meta));write_manifest(public)
            self.assertIn('recorded parameters contradict the observation session',validate_session(public))
            meta['parameters']['interval_seconds']=.05;(public/'metadata.json').write_text(json.dumps(meta))
            analysis['identity_change_captured']=True;(public/'timeline.json').write_text(json.dumps(analysis));write_manifest(public)
            self.assertIn('timeline contradicts continuous recording',validate_session(public))

    def test_preflight_disappearance_is_a_structured_failed_recording(self):
        from dwc2_diag.observer import ObservationError
        spec=importlib.util.spec_from_file_location('m8_test_capture',ROOT/'scripts/pi/m8-validate.py')
        capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'raw'
            with patch.object(sys,'argv',['m8','record','--bin','/fake','--hostlab','/fake','--out',str(output)]), \
                 patch.object(capture,'preflight',side_effect=ObservationError('no_device','sysfs','disappeared',19)), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(capture.main(),1)
            result=json.loads((output/'result.json').read_text())
            self.assertEqual(result['status'],'FAIL')
            self.assertEqual(result['collector_error']['system_errno'],19)
            self.assertTrue(validate_session(output))


if __name__=='__main__':unittest.main()
