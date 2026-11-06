#!/usr/bin/env bash
# Download a pinned gitleaks binary and check the release checksum (NSE-001).
# The working-tree scan is `make secrets`. History scanning is separate.
set -euo pipefail

VERSION="8.30.1"
# linux/amd64 asset from the v8.30.1 checksums file. CI runs on that platform.
LINUX_X64_SHA256="551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${ROOT}/tools/gitleaks"
BASE="https://github.com/gitleaks/gitleaks/releases/download/v${VERSION}"

if [[ -x "${DEST}" ]] && "${DEST}" version 2>/dev/null | grep -q "${VERSION}"; then
  exit 0
fi

os="$(uname -s | tr '[:upper:]' '[:lower:]')"
arch="$(uname -m)"
case "${os}-${arch}" in
  linux-x86_64 | linux-amd64) asset="linux_x64" ;;
  linux-aarch64 | linux-arm64) asset="linux_arm64" ;;
  darwin-arm64) asset="darwin_arm64" ;;
  darwin-x86_64) asset="darwin_x64" ;;
  *)
    echo "unsupported platform ${os}-${arch}" >&2
    exit 1
    ;;
esac

mkdir -p "${ROOT}/tools"
tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT
archive="gitleaks_${VERSION}_${asset}.tar.gz"
curl -fsSL "${BASE}/${archive}" -o "${tmp}/${archive}"
curl -fsSL "${BASE}/gitleaks_${VERSION}_checksums.txt" -o "${tmp}/checksums.txt"
(
  cd "${tmp}"
  grep -F "${archive}" checksums.txt > check.txt
  sha256sum -c check.txt
)
if [[ "${asset}" == "linux_x64" ]]; then
  echo "${LINUX_X64_SHA256}  ${tmp}/${archive}" | sha256sum -c -
fi
tar -xzf "${tmp}/${archive}" -C "${tmp}" gitleaks
install -m 0755 "${tmp}/gitleaks" "${DEST}"
