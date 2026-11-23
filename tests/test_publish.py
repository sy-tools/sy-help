import json
import os
import subprocess
import sys

import pytest

from tools import publish
from tools.scramble import transform

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cat(*files):
    return {"version": 1, "sections": [{"id": "guide", "title": {"uk": "Р"}, "order": "manual",
                                        "videos": [{"file": f, "title": {"uk": f}} for f in files]}]}


def test_plan_sorts_listed_missing_and_orphan_files():
    out = publish.plan(cat("a", "b"), ["a.bin", "old.bin"])
    assert out == {"publish": ["a"], "missing": ["b"], "orphans": ["old"]}


def test_plan_refuses_an_asset_name_that_is_not_a_slug():
    with pytest.raises(ValueError, match="Intro.mp4"):
        publish.plan(cat("a"), ["a.bin", "Intro.mp4"])


def run(tmp_path, catalog):
    (tmp_path / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "tools.publish", "--catalog", str(tmp_path / "catalog.json"),
         "--assets", str(tmp_path / "assets"), "--subs", str(tmp_path / "subs"), "--out", str(tmp_path / "site")],
        cwd=ROOT, capture_output=True, text=True)


def test_cli_decodes_listed_videos_and_copies_catalog_and_subtitles(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "subs").mkdir()
    (tmp_path / "site").mkdir()
    video = os.urandom(5000)
    (tmp_path / "assets" / "a.bin").write_bytes(transform(video))
    (tmp_path / "assets" / "old.bin").write_bytes(b"x")
    (tmp_path / "subs" / "a.uk.vtt").write_text("WEBVTT\n", encoding="utf-8")
    result = run(tmp_path, cat("a"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "site" / "v" / "a.mp4").read_bytes() == video
    assert not (tmp_path / "site" / "v" / "old.mp4").exists()
    assert (tmp_path / "site" / "subs" / "a.uk.vtt").exists()
    assert json.loads((tmp_path / "site" / "catalog.json").read_text(encoding="utf-8")) == cat("a")
    assert "old" in result.stdout


def test_cli_fails_when_a_listed_video_has_no_asset(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "subs").mkdir()
    result = run(tmp_path, cat("a"))
    assert result.returncode == 1
    assert "'a'" in result.stdout


def test_cli_publishes_subtitles_only_of_catalogued_videos(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "subs").mkdir()
    (tmp_path / "assets" / "a.bin").write_bytes(transform(b"v"))
    (tmp_path / "subs" / "a.uk.vtt").write_text("WEBVTT\n", encoding="utf-8")
    (tmp_path / "subs" / "gone.uk.vtt").write_text("WEBVTT\n", encoding="utf-8")
    result = run(tmp_path, cat("a"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "site" / "subs" / "a.uk.vtt").exists()
    assert not (tmp_path / "site" / "subs" / "gone.uk.vtt").exists()
