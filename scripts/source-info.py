#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Provenance for a Git checkout or a checksum-verified source export."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def source_info(root):
    root=Path(root)
    if (root/'.git').exists():
        return {'revision':subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),
                'epoch':int(subprocess.check_output(['git','-C',str(root),'show','-s','--format=%ct','HEAD'],text=True)),
                'files':subprocess.check_output(['git','-C',str(root),'ls-files','-z']).decode().strip('\0').split('\0')}
    value=json.loads((root/'SOURCE_INFO.json').read_text())
    for name,digest in value['sha256'].items():
        path=root/name
        if path.resolve().is_relative_to(root.resolve()) is False or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('source export checksum mismatch: '+name)
    return {'revision':value['revision'],'epoch':value['epoch'],'files':list(value['sha256'])}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--field',choices=('revision','epoch','json'),default='json')
    args=parser.parse_args();value=source_info(args.root)
    print(json.dumps(value) if args.field=='json' else value[args.field])


if __name__=='__main__':main()
