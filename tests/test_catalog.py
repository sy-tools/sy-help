import copy

from tools import catalog


def video(file, **extra):
    v = {"file": file, "title": {"uk": "Назва", "en": "Title"}}
    v.update(extra)
    return v


def cat(*sections):
    return {"version": 1, "sections": list(sections)}


def section(sid, videos, order="manual"):
    return {"id": sid, "title": {"uk": "Розділ", "en": "Section"}, "order": order, "videos": videos}


def test_a_valid_catalog_has_no_errors():
    c = cat(section("guide", [video("intro")]), section("updates", [video("upd", date="2026-09-05")], "chronological"))
    assert catalog.validate(c) == []


def test_validate_flags_each_broken_rule():
    c = cat(
        section("guide", [video("intro"), video("intro"), video("Bad_Name")]),
        section("updates", [video("upd")], "chronological"),
        section("other", [], "random"),
    )
    c["version"] = 2
    errors = "\n".join(catalog.validate(c))
    assert "version" in errors
    assert "duplicate file 'intro'" in errors
    assert "'Bad_Name'" in errors
    assert "'upd' has no date" in errors
    assert "order 'random'" in errors


def test_files_lists_every_video_in_order():
    c = cat(section("a", [video("x"), video("y")]), section("b", [video("z", date="2026-01-01")], "chronological"))
    assert catalog.files(c) == ["x", "y", "z"]


def test_upsert_appends_a_new_video_to_its_section():
    c = cat(section("guide", [video("intro")]))
    out = catalog.upsert(c, "guide", video("next"), replaces=None)
    assert catalog.files(out) == ["intro", "next"]
    assert catalog.files(c) == ["intro"], "the input is not mutated"


def test_upsert_replacing_keeps_the_place_and_the_texts_not_given():
    old = video("intro-2", description={"uk": "Опис", "en": "About"}, subtitles=["uk", "en"])
    c = cat(section("guide", [video("a"), old, video("b")]))
    out = catalog.upsert(c, "guide", {"file": "intro-3", "duration": 12.5}, replaces="intro-2")
    entry = out["sections"][0]["videos"][1]
    assert entry["file"] == "intro-3"
    assert entry["title"] == old["title"]
    assert entry["description"] == old["description"]
    assert entry["duration"] == 12.5
    assert "subtitles" not in entry, "a new recording needs new subtitles"


def test_upsert_of_an_existing_file_updates_it_in_place():
    c = cat(section("guide", [video("intro", duration=1.0)]))
    out = catalog.upsert(c, "guide", video("intro", duration=2.0), replaces=None)
    assert catalog.files(out) == ["intro"]
    assert out["sections"][0]["videos"][0]["duration"] == 2.0


def test_remove_file_and_set_subtitles():
    c = cat(section("guide", [video("a"), video("b")]))
    assert catalog.files(catalog.remove_file(c, "a")) == ["b"]
    out = catalog.set_subtitles(c, "b", ["uk", "en"])
    assert out["sections"][0]["videos"][1]["subtitles"] == ["uk", "en"]


def test_dump_is_stable_utf8_json_with_a_trailing_newline():
    c = cat(section("guide", [video("a")]))
    text = catalog.dump(c)
    assert text.endswith("}\n")
    assert "Назва" in text
    assert catalog.loads(text) == copy.deepcopy(c)


def test_validate_flags_a_section_without_a_video_list():
    c = cat(section("guide", []))
    del c["sections"][0]["videos"]
    assert "has no videos list" in "\n".join(catalog.validate(c))


def test_validate_refuses_two_videos_sharing_a_name_apart_from_a_version():
    c = cat(section("guide", [video("intro"), video("intro-v2"), video("intro-2")]))
    errors = catalog.validate(c)
    assert errors == ["'intro-v2' shares the name 'intro' with 'intro'; a -vN suffix marks a replacement"]


def test_stem_strips_only_a_version_suffix():
    assert catalog.stem("intro-v12") == "intro"
    assert catalog.stem("intro-2") == "intro-2"
