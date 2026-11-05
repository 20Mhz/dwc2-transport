#!/usr/bin/env bash
# Adapted from HostLab's ARM1176 build and negative-control check (MIT).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
image="${DT_BUILD_IMAGE:-dwc2-hostlab-build}"
if ! docker image inspect "$image" >/dev/null 2>&1; then
    image=dwc2-transport-build
    docker build -t "$image" "$root/docker"
fi
export SOURCE_DATE_EPOCH="$(python3 "$root/scripts/source-info.py" --field epoch)"
docker run --rm --user "$(id -u):$(id -g)" -e SOURCE_DATE_EPOCH -v "$root:/work" -w /work "$image" bash -euo pipefail -c '
make BUILD=build/armv6 CC=arm-linux-gnueabi-gcc AR=arm-linux-gnueabi-ar \
    CFLAGS="-O2 -march=armv6kz -marm" LDFLAGS=-static all test \
    TEST_RUNNER="qemu-arm-static -cpu arm1176"
for n in usb-discover usb-inspect usb-diagnostics read-descriptor test-hardware; do
    arm-linux-gnueabi-readelf -A "build/armv6/$n" | grep -q "Tag_CPU_arch: v6KZ"
    file "build/armv6/$n"
done
cat > /tmp/dt-v7.c <<EOF2
int main(void) { int r; __asm__ volatile("movw %0, #1" : "=r"(r)); return r - 1; }
EOF2
arm-linux-gnueabi-gcc -static -O2 -march=armv7-a -marm -o /tmp/dt-v7 /tmp/dt-v7.c
ulimit -c 0
qemu-arm-static -cpu cortex-a7 /tmp/dt-v7
if (cd /tmp && qemu-arm-static -cpu arm1176 ./dt-v7) 2>/dev/null; then
    echo "FAIL: ARMv7 instruction ran under arm1176" >&2; exit 1
fi
echo "ARMv7 negative control rejected by ARM1176: PASS"
arm-linux-gnueabi-gcc --version | head -1
qemu-arm-static --version | head -1
mkdir -p build/armv6/licenses
cp /usr/share/doc/libc6-armel-cross/copyright build/armv6/licenses/glibc-copyright
cp /usr/share/doc/libgcc-12-dev-armel-cross/copyright build/armv6/licenses/gcc-runtime-copyright
cp /usr/share/common-licenses/LGPL-2.1 /usr/share/common-licenses/GPL-2 /usr/share/common-licenses/GPL-3 build/armv6/licenses/
dpkg-query -W libc6-armel-cross libc6-dev-armel-cross libgcc-12-dev-armel-cross gcc-12-arm-linux-gnueabi > build/armv6/TOOLCHAIN_PACKAGES
'
docker image inspect "$image" --format '{{.Id}}' > "$root/build/armv6/BUILD_IMAGE"

python3 "$root/scripts/source-info.py" --field revision > "$root/build/armv6/BUILD_REVISION"
python3 - "$root" <<'PYBUILD'
from pathlib import Path
import hashlib
import json
import sys
root=Path(sys.argv[1]);build=root/'build/armv6'
paths=[p for folder in ('src','include','tools','data') for p in (root/folder).rglob('*') if p.is_file() and p.suffix in ('.c','.h','.json','.py')]
paths += [root/'Makefile',root/'CMakeLists.txt',root/'scripts/build-armv6.sh',root/'scripts/source-info.py',root/'docker/Dockerfile']
manifest={'sdk_revision':(build/'BUILD_REVISION').read_text().strip(),
          'target':'ARM1176 ARMv6KZ static armel','flags':'-O2 -march=armv6kz -marm -static',
          'source_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)},
          'binary_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(build.iterdir()) if p.is_file() and (p.name.startswith(('usb-', 'test-')) or p.name in ('read-descriptor','libdwc2_transport.a'))}}
(build/'BUILD_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
PYBUILD
