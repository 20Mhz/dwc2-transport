#!/usr/bin/env python3
"""Extract bounded conventional descriptor reads from a HostLab user.jsonl.
Only successful standard device/config descriptor reads, no device identifiers
from strings or endpoint payloads. Output is deterministic text replay v1.
"""
import argparse
import json
from pathlib import Path


def extract(source, limit):
    rows = []
    for line in source.read_text().splitlines():
        record = json.loads(line)
        if record.get('ev') != 'xfer' or record.get('status') != 'ok':
            continue
        setup = bytes.fromhex(record.get('setup', ''))
        if len(setup) != 8 or setup[:2] != b'\x80\x06' or setup[3] not in (1, 2):
            continue
        data = bytes.fromhex(record.get('data', ''))
        if len(data) > 4096 or len(data) != record.get('actual'):
            continue
        start = record.get('t_submit_ns')
        end = record.get('t_done_ns', record.get('t_reap_ns'))
        if not isinstance(start, int) or not isinstance(end, int) or end < start:
            continue
        rows.append(f'{setup.hex()} 0 {end-start} {data.hex() or "-"}')
        if len(rows) == limit:
            break
    if not rows:
        raise ValueError('no suitable conventional descriptor records')
    return 'DWC2_REPLAY 1\n' + '\n'.join(rows) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--limit', type=int, default=8, choices=range(1, 129))
    args = parser.parse_args()
    args.output.write_text(extract(args.source, args.limit))


if __name__ == '__main__':
    main()
