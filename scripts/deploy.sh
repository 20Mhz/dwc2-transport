#!/usr/bin/env bash
# Userspace-only deployment. No kernel/module/configuration changes.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
host="${1:?usage: deploy.sh HOST}"
case "$host" in -*|*[!a-zA-Z0-9@._-]*) echo 'invalid SSH host' >&2; exit 2;; esac
package="$("$root/scripts/package.sh")"
archive="$(basename "$package")"
release="${archive%.tar.gz}"
# The archive is versioned; existing installed releases remain separate.
COPYFILE_DISABLE=1 tar --no-xattrs -C "$root" -cf - "${package#"$root/"}" | \
    ssh -o BatchMode=yes -o ConnectTimeout=10 "$host" 'mkdir -p dwc2-transport; tar -C dwc2-transport -xf -'
ssh -o BatchMode=yes "$host" "cd dwc2-transport && tar -xzf 'releases/$archive' && cd '$release' && sha256sum -c SHA256SUMS && bin/usb-discover --version"
