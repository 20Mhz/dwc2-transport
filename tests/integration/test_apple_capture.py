#!/usr/bin/env python3
"""No-hardware checks for Apple capture gating and accurate pass/fail reporting."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('apple_capture', ROOT / 'scripts/pi/apple-tv-diagnostics.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
APPLE = {'path': '/dev/bus/usb/001/003', 'vendor_id': 0x05ac,
         'product_id': 0x1281, 'usb_mode': 'recovery'}


class CaptureTests(unittest.TestCase):
    def invoke(self, discoveries, bad_transfer=False):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        binaries = base / 'bin'
        binaries.mkdir()
        for name in ('usb-discover', 'usb-inspect', 'usb-diagnostics'):
            (binaries / name).write_bytes(b'fixture binary')
        (base / 'REVISION').write_text('test-source\n')
        commands = []
        inventory = iter(discoveries)

        def run(command, capture_output, timeout):
            self.assertTrue(capture_output)
            self.assertGreater(timeout, 0)
            commands.append(command)
            self.assertIn('--profile', command)
            self.assertEqual(command[command.index('--profile') + 1], 'apple-tv-a1427')
            tool = Path(command[0]).name
            if tool == 'usb-discover':
                document = {'devices': next(inventory)}
            elif tool == 'usb-inspect':
                document = {'device_descriptor': {'raw': '00' * 18},
                            'configurations': [{'status': 'ok'}]}
            elif tool == 'usb-diagnostics':
                count = int(command[command.index('--repeat') + 1])
                document = {'transfers': {'ok': count - int(bad_transfer),
                                          'errors': int(bad_transfer)}}
            else:
                self.fail(f'unexpected tool: {tool}')
            return subprocess.CompletedProcess(command, 0, json.dumps(document).encode(), b'')

        out = base / 'out'
        with patch.object(MODULE.subprocess, 'run', side_effect=run), contextlib.redirect_stdout(io.StringIO()):
            code = MODULE.capture(binaries, out)
        return code, json.loads((out / 'summary.json').read_text()), commands

    def test_absent_device_does_not_start_usb_transfers(self):
        code, summary, commands = self.invoke([[]])
        self.assertEqual(code, 2)
        self.assertEqual(summary['state'], 'unavailable')
        self.assertEqual(len(commands), 1)

    def test_multiple_devices_require_an_explicit_selection(self):
        code, summary, commands = self.invoke([[APPLE, {**APPLE, 'path': '/dev/bus/usb/001/004'}]])
        self.assertEqual(code, 2)
        self.assertEqual(summary['state'], 'needs_selection')
        self.assertEqual(len(commands), 1)

    def test_success_is_limited_to_observed_descriptor_checks(self):
        code, summary, commands = self.invoke([[APPLE], [APPLE]])
        self.assertEqual(code, 0)
        self.assertEqual(summary['state'], 'passed')
        self.assertFalse(summary['physical_model_verified'])
        self.assertFalse(summary['physical_reconnect_tested'])
        self.assertEqual(len(commands), 9)

    def test_transfer_errors_and_lost_devices_cannot_pass(self):
        code, summary, _ = self.invoke([[APPLE], []], bad_transfer=True)
        self.assertEqual(code, 1)
        self.assertEqual(summary['state'], 'failed')
        self.assertFalse(summary['detail']['diagnostics_ok'])
        self.assertFalse(summary['detail']['post_discovery_identity_match'])


class TraceValidationTests(unittest.TestCase):
    def test_missing_usbmon_is_not_a_trace_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / 'hostlab-session').mkdir()
            (out / 'hostlab-session/session.json').write_text(json.dumps(
                {'command_exit': 0, 'warnings': ['hostlab-mon exited early with 1']}))
            self.assertFalse(MODULE.verify_trace(out, 10))

    def test_success_requires_observed_transfers_and_no_drops(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            session = out / 'hostlab-session'
            session.mkdir()
            metadata = {'command_exit': 0, 'warnings': [], 'teardown': {'errors': []}}
            (session / 'session.json').write_text(json.dumps(metadata))
            analysis = {'consistency': {'ctrl_urbs_ok': 10, 'ctrl_urbs_phases_exact': 10},
                        'channel_events': {'ambiguous': 0, 'unattributed': 0}}
            (out / 'hostlab-analysis.json').write_text(json.dumps(analysis))
            records = [{'ev': 'xfer', 'status': 'ok', 'actual': 18}] * 10
            (session / 'user.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in records))
            stats = {'ev': 'stats', 'dropped': 0, 'queued': 0}
            (session / 'usbmon.jsonl').write_text(json.dumps(stats) + '\n')
            self.assertTrue(MODULE.verify_trace(out, 10))
            stats['dropped'] = 1
            (session / 'usbmon.jsonl').write_text(json.dumps(stats) + '\n')
            self.assertFalse(MODULE.verify_trace(out, 10))
            stats['dropped'] = 0
            (session / 'usbmon.jsonl').write_text(json.dumps(stats) + '\n')
            analysis['consistency']['ctrl_urbs_phases_exact'] = 9
            (out / 'hostlab-analysis.json').write_text(json.dumps(analysis))
            self.assertFalse(MODULE.verify_trace(out, 10))


if __name__ == '__main__':
    unittest.main()
