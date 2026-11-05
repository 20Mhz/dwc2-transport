#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bounded M6 validation. Raw evidence is local; exported bundles are redacted."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
from dwc2_diag.evidence import create_bundle, validate_bundle, write_manifest
from dwc2_diag.identification import load_database


def terminate_observer(command, output):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    data = bytearray(); ready = False
    deadline = time.monotonic() + 10
    try:
        while process.poll() is None and time.monotonic() < deadline:
            for key, _ in selector.select(0.1):
                chunk = os.read(key.fd,65536)
                data.extend(chunk)
                if b'"event":"connected"' in data:
                    ready = True
                    break
            if ready:
                process.send_signal(signal.SIGTERM)
                break
        if not ready and process.poll() is None:
            process.kill()
        tail, error = process.communicate(timeout=5)
        data.extend(tail)
    except subprocess.TimeoutExpired:
        process.kill();tail,error = process.communicate();data.extend(tail)
    finally:
        selector.close()
        if process.poll() is None:
            process.kill();process.wait()
    output.write_bytes(data)
    output.with_suffix('.stderr').write_bytes(error)
    rows=[json.loads(line) for line in data.decode().splitlines() if line]
    summaries=[row for row in rows if row.get('event')=='summary']
    return {'returncode':process.returncode,'ready_before_signal':ready,
            'summary':summaries[-1] if summaries else {}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin',type=Path,required=True)
    parser.add_argument('--raw-out',type=Path,required=True)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--port',default='1-1')
    parser.add_argument('--hostlab',type=Path,required=True)
    parser.add_argument('--observer-log',type=Path,action='append',default=[])
    args=parser.parse_args()
    spec=importlib.util.spec_from_file_location('apple_capture',Path(__file__).with_name('apple-tv-diagnostics.py'))
    capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
    status=capture.capture(args.bin,args.raw_out,hostlab=args.hostlab)
    if status:
        print(json.dumps({'state':'failed','operation':'capture','raw_evidence':str(args.raw_out)}));return status
    wrapper=ROOT/'tools/usb-observe'
    if not wrapper.exists():wrapper=args.bin/'usb-observe'
    command=[sys.executable,str(wrapper),'--bin',str(args.bin),'--port',args.port,'--duration','3','--interval','.5']
    observed=subprocess.run(command,capture_output=True,timeout=10)
    log=args.raw_out/'passive-baseline.jsonl';log.write_bytes(observed.stdout)
    (args.raw_out/'passive-baseline.stderr').write_bytes(observed.stderr)
    if observed.returncode:return 1
    command[command.index('--duration')+1]='20'
    termination=terminate_observer(command,args.raw_out/'termination.jsonl')
    if termination['returncode'] or termination.get('summary',{}).get('reason')!='signal':return 1
    (args.raw_out/'termination.json').write_text(json.dumps(termination,indent=2)+'\n')
    # Preserve the capture-only manifest, then cover the complete raw run.
    (args.raw_out/'SHA256SUMS').rename(args.raw_out/'CAPTURE_SHA256SUMS')
    write_manifest(args.raw_out)
    result=create_bundle(args.raw_out,args.bundle,load_database(),[log,*args.observer_log],termination)
    problems=validate_bundle(args.bundle)
    print(json.dumps({'result':result,'validation_errors':problems,'bundle':str(args.bundle)},indent=2))
    return 1 if problems else 0


if __name__=='__main__':raise SystemExit(main())
