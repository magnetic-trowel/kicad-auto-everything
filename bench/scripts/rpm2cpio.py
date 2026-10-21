#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal rpm2cpio: write an RPM's cpio payload to stdout (usage: rpm2cpio.py FILE|-).

Used by setup.sh to run Apptainer's unprivileged installer on hosts without the
rpm2cpio package. Handles xz, gzip and bzip2 payloads (zstd needs Python 3.14+).
"""
import bz2
import gzip
import lzma
import struct
import sys


def _header_len(data, off):
    if data[off:off + 3] != b"\x8e\xad\xe8":
        raise ValueError("bad RPM header magic")
    nindex, hsize = struct.unpack(">II", data[off + 8:off + 16])
    return 16 + 16 * nindex + hsize


def payload(data):
    if data[:4] != b"\xed\xab\xee\xdb":
        raise SystemExit(f"rpm2cpio: not an RPM file ({len(data)} bytes read)")
    off = 96                                   # lead
    sig = _header_len(data, off)
    off += sig + (-sig) % 8                    # signature header is padded to 8 bytes
    off += _header_len(data, off)              # main header
    return data[off:]


def decompress(p):
    if p[:6] == b"\xfd7zXZ\x00":
        return lzma.decompress(p)
    if p[:2] == b"\x1f\x8b":
        return gzip.decompress(p)
    if p[:3] == b"BZh":
        return bz2.decompress(p)
    if p[:4] == b"\x28\xb5\x2f\xfd":
        try:
            from compression import zstd  # Python 3.14+
        except ImportError:
            raise SystemExit("zstd-compressed RPM; use an EL8 package or install rpm2cpio")
        return zstd.decompress(p)
    if p[:6] in (b"070701", b"070702"):
        return p
    raise SystemExit("unknown RPM payload compression")


def main(argv):
    src = sys.stdin.buffer if len(argv) < 2 or argv[1] == "-" else open(argv[1], "rb")
    sys.stdout.buffer.write(decompress(payload(src.read())))


if __name__ == "__main__":
    main(sys.argv)
