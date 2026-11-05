#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
from dwc2_diag.evidence import (create_bundle, privacy_errors, redact_inspection,
                                trace_report, validate_bundle, verify_manifest, write_manifest)
from dwc2_diag.identification import load_database
DEVICE='1201000200000040ac05a712100301020301'
CONFIG='09022000010105c0010904000002fffe02060705020200020007058102000200'


def inspection():
    return {'device':{'vendor_id':1452,'product_id':4775},'device_descriptor':{'raw':DEVICE,'serial_index':3},
            'configurations':[{'status':'ok','raw':CONFIG}],
            'strings':[{'index':1,'text':'Apple Inc.'},{'index':3,'text':'UNIQUE_SECRET','raw':'deadbeef'}]}


class EvidenceTests(unittest.TestCase):
    def test_redaction_removes_plain_and_hex_serial_and_shared_roles(self):
        source=inspection();redacted=redact_inspection(source)
        self.assertNotIn('UNIQUE_SECRET',json.dumps(redacted))
        self.assertNotIn('deadbeef',json.dumps(redacted))
        self.assertEqual(source['strings'][1]['text'],'UNIQUE_SECRET')
        self.assertEqual(privacy_errors(redacted),[])
        self.assertTrue(privacy_errors(source))
        redacted['strings'][1]['raw']='deadbeef'
        self.assertTrue(privacy_errors(redacted))

    def test_empty_and_incomplete_trace_data_never_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.assertFalse(trace_report(root)['passed'])
            (root/'hostlab-session').mkdir()
            for name,data in [('hostlab-session/session.json','{}'),('hostlab-analysis.json','null'),
                              ('hostlab-session/usbmon.jsonl','[]\n'),('hostlab-session/user.jsonl','')]:
                (root/name).write_text(data)
            self.assertFalse(trace_report(root)['passed'])

    def fixture(self, root):
        raw=root/'raw';raw.mkdir();(raw/'hostlab-session').mkdir()
        docs={'metadata.json':{'sdk_revision':'a'*40,'kernel':'6.12.47+rpt-rpi-v6'},
              'summary.json':{'state':'passed'},'inspection.stdout':inspection(),
              'diagnostics.stdout':{'transfers':{'ok':25,'errors':0}},
              'hostlab-session/session.json':{'command_exit':0,'warnings':[],'teardown':{'errors':[]}},
              'hostlab-analysis.json':{'consistency':{'ctrl_urbs_ok':10,'ctrl_urbs_phases_exact':10},
                                       'channel_events':{'total':30,'unattributed':0,'ambiguous':0}}}
        for name,data in docs.items():(raw/name).write_text(json.dumps(data))
        (raw/'hostlab-session/usbmon.jsonl').write_text(json.dumps({'ev':'stats','queued':0,'dropped':0})+'\n')
        (raw/'hostlab-session/user.jsonl').write_text(''.join(json.dumps({'ev':'xfer','status':'ok','actual':18})+'\n' for _ in range(10)))
        observer=root/'observer.jsonl';observer.write_text(json.dumps({'event':'summary','polls':5})+'\n')
        write_manifest(raw)
        return raw,observer

    def test_bundle_integrity_redaction_and_semantic_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);raw,observer=self.fixture(root);out=root/'public'
            result=create_bundle(raw,out,load_database(),[observer],{'returncode':0,'summary':{'reason':'signal'}})
            self.assertTrue(result['passed'])
            self.assertEqual(validate_bundle(out),[])
            self.assertFalse((out/'hostlab-session').exists())
            self.assertNotIn('UNIQUE_SECRET',''.join(path.read_text() for path in out.iterdir() if path.is_file()))
            (out/'inspection.json').write_text('{}')
            self.assertTrue(verify_manifest(out))
            write_manifest(out)
            self.assertTrue(validate_bundle(out))

    def test_manifest_rejects_traversal_duplicates_and_extra_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);out=root/'bundle';out.mkdir();(out/'one').write_text('one')
            write_manifest(out);self.assertEqual(verify_manifest(out),[])
            original=(out/'SHA256SUMS').read_text()
            (out/'extra').write_text('extra');self.assertTrue(verify_manifest(out));(out/'extra').unlink()
            (out/'SHA256SUMS').write_text(original+original);self.assertTrue(verify_manifest(out))
            (out/'SHA256SUMS').write_text('0'*64+'  ../outside\n');self.assertTrue(verify_manifest(out))
            (out/'SHA256SUMS').write_text('');self.assertTrue(verify_manifest(out))

    def test_outer_manifest_covers_nested_manifests(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);nested=root/'nested';nested.mkdir()
            (nested/'data').write_text('payload');write_manifest(nested);write_manifest(root)
            self.assertEqual(verify_manifest(root),[])
            (nested/'SHA256SUMS').write_text('tampered')
            self.assertTrue(verify_manifest(root))

    def test_false_pass_claim_or_raw_overlap_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);raw,observer=self.fixture(root)
            with self.assertRaises(ValueError):create_bundle(raw,raw/'public',load_database(),[observer])
            out=root/'public';create_bundle(raw,out,load_database(),[observer])
            (out/'diagnostics.json').write_text(json.dumps({'transfers':{'ok':24,'errors':1}}))
            write_manifest(out);self.assertTrue(validate_bundle(out))

    def test_raw_integrity_and_reconnect_claims_are_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);raw,observer=self.fixture(root)
            (raw/'unexpected').write_text('unlisted')
            with self.assertRaises(ValueError):create_bundle(raw,root/'bad',load_database(),[observer])
            (raw/'unexpected').unlink()
            out=root/'public';create_bundle(raw,out,load_database(),[observer])
            result=json.loads((out/'result.json').read_text());result['physical_reconnect_observed']=True
            (out/'result.json').write_text(json.dumps(result));write_manifest(out)
            self.assertIn('observer records do not support reconnect claims',validate_bundle(out))
            result['physical_reconnect_observed']=False
            (out/'result.json').write_text(json.dumps(result))
            (out/'observer-0.jsonl').write_text('{}\n');write_manifest(out)
            self.assertIn('observer records do not support reported results',validate_bundle(out))


if __name__=='__main__':unittest.main()
