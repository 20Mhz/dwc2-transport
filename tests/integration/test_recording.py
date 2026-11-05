#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Simulated recordings exercise validation; these are not hardware evidence."""
import copy
import contextlib
import importlib.util
import io
import json
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
from dwc2_diag.observer import observe
from dwc2_diag.recording import (create_release_evidence, event_errors, recording_errors,
                                 test_outcome, validate_release_evidence)
from dwc2_diag.evidence import write_manifest
import test_observer as fixtures


class RecordingTests(unittest.TestCase):
    def events(self, root, reconnect=False):
        fixture=fixtures.SnapshotTests().fixture(root);rows=[]
        polls=[0]
        def command(command, timeout):
            if str(command[0]).endswith('usb-discover'):
                polls[0]+=1
                if reconnect and polls[0]==2:return {'devices':[]}
                return {'devices':[fixtures.INFO]}
            return fixtures.INSPECTION
        with patch('dwc2_diag.observer.command_json',side_effect=command), \
                patch('dwc2_diag.observer.time',fixtures.SimulatedClock()):
            observe('/fake',fixture,.16,.05,probe=True,emit=rows.append,stop_after_reconnect=reconnect)
        return rows

    def test_ordering_completion_and_counts_are_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            rows=self.events(directory)
            self.assertEqual(event_errors(rows),[])
            self.assertEqual(test_outcome('D1',rows,0)['status'],'PASS')
            self.assertTrue(event_errors(rows[:-1]))
            for mutate in (lambda r:r[1].update(sequence=9),lambda r:r[-1].update(probes_ok=9),
                           lambda r:r[-1].update(completion_status='incomplete'),
                           lambda r:r[1]['snapshot'].update(serial='PRIVATE'),
                           lambda r:r[1].update(presence_generation=2)):
                changed=copy.deepcopy(rows);mutate(changed);self.assertTrue(event_errors(changed))
            self.assertEqual(test_outcome('D2',rows,0)['status'],'FAIL')
            self.assertEqual(test_outcome('D1',rows,1)['status'],'FAIL')

    def test_pending_hardware_cannot_be_promoted_to_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'public'
            result=create_release_evidence(root,[],'Pi unreachable; operator action pending')
            self.assertFalse(result['physical_validation_complete'])
            self.assertEqual(validate_release_evidence(root),[])
            result['physical_validation_complete']=True
            (root/'result.json').write_text(json.dumps(result));write_manifest(root)
            self.assertIn('overstated physical completion',validate_release_evidence(root))

    def test_verifier_cli_returns_json_failure_for_malformed_test_map(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'public';result=create_release_evidence(root,[],'operator pending')
            result['tests']=[];(root/'result.json').write_text(json.dumps(result));write_manifest(root)
            process=subprocess.run([sys.executable,str(ROOT/'tools/usb-evidence-verify'),str(root)],capture_output=True,text=True,timeout=3)
            self.assertEqual(process.returncode,1)
            self.assertFalse(json.loads(process.stdout)['valid'])
            self.assertEqual(process.stderr,'')

    def test_operator_reboot_prevents_cable_only_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);fixture=root/'sysfs';fixture.mkdir();rows=self.events(fixture,reconnect=True)
            raw=root/'raw';raw.mkdir()
            metadata={'sdk_revision':'a'*40,'application_revision':'b'*40,'hostlab_revision':'c'*40,
                      'kernel':'test','host_model':'test','hardware_revision':'test','controller':'dwc2',
                      'parameters':{'test':'D2'},'binary_sha256':{'test':'d'*64},'application_sha256':{'test':'e'*64},
                      'evidence_kind':'physical_observation'}
            result={'schema':1,'test':'D2','returncodes':[0],'runs':[test_outcome('D2',rows,0)],'status':'PASS'}
            (raw/'metadata.json').write_text(json.dumps(metadata));(raw/'result.json').write_text(json.dumps(result))
            (raw/'observer-0.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows));write_manifest(raw)
            context={'D2':{'source':'operator_report','cable_reconnected':True,'power_maintained':None,'reboot_reported':True}}
            out=root/'public';report=create_release_evidence(out,[raw],'not run',context)
            self.assertEqual(report['tests']['D2']['status'],'INCONCLUSIVE_OPERATOR_REBOOT')
            self.assertEqual(validate_release_evidence(out),[])
            report['tests']['D2']['status']='PASS'
            (out/'result.json').write_text(json.dumps(report));write_manifest(out)
            self.assertIn('cable-only conditions were not confirmed',validate_release_evidence(out))
            context['D2'].update(power_maintained=True,reboot_reported=False)
            (out/'operator-context.json').write_text(json.dumps(context));write_manifest(out)
            self.assertEqual(validate_release_evidence(out),[])

    def test_recording_provenance_and_public_export_omit_stderr(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);fixture=root/'sysfs';fixture.mkdir();rows=self.events(fixture)
            raw=root/'raw';raw.mkdir()
            metadata={'sdk_revision':'a'*40,'application_revision':'b'*40,'hostlab_revision':'c'*40,
                      'kernel':'test','host_model':'test','hardware_revision':'test','controller':'dwc2',
                      'parameters':{'test':'D1'},'binary_sha256':{'test':'d'*64},'application_sha256':{'test':'e'*64},
                      'evidence_kind':'physical_observation'}
            result={'schema':1,'test':'D1','returncodes':[0],'runs':[test_outcome('D1',rows,0)],'status':'PASS'}
            (raw/'metadata.json').write_text(json.dumps(metadata));(raw/'result.json').write_text(json.dumps(result))
            (raw/'observer-0.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
            (raw/'observer-0.stderr').write_text('PRIVATE RAW ERROR');write_manifest(raw)
            self.assertEqual(recording_errors(raw),[])
            out=root/'public';create_release_evidence(out,[raw],'not run')
            self.assertEqual(validate_release_evidence(out),[])
            self.assertFalse((out/'D1/observer-0.stderr').exists())
            metadata['hostlab_revision']='unknown';(raw/'metadata.json').write_text(json.dumps(metadata));write_manifest(raw)
            self.assertTrue(recording_errors(raw))

    def collector(self):
        spec=importlib.util.spec_from_file_location('m7_collector',ROOT/'scripts/pi/m7-validate.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_installed_hostlab_provenance_does_not_require_git(self):
        module=self.collector()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);binary=root/'bin';binary.mkdir();hostlab=root/'hostlab';(hostlab/'bin').mkdir(parents=True)
            for name in ('usb-discover','usb-inspect'):(binary/name).write_bytes(b'fixture')
            for name in ('hostlab-session','hostlab-analyze'):(hostlab/'bin'/name).write_bytes(b'fixture')
            (root/'REVISION').write_text('a'*40);(root/'APPLICATION_REVISION').write_text('b'*40)
            (hostlab/'REVISION').write_text('c'*40)
            args=SimpleNamespace(bin=binary,hostlab=hostlab,test='D1',duration=8,interval=.5,iterations=3,port='1-1')
            original=Path.read_text
            def read(path,*args,**kwargs):
                return 'Revision : 9000c1\nSerial : PRIVATE\n' if str(path)=='/proc/cpuinfo' else original(path,*args,**kwargs)
            with patch.object(Path,'read_text',read),patch.object(module.subprocess,'run',side_effect=AssertionError('Git must not run')):
                value=module.metadata(args)
            self.assertEqual(value['hostlab_revision'],'c'*40)
            self.assertEqual(value['hardware_revision'],'9000c1')
            self.assertNotIn('PRIVATE',json.dumps(value))

    def test_collector_reaps_its_independent_observer_after_sigterm(self):
        module=self.collector()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);binary=root/'bin';binary.mkdir();out=root/'out';out.mkdir()
            (binary/'usb-observe').write_text('import signal,json,time,sys\n'
                'stopped=[False]\n'
                'def stop(a,b):\n stopped[0]=True\n'
                'signal.signal(signal.SIGTERM,stop)\n'
                'print(json.dumps({"event":"connected","snapshot":{"address":3}}),flush=True)\n'
                'while not stopped[0]: time.sleep(.05)\n'
                'print(json.dumps({"event":"summary","reason":"signal"}),flush=True)\n')
            args=SimpleNamespace(bin=binary,out=out,test='D4',port='1-1',duration=1,interval=.05)
            with contextlib.redirect_stdout(io.StringIO()):code=module.run_observer(args,0)
            self.assertEqual(code,0)
            rows=[json.loads(line) for line in (out/'observer-0.jsonl').read_text().splitlines()]
            self.assertEqual(rows[-1]['reason'],'signal')


if __name__=='__main__':unittest.main()
