#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Local, deterministic release archive with source, relink objects and privacy audit."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from dwc2_diag.evidence import verify_manifest,write_manifest
from dwc2_diag.privacy import public_errors


def archive_tree(stage,archive,epoch):
    with archive.open('wb') as stream,gzip.GzipFile(filename='',mode='wb',fileobj=stream,mtime=0) as compressed,tarfile.open(fileobj=compressed,mode='w',format=tarfile.PAX_FORMAT) as tar:
        for path in [stage,*sorted(stage.rglob('*'))]:
            info=tar.gettarinfo(str(path),arcname=str(path.relative_to(stage.parent)))
            info.uid=info.gid=0;info.uname=info.gname='root';info.mtime=epoch;info.pax_headers={}
            if path.is_file():
                with path.open('rb') as data:tar.addfile(info,data)
            else:tar.addfile(info)
    Path(str(archive)+'.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')


def main():
    os.chdir(ROOT)
    build=Path(sys.argv[1] if len(sys.argv)>1 else 'build/armv6').resolve()
    manifest=json.loads((build/'BUILD_MANIFEST.json').read_text())
    for name,digest in manifest['source_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:
            raise SystemExit('source changed since build: '+name)
    for name,digest in manifest['binary_sha256'].items():
        if hashlib.sha256((build/name).read_bytes()).hexdigest()!=digest:
            raise SystemExit('binary changed since build: '+name)
    spec=importlib.util.spec_from_file_location('source_info',ROOT/'scripts/source-info.py')
    provenance=importlib.util.module_from_spec(spec);spec.loader.exec_module(provenance)
    info=provenance.source_info(ROOT);revision,epoch=info['revision'],info['epoch']
    version=re.search(r'#define DT_VERSION "([^"]+)"',Path('include/dwc2_transport/transport.h').read_text())[1]
    name=f'dwc2-transport-{version}-linux-armv6'
    with tempfile.TemporaryDirectory() as temporary:
        stage=Path(temporary)/name;stage.mkdir()
        def copy(source,target=None):
            source=Path(source);target=stage/(target or source)
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        for program in ('usb-discover','usb-inspect','usb-diagnostics','read-descriptor','test-hardware','test-core','test-async','test-replay'):
            copy(build/program,Path('bin')/program)
        copy(build/'libdwc2_transport.a','lib/libdwc2_transport.a')
        for wrapper in ('usb-observe','usb-evidence-verify','usb-annotate'):
            copy('tools/'+wrapper,'bin/'+wrapper)
        tracked=info['files']
        source_roots={'src','include','tools','examples','tests','scripts','cmake','docker','python','data'}
        for relative in tracked:
            if not relative:continue
            source=Path(relative)
            if source.parts[0] in source_roots and source.is_file():copy(source,Path('source')/source)
            if source.parts[0] in ('include','examples','python','data') or relative in ('LICENSE','NOTICE','README.md'):copy(source)
            if source.parts[0]=='scripts' and source.suffix=='.py':copy(source)
            if source.parts[0]=='docs' and source.suffix=='.md':copy(source)
        for file in ('Makefile','CMakeLists.txt','LICENSE','NOTICE'):copy(file,Path('source')/file)
        # Prior raw/evidence logs stay local; copy only the sanitized M7 export.
        for public in (Path('docs/evidence/m7-20261104'),Path('docs/evidence/m8-20261104')):
            if public.exists():
                for source in public.rglob('*'):
                    if source.is_file():copy(source)
        for path in sorted(build.rglob('*.o')):copy(path,Path('relink')/path.relative_to(build))
        for path in (build/'licenses').iterdir():copy(path,Path('licenses')/path.name)
        runtime=json.loads(Path('data/runtime-source-manifest.json').read_text())
        versions=dict(line.split() for line in (build/'TOOLCHAIN_PACKAGES').read_text().splitlines())
        if any(versions.get(name)!=version for name,version in runtime['toolchain_requirements'].items()):
            raise SystemExit('runtime source pins do not match the recorded toolchain; update the source/license audit')
        cache=ROOT/'licenses/runtime-sources'
        if not cache.is_dir():cache=ROOT/'build/runtime-sources'
        for item in runtime['files']:
            source=cache/item['name']
            if hashlib.sha256(source.read_bytes()).hexdigest()!=item['sha256'] or source.stat().st_size!=item['bytes']:
                raise SystemExit('runtime source checksum mismatch: '+item['name'])
            copy(source,Path('licenses/runtime-sources')/item['name'])
        copy('data/runtime-source-manifest.json','licenses/runtime-sources/SOURCE_MANIFEST.json')
        (stage/'LICENSE_AUDIT.json').write_text(json.dumps({'schema':1,'project':'MIT; LICENSE and HostLab attribution in NOTICE',
            'runtime_sources':'GNU libc 2.36-8 and cross-toolchain-base 66 source, Debian patches and descriptors included',
            'gcc_runtime':'Debian copyright and GCC Runtime Library Exception included',
            'relink_materials':'Application source, object files and SDK static library included',
            'external_classification':'Public facts and references only; no external protocol implementation linked',
            'limitations':['Debian source descriptor signatures were not independently checked.',
                           'Runtime provenance uses recorded package versions; the runtime itself was not rebuilt in this validation.']},indent=2)+'\n')
        for file in ('BUILD_MANIFEST.json','TOOLCHAIN_PACKAGES','BUILD_IMAGE'):copy(build/file,file)
        copy(build/'BUILD_REVISION','REVISION')
        (stage/'APPLICATION_REVISION').write_text(revision+'\n')
        (stage/'APPLICATION_MANIFEST.json').write_text(json.dumps({'revision':revision,
            'files':{str(path.relative_to(stage)):hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in sorted(stage.rglob('*')) if path.is_file() and path.relative_to(stage).parts[0] in ('python','data','scripts','source')}},indent=2)+'\n')
        forbidden=[]
        legacy=Path('docs/evidence/apple-tv-20261104-pi-readonly2/inspection.stdout')
        if legacy.exists():
            inspection=json.loads(legacy.read_text());index=bytes.fromhex(inspection['device_descriptor']['raw'])[16]
            for item in inspection['strings']:
                if item['index']==index and item.get('text'):
                    serial=item['text'];forbidden += [serial.encode(),serial.encode('utf-16-le'),serial.encode('utf-16-le').hex().encode(),item['raw'].encode()]
        errors=public_errors(stage,forbidden)
        if errors:raise SystemExit('public artifact audit failed:\n'+'\n'.join(errors))
        (stage/'PUBLIC_AUDIT.json').write_text(json.dumps({'schema':1,'revision':revision,
            'result':'PASS','scope':'archive regular files; source and relink objects included',
            'checks':['credentials and key patterns','private home paths','raw trace types','structured serial fields','known legacy serial encodings'],
            'limitations':'Pattern checks are not proof that arbitrary unknown secrets are absent. Git history and raw local files are not included. Nested upstream source archives are checksum-verified, not recursively pattern-scanned.'},indent=2)+'\n')
        write_manifest(stage)
        if verify_manifest(stage):raise SystemExit('release manifest invalid')
        output=Path('releases');output.mkdir(exist_ok=True)
        archive=output/(name+'.tar.gz')
        archive_tree(stage,archive,epoch)
        source_stage=Path(temporary)/f'dwc2-transport-{version}-source'
        shutil.copytree(stage/'source',source_stage)
        shutil.copytree(stage/'docs',source_stage/'docs')
        for file in ('README.md','BUILD_IMAGE','TOOLCHAIN_PACKAGES','LICENSE_AUDIT.json'):
            shutil.copy2(stage/file,source_stage/file)
        shutil.copytree(stage/'licenses',source_stage/'licenses')
        source_files={str(path.relative_to(source_stage)):hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in sorted(source_stage.rglob('*')) if path.is_file()}
        (source_stage/'SOURCE_INFO.json').write_text(json.dumps({'schema':1,'revision':revision,'epoch':epoch,'sha256':source_files},indent=2)+'\n')
        source_errors=public_errors(source_stage,forbidden)
        if source_errors:raise SystemExit('source privacy audit failed: '+str(source_errors))
        write_manifest(source_stage)
        archive_tree(source_stage,output/f'dwc2-transport-{version}-source.tar.gz',epoch)
        print(ROOT/archive)


if __name__=='__main__':main()
