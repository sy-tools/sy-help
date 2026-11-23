import hashlib
import os

import pytest

from tools import catalog, ingest


def write_parts(tmp_path, data, size=1000):
    parts = tmp_path / "parts"
    parts.mkdir()
    for n, start in enumerate(range(0, len(data), size)):
        (parts / f"{n:03d}").write_bytes(data[start : start + size])
    return parts


def manifest(data, size=1000):
    return [{"size": len(data[i:i + size]), "sha256": hashlib.sha256(data[i:i + size]).hexdigest()}
            for i in range(0, len(data), size)]


def test_assemble_joins_the_parts_in_order(tmp_path):
    data = os.urandom(12_345)
    parts = write_parts(tmp_path, data)
    out = tmp_path / "raw"
    ingest.assemble(parts, out, len(data), manifest(data))
    assert out.read_bytes() == data


def test_assemble_refuses_a_part_that_is_not_the_one_uploaded(tmp_path):
    data = os.urandom(3000)
    parts = write_parts(tmp_path, data)
    bad = manifest(data)
    bad[1]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="part 001"):
        ingest.assemble(parts, tmp_path / "raw", len(data), bad)


def test_assemble_refuses_a_missing_part_or_a_wrong_total(tmp_path):
    data = os.urandom(3000)
    parts = write_parts(tmp_path, data)
    with pytest.raises(ValueError):
        ingest.assemble(parts, tmp_path / "raw", len(data), manifest(data) + manifest(b"x"))
    with pytest.raises(ValueError):
        ingest.assemble(parts, tmp_path / "raw", len(data) + 1, manifest(data))


def base():
    return {"version": 1, "sections": [
        {"id": "guide", "title": {"uk": "Р"}, "order": "manual",
         "videos": [{"file": "intro", "title": {"uk": "Вступ"}, "subtitles": ["uk", "en"], "duration": 5.0}]},
        {"id": "updates", "title": {"uk": "О"}, "order": "chronological", "videos": []},
    ]}


def entry(**kw):
    e = {"section": "guide", "file": "next", "replaces": None, "title": {"uk": "Далі", "en": "Next"},
         "description": {"uk": "", "en": ""}, "date": None, "notes": {"uk": [], "en": []},
         "size": 1, "parts": [{"size": 1, "sha256": "x"}]}
    e.update(kw)
    return e


def test_apply_adds_a_new_video_with_its_duration_and_no_upload_fields():
    out = ingest.apply(base(), entry(), 61.25)
    v = out["sections"][0]["videos"][1]
    assert v == {"file": "next", "title": {"uk": "Далі", "en": "Next"}, "description": {"uk": "", "en": ""},
                 "notes": {"uk": [], "en": []}, "duration": 61.25}


def test_apply_keeps_a_date_for_a_chronological_section():
    out = ingest.apply(base(), entry(section="updates", date="2026-12-01"), 3.0)
    assert out["sections"][1]["videos"][0]["date"] == "2026-12-01"
    assert catalog.validate(out) == []


def test_apply_replacing_takes_the_old_place_and_drops_its_subtitles():
    out = ingest.apply(base(), entry(file="intro-2", replaces="intro", title=None, description=None, notes=None), 9.0)
    v = out["sections"][0]["videos"][0]
    assert v["file"] == "intro-2"
    assert v["title"] == {"uk": "Вступ"}
    assert v["duration"] == 9.0
    assert "subtitles" not in v


def test_apply_twice_is_the_same_as_once():
    once = ingest.apply(base(), entry(), 2.0)
    assert ingest.apply(once, entry(), 2.0) == once
