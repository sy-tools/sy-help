"""Scramble a video for the `media` release, or restore it: the same XOR both ways.

    python -m tools.scramble IN OUT

The release page lists every asset, and a plain mp4 there opens in a player
with one click. A scrambled `.bin` is noise to a player. This is obfuscation,
not secrecy: the key is the constant below, in a public repository. The Pages
deploy restores the mp4 the portal plays.
"""

import hashlib
import sys

KEY = b"sy-help/scramble/v1"
BLOCK = 32  # bytes of keystream per SHA-256 digest
CHUNK = 1024 * 1024


def _keystream(offset, length):
    first = offset // BLOCK
    last = (offset + length + BLOCK - 1) // BLOCK
    stream = b"".join(hashlib.sha256(KEY + n.to_bytes(8, "big")).digest() for n in range(first, last))
    start = offset - first * BLOCK
    return stream[start : start + length]


def transform(data, offset=0):
    """XOR `data`, which sits at byte `offset` of its file, with the keystream."""
    key = _keystream(offset, len(data))
    return (int.from_bytes(data, "big") ^ int.from_bytes(key, "big")).to_bytes(len(data), "big")


def main(argv=None):
    src, dst = (argv if argv is not None else sys.argv[1:])[:2]
    offset = 0
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        while chunk := fin.read(CHUNK):
            fout.write(transform(chunk, offset))
            offset += len(chunk)


if __name__ == "__main__":
    main()
