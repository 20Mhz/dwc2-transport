#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


class ReleaseTests(unittest.TestCase):
    def test_source_export_uses_its_manifest_and_rejects_modified_source(self):
        source=module('release_source_info','scripts/source-info.py')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'file.c').write_text('source')
            (root/'SOURCE_INFO.json').write_text(json.dumps({'revision':'a'*40,'epoch':1234567890,
                'sha256':{'file.c':hashlib.sha256(b'source').hexdigest()}}))
            with patch.object(source.subprocess,'check_output',side_effect=AssertionError('parent Git must not be used')):
                self.assertEqual(source.source_info(root)['revision'],'a'*40)
            (root/'file.c').write_text('changed')
            with self.assertRaises(ValueError):source.source_info(root)

    def test_archive_bytes_do_not_depend_on_file_mtime_or_owner_metadata(self):
        release=module('release_packaging','scripts/package-release.py')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);stage=root/'source';stage.mkdir();(stage/'file').write_text('payload')
            release.archive_tree(stage,root/'one.tar.gz',1234567890)
            self.assertEqual((root/'one.tar.gz.sha256').read_text(),
                hashlib.sha256((root/'one.tar.gz').read_bytes()).hexdigest()+'  one.tar.gz\n')
            import os
            os.utime(stage/'file',(1,2))
            release.archive_tree(stage,root/'two.tar.gz',1234567890)
            self.assertEqual((root/'one.tar.gz').read_bytes(),(root/'two.tar.gz').read_bytes())


if __name__=='__main__':unittest.main()
