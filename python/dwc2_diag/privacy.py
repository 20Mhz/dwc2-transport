# SPDX-License-Identifier: MIT
"""Conservative public-artifact checks. No raw identifiers are printed."""
import json
from pathlib import Path
import re
from .evidence import privacy_errors


def object_errors(value):
    errors = []
    if isinstance(value, dict):
        if any(key.lower() in ('serial', 'serial_number', 'serialnumber', 'ecid', 'udid', 'password', 'private_key', 'access_token') for key in value):
            errors.append('sensitive identity or credential field')
        if 'device_descriptor' in value and 'strings' in value:
            errors.extend(privacy_errors(value))
        for child in value.values():
            errors.extend(object_errors(child))
    elif isinstance(value, list):
        for child in value:
            errors.extend(object_errors(child))
    return errors


def public_errors(root, forbidden=()):
    root = Path(root)
    errors = []
    patterns = [rb'-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----',
                rb'AKIA[0-9A-Z]{16}', rb'gh[pousr]_[A-Za-z0-9]{30,}']
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            errors.append(name + ': symlink is not a public regular file')
            continue
        if not path.is_file():
            continue
        if any(part in ('.git', '.ssh', '.aws', '.env', '.local-evidence') for part in path.parts) or path.suffix in ('.stdout', '.stderr', '.pem', '.key', '.pcap', '.pcapng'):
            errors.append(name + ': private/raw file type')
        data = path.read_bytes()
        if any(re.search(pattern, data) for pattern in patterns) or any(secret and secret in data for secret in forbidden):
            errors.append(name + ': sensitive content pattern')
        for match in re.finditer(rb'/(?:Users|home)/([^/\s"\'<>\\]+)', data):
            if match.group(1) not in (b'USER', b'USERNAME'):
                errors.append(name + ': unnecessary private home path')
                break
        if path.suffix in ('.json', '.jsonl'):
            try:
                values = [json.loads(line) for line in data.decode().splitlines()] if path.suffix == '.jsonl' else [json.loads(data)]
                if any(object_errors(value) for value in values):
                    errors.append(name + ': unredacted structured data')
            except (ValueError, UnicodeDecodeError):
                errors.append(name + ': malformed public JSON')
    return errors
