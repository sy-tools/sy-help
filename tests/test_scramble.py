import os
import subprocess
import sys

from tools.scramble import transform

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_transform_is_its_own_inverse():
    data = os.urandom(3 * 1024 * 1024 + 17)
    assert transform(transform(data)) == data


def test_transform_hides_the_mp4_signature():
    head = b"\x00\x00\x00\x20ftypisom"
    assert transform(head)[4:8] != b"ftyp"


def test_transform_at_an_offset_continues_the_keystream():
    data = os.urandom(100_000)
    whole = transform(data)
    assert transform(data[:40_000]) + transform(data[40_000:], offset=40_000) == whole


def test_cli_streams_the_same_bytes_as_one_shot(tmp_path):
    data = os.urandom(2 * 1024 * 1024 + 5)
    src, out = tmp_path / "in.mp4", tmp_path / "out.bin"
    src.write_bytes(data)
    subprocess.run([sys.executable, "-m", "tools.scramble", str(src), str(out)], cwd=ROOT, check=True)
    assert out.read_bytes() == transform(data)
