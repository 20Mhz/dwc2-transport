#!/usr/bin/env python3
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

build = Path(sys.argv[1]).resolve()
runner = shlex.split(os.environ.get('TEST_RUNNER', ''))
checks = 0


def run(tool, *args, expected=0):
    global checks
    result = subprocess.run([*runner, str(build / tool), *args], text=True, capture_output=True, timeout=20)
    assert result.returncode == expected, (args, result.returncode, result.stderr, result.stdout)
    checks += 1
    return result.stdout


listing = json.loads(run('usb-discover', '--mock', '--json'))
assert listing['schema'] == 1 and listing['devices'][0]['path'] == 'mock:1:2'
inspection = json.loads(run('usb-inspect', '--mock', '--json'))
assert inspection['device_descriptor']['configurations'] == 1
assert [d['endpoint'] for d in inspection['configurations'][0]['descriptors'] if d['type'] == 5] == [129, 1]
summary = json.loads(run('usb-diagnostics', '--mock', '--device', 'mock:1:2', '--repeat', '25', '--json'))
assert summary['transfers'] == {'requested': 25, 'ok': 25, 'errors': 0, 'timeouts': 0, 'cancelled': 0}
stream = [json.loads(x) for x in run('usb-diagnostics', '--mock', '--device', 'mock:1:2', '--repeat', '3', '--jsonl').splitlines()]
assert [r['status'] for r in stream if r['ev'] == 'xfer'] == ['ok'] * 3
assert not json.loads(run('usb-discover', '--mock', '--profile', 'apple-tv-a1427', '--json'))['devices']
error = json.loads(run('usb-inspect', '--mock', '--device', 'bad', '--json', expected=1))
assert error['error']['status'] == 'no_device'
for tool in ('usb-discover', 'usb-inspect', 'usb-diagnostics'):
    assert 'usage:' in run(tool, '--help')
    run(tool, '--repeat', '0', expected=2)
run('usb-diagnostics', '--mock', '--json', '--jsonl', expected=2)
assert 'SDK ' + run('usb-diagnostics', '--version').strip() in run('usb-diagnostics', '--mock')

# An explicit serial opt-in is required; shared indices are also redacted.
for case in ('default', 'alias', 'missing', 'include', 'timeout'):
    document = json.loads(run('test-inspection', case))
    serial = next(item for item in document['strings'] if item['index'] == 3)
    if case != 'include':
        assert serial == {'index': 3, 'roles_mask': 5 if case == 'alias' else 4,
                          'status': 'redacted', 'redacted': True}
        assert '53004500430052004500540034003200' not in json.dumps(document)
    else:
        assert serial['text'] == 'SECRET42'
    if case == 'missing':
        assert next(item for item in document['strings'] if item['index'] == 1)['status'] == 'stall'

broken = json.loads(run('test-inspection', 'malformed', expected=1))
assert broken['configurations'][0]['status'] == 'protocol'
assert 'descriptors' not in broken['configurations'][0]
slow = json.loads(run('test-inspection', 'timeout'))
assert next(item for item in slow['strings'] if item['index'] == 1)['status'] == 'timeout'

print(f'CLI: {checks} invocations PASS')
