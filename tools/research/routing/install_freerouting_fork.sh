#!/bin/bash
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Build the magnetic-trowel/freerouting fork and install it where kae's bridge finds it:
#   $KAE_HOME/kae-freerouting-fork-<sha>/bin/freerouting
# with its own Java runtime (jlink, the modules of the upstream 2.5.0 bundle), so it runs in
# the benchmark sandbox without a system JDK. kae.route.freerouting prefers the newest such
# install (or KAE_BRIDGE_FREEROUTING); kaebench's own `freerouting` adapter keeps using the
# upstream release, so the human+Freerouting baseline does not change.
#
#   tools/research/routing/install_freerouting_fork.sh [REF] [SRC_DIR]
# REF defaults to origin/master; SRC_DIR to $KAE_HOME/src/freerouting (cloned if missing).
# Gradle provisions the JDK 25 toolchain the fork needs.
set -euo pipefail
KAE_HOME=${KAE_HOME:-$HOME/.cache/kaebench}
REF=${1:-origin/master}
SRC=${2:-$KAE_HOME/src/freerouting}
URL=https://github.com/magnetic-trowel/freerouting
MODULES=java.base,java.datatransfer,java.xml,java.prefs,java.desktop,java.logging,java.management,java.net.http,java.transaction.xa,java.sql,jdk.crypto.ec,jdk.management

if [ ! -d "$SRC/.git" ]; then
  git clone -q "$URL" "$SRC"
fi
git -C "$SRC" config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'
git -C "$SRC" fetch -q --prune origin
git -C "$SRC" checkout -q --detach "$REF"
SHA=$(git -C "$SRC" rev-parse --short=7 HEAD)
DEST=$KAE_HOME/kae-freerouting-fork-$SHA
if [ -x "$DEST/bin/freerouting" ]; then
  echo "already installed: $DEST/bin/freerouting"
  exit 0
fi
(cd "$SRC" && ./gradlew -q executableJar)
JAR=$(ls "$SRC"/build/libs/*-executable.jar)
JDK=$(ls -d "$HOME"/.gradle/jdks/*25*/ 2>/dev/null | grep -v '\.tar' | head -1)
[ -x "$JDK/bin/jlink" ] || { echo "no JDK 25 under ~/.gradle/jdks (gradle toolchain)"; exit 1; }
TMP=$DEST.tmp
rm -rf "$TMP" && mkdir -p "$TMP/bin" "$TMP/lib"
"$JDK/bin/jlink" --add-modules "$MODULES" --strip-debug --no-header-files --no-man-pages \
  --output "$TMP/lib/runtime"
cp "$JAR" "$TMP/lib/freerouting.jar"
cat > "$TMP/bin/freerouting" <<'EOF'
#!/bin/sh
D=$(cd "$(dirname "$0")/.." && pwd)
exec "$D/lib/runtime/bin/java" $FREEROUTING_JAVA_OPTS -jar "$D/lib/freerouting.jar" "$@"
EOF
chmod +x "$TMP/bin/freerouting"
echo "$SHA $(git -C "$SRC" log -1 --format=%s)" > "$TMP/VERSION"
mv "$TMP" "$DEST"
"$DEST/bin/freerouting" --help 2>&1 | grep -m1 "Freerouting v" || true
echo "installed: $DEST/bin/freerouting"
