#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal `cpio -idum`: extract a newc cpio archive from stdin into the current directory.

Used by setup.sh, together with rpm2cpio.py, to run Apptainer's unprivileged installer
on hosts without the cpio package. Only extraction (-i) of newc/crc archives is supported.
"""
import os
import stat
import sys


def _field(hdr, i):
    return int(hdr[6 + 8 * i:14 + 8 * i], 16)


def extract(stream, dest="."):
    data = stream.read()
    off = 0
    while off < len(data):
        hdr = data[off:off + 110]
        if len(hdr) < 110 or hdr[:6] not in (b"070701", b"070702"):
            raise SystemExit("not a newc cpio archive")
        mode, mtime, filesize, namesize = _field(hdr, 1), _field(hdr, 5), _field(hdr, 6), _field(hdr, 11)
        off += 110
        name = data[off:off + namesize - 1].decode()
        off += namesize + (-(110 + namesize)) % 4
        body = data[off:off + filesize]
        off += filesize + (-filesize) % 4
        if name == "TRAILER!!!":
            return
        path = os.path.normpath(os.path.join(dest, name.lstrip("/")))
        if not os.path.abspath(path).startswith(os.path.abspath(dest)):
            raise SystemExit(f"refusing to write outside {dest}: {name}")
        if stat.S_ISDIR(mode):
            os.makedirs(path, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if os.path.lexists(path):
            os.remove(path)
        if stat.S_ISLNK(mode):
            os.symlink(body.decode(), path)
            continue
        if stat.S_ISREG(mode):
            with open(path, "wb") as f:
                f.write(body)
            os.chmod(path, stat.S_IMODE(mode))
            os.utime(path, (mtime, mtime))
    # like cpio, fail on empty or truncated input so callers' retry loops kick in
    raise SystemExit("cpio: premature end of archive")


def main(argv):
    if not argv[1:] or not argv[1].startswith("-") or "i" not in argv[1]:
        raise SystemExit("usage: cpio -idum < archive")
    extract(sys.stdin.buffer)


if __name__ == "__main__":
    main(sys.argv)
