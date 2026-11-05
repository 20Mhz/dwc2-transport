#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
from dwc2_diag.privacy import public_errors


class PrivacyTests(unittest.TestCase):
    def test_private_paths_raw_traces_keys_and_serials_are_rejected(self):
        cases=[('file.txt','/Users/'+'privateperson/project'),('file.stdout','data'),
               ('file.json',json.dumps({'serial':'PRIVATE'})),
               ('file.txt','-----BEGIN '+'OPENSSH PRIVATE KEY-----'),
               ('file.txt','AKIA'+'A'*16),('file.json','{')]
        for name,value in cases:
            with self.subTest(name=name,value=value),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);(root/name).write_text(value)
                self.assertTrue(public_errors(root))

    def test_public_placeholders_and_redacted_descriptors_are_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'README.md').write_text('Use /home/USER/project; serial numbers are skipped.')
            (root/'state.json').write_text(json.dumps({'serial_policy':'not_read','serial_index':3}))
            self.assertEqual(public_errors(root),[])
            (root/'secret.txt').write_bytes(b'FORBIDDEN_TARGET_VALUE')
            self.assertTrue(public_errors(root,[b'FORBIDDEN_TARGET_VALUE']))


if __name__=='__main__':unittest.main()
