#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Set up a kaebench host (Ubuntu 22.04/24.04 x86_64): KiCad 10, Freerouting 2.5.0, venv.
# Works without sudo: KiCad then runs from the official kicad/kicad image via
# Apptainer/Singularity (installed rootless into KAE_HOME if absent; needs unprivileged
# user namespaces), and the venv comes from uv if python3-venv is missing.
#
#   bench/scripts/setup.sh [--kicad auto|apt|container|none] [--no-freerouting] [--venv DIR]
#
# Environment: KAE_HOME (default ~/.cache/kaebench) holds Freerouting, the KiCad image
# and env.sh (sourced by the venv's activate script). KICAD_IMAGE_TAG (default 10.0.7).
set -euo pipefail

BENCH_DIR="$(cd "$(dirname "$0")/.." && pwd)"
KAE_HOME="${KAE_HOME:-$HOME/.cache/kaebench}"
VENV="$BENCH_DIR/.venv"
KICAD_MODE=auto
DO_FR=1
FR_VERSION="2.5.0"
FR_ZIP_SHA256="e8ffca14914e5307a2fa9aea723fb93d11b99bebda20d126472da5460c03196e"
KICAD_IMAGE_TAG="${KICAD_IMAGE_TAG:-10.0.7}"
APPTAINER_VERSION="1.5.4"
APPTAINER_INSTALLER_SHA256="a097956eafa6ab3dd843ee429d0b774ed029753bfadf013b8046556228fac6f2"

while [ $# -gt 0 ]; do
  case "$1" in
    --kicad) KICAD_MODE="$2"; shift ;;
    --no-kicad) KICAD_MODE=none ;;
    --no-freerouting) DO_FR=0 ;;
    --venv) VENV="$2"; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

mkdir -p "$KAE_HOME"
if [ "$(id -u)" -eq 0 ]; then SUDO=""; HAVE_SUDO=1
elif sudo -n true 2>/dev/null; then SUDO="sudo"; HAVE_SUDO=1
else SUDO=""; HAVE_SUDO=0
fi
ENV_FILE="$KAE_HOME/env.sh"
ENV_LINES=("export KAE_HOME=\"$KAE_HOME\"")

kicad_major() { kicad-cli version 2>/dev/null | cut -d. -f1; }
container_tool() {
  command -v apptainer || command -v singularity ||
    { [ -x "$KAE_HOME/apptainer/bin/apptainer" ] && echo "$KAE_HOME/apptainer/bin/apptainer"; } || true
}
userns_ok() { unshare -Ur true 2>/dev/null; }

install_apptainer_unpriv() {
  # Apptainer's own no-root installer unpacks EL8 RPMs; rpm2cpio and cpio fall back to
  # Python shims when the host lacks them.
  local dest="$KAE_HOME/apptainer" shims="$KAE_HOME/shims" inst="$KAE_HOME/install-unprivileged.sh"
  echo "Installing Apptainer $APPTAINER_VERSION without root into $dest"
  rm -rf "$dest" "$shims"
  mkdir -p "$shims"
  command -v rpm2cpio >/dev/null || ln -s "$BENCH_DIR/scripts/rpm2cpio.py" "$shims/rpm2cpio"
  command -v cpio >/dev/null || ln -s "$BENCH_DIR/scripts/cpio_extract.py" "$shims/cpio"
  curl -fsSL -o "$inst" \
    "https://raw.githubusercontent.com/apptainer/apptainer/v$APPTAINER_VERSION/tools/install-unprivileged.sh"
  echo "$APPTAINER_INSTALLER_SHA256  $inst" | sha256sum -c - >/dev/null
  PATH="$shims:$PATH" bash "$inst" -d el8 -v "$APPTAINER_VERSION" "$dest"
  rm -rf "$inst" "$shims"
}

install_kicad_apt() {
  . /etc/os-release
  echo "Installing KiCad 10 from ppa:kicad/kicad-10.0-releases (no recommends)"
  FP=$(curl -fsSL "https://api.launchpad.net/1.0/~kicad/+archive/ubuntu/kicad-10.0-releases" |
       python3 -c "import json,sys; print(json.load(sys.stdin)['signing_key_fingerprint'])")
  curl -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x$FP" |
    $SUDO gpg --dearmor --yes -o /usr/share/keyrings/kicad-10.gpg
  echo "deb [signed-by=/usr/share/keyrings/kicad-10.gpg] https://ppa.launchpadcontent.net/kicad/kicad-10.0-releases/ubuntu ${VERSION_CODENAME} main" |
    $SUDO tee /etc/apt/sources.list.d/kicad-10.list >/dev/null
  $SUDO apt-get update -qq
  $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends kicad
}

install_kicad_container() {
  local tool dir
  tool="$(container_tool)"
  dir="$KAE_HOME/kicad-$KICAD_IMAGE_TAG"
  if [ ! -x "$dir/usr/bin/kicad-cli" ]; then
    rm -rf "$dir"   # a partial unpack from an interrupted run
    echo "Unpacking docker://kicad/kicad:$KICAD_IMAGE_TAG into $dir with $(basename "$tool") (~2.5 GB, no root needed)"
    # an unpacked directory needs neither root nor /dev/fuse at run time
    APPTAINER_CACHEDIR="${APPTAINER_CACHEDIR:-$KAE_HOME/apptainer-cache}" \
      "$tool" build --sandbox "$dir" "docker://kicad/kicad:$KICAD_IMAGE_TAG"
    [ -n "${APPTAINER_CACHEDIR:-}" ] || rm -rf "$KAE_HOME/apptainer-cache"   # keep a user-set cache
  fi
  ENV_LINES+=("export KAE_KICAD_WRAP=\"$tool exec $dir\"")
}

case "$KICAD_MODE" in
  none)  # keep any KiCad wrapper configured by an earlier run
    if [ -f "$ENV_FILE" ]; then
      while IFS= read -r line; do ENV_LINES+=("$line"); done < <(grep '^export KAE_KICAD_' "$ENV_FILE" || true)
    fi ;;
  apt) install_kicad_apt ;;
  container)
    if [ -z "$(container_tool)" ]; then
      userns_ok || { echo "no apptainer/singularity, and unprivileged user namespaces are disabled" >&2; exit 1; }
      install_apptainer_unpriv
    fi
    install_kicad_container ;;
  auto)
    if [ "$(kicad_major || echo 0)" -ge 10 ] 2>/dev/null; then
      echo "KiCad $(kicad-cli version) already installed"
    elif [ "$HAVE_SUDO" = 1 ] && grep -q '^ID=ubuntu' /etc/os-release 2>/dev/null; then
      install_kicad_apt
    elif [ -n "$(container_tool)" ]; then
      install_kicad_container
    elif [ "$(uname -m)" = x86_64 ] && userns_ok; then
      install_apptainer_unpriv
      install_kicad_container
    else
      cat >&2 <<'EOF'
KiCad 10 is not installed, there is no sudo or Apptainer/Singularity, and Apptainer cannot
be installed rootless here (needs x86_64 and unprivileged user namespaces; `unshare -Ur true`
fails, e.g. on Ubuntu 24.04 with kernel.apparmor_restrict_unprivileged_userns=1). Options:
  - ask an admin to run: bench/scripts/setup.sh --kicad apt   (KiCad PPA, no recommends)
  - ask an admin to install apptainer, then re-run this script (KiCad runs from the official image)
  - flatpak --user install flathub org.kicad.KiCad, then set
      KAE_KICAD_CLI="flatpak run --command=kicad-cli org.kicad.KiCad"
      KAE_KICAD_PYTHON="flatpak run --command=python3 org.kicad.KiCad"
Re-run with --kicad none to install the rest now.
EOF
      exit 1
    fi ;;
  *) echo "unknown --kicad mode $KICAD_MODE" >&2; exit 2 ;;
esac

if [ "$DO_FR" = 1 ]; then
  DEST="$KAE_HOME/freerouting-$FR_VERSION-linux-x64"
  if [ -x "$DEST/bin/freerouting" ]; then
    echo "Freerouting $FR_VERSION already at $DEST"
  else
    ZIP="$KAE_HOME/freerouting-$FR_VERSION-linux-x64.zip"
    curl -fsSL -o "$ZIP" \
      "https://github.com/freerouting/freerouting/releases/download/v$FR_VERSION/freerouting-$FR_VERSION-linux-x64.zip"
    echo "$FR_ZIP_SHA256  $ZIP" | sha256sum -c -
    python3 -c "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$ZIP" "$KAE_HOME"
    chmod +x "$DEST/bin/freerouting" "$DEST/lib/runtime/bin/"* "$DEST/lib/runtime/lib/jspawnhelper" 2>/dev/null || true
    rm -f "$ZIP"
  fi
fi

if python3 -c "import ensurepip, venv" 2>/dev/null; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -e "$BENCH_DIR[test]"
elif [ "$HAVE_SUDO" = 1 ]; then
  $SUDO apt-get install -y -qq python3-venv
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -e "$BENCH_DIR[test]"
else
  echo "python3-venv is missing and there is no sudo: using uv for the venv"
  command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
  UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
  "$UV" venv -q --python 3.12 "$VENV"
  "$UV" pip install -q --python "$VENV/bin/python" -e "$BENCH_DIR[test]"
fi

printf '%s\n' "${ENV_LINES[@]}" > "$ENV_FILE"
grep -qF "$ENV_FILE" "$VENV/bin/activate" || echo "[ -f \"$ENV_FILE\" ] && . \"$ENV_FILE\"" >> "$VENV/bin/activate"
echo
( . "$ENV_FILE" && "$VENV/bin/kaebench" doctor )
echo
echo "Activate with: source $VENV/bin/activate"
