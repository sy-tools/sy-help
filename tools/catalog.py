"""The tutorial catalog, `catalog.json`: the one source of every tutorial field.

    python -m tools.catalog validate [catalog.json]
    python -m tools.catalog set-subtitles FILE LANG[,LANG] [--catalog catalog.json]

The portal reads it to list the tutorials, its admin rewrites it, ingest adds
the videos it publishes, and the subtitle pipeline records which languages a
video has. Every function here returns a new catalog and leaves its input as
it was.
"""

import argparse
import copy
import json
import re
import sys

FILE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ORDERS = ("manual", "chronological")
DEFAULT_PATH = "catalog.json"


VERSION_SUFFIX_RE = re.compile(r"-v\d+$")


def stem(file):
    """The name apart from its -vN suffix: the video's identity across replacements."""
    return VERSION_SUFFIX_RE.sub("", file)


def loads(text):
    return json.loads(text)


def load(path=DEFAULT_PATH):
    with open(path, encoding="utf-8") as f:
        return loads(f.read())


def dump(cat):
    return json.dumps(cat, ensure_ascii=False, indent=2) + "\n"


def save(cat, path=DEFAULT_PATH):
    with open(path, "w", encoding="utf-8") as f:
        f.write(dump(cat))


def videos(cat):
    for section in cat.get("sections", []):
        yield from section.get("videos", [])


def files(cat):
    return [v["file"] for v in videos(cat)]


def validate(cat):
    errors = []
    if cat.get("version") != 1:
        errors.append(f"version must be 1, not {cat.get('version')!r}")
    seen = set()
    stems = {}
    section_ids = set()
    for section in cat.get("sections", []):
        sid = section.get("id")
        if not sid or not FILE_RE.match(str(sid)):
            errors.append(f"section id {sid!r} is not a slug")
        if sid in section_ids:
            errors.append(f"duplicate section '{sid}'")
        section_ids.add(sid)
        if not isinstance(section.get("videos"), list):
            errors.append(f"section '{sid}' has no videos list")
            continue
        order = section.get("order")
        if order not in ORDERS:
            errors.append(f"section '{sid}' has order '{order}', not one of {', '.join(ORDERS)}")
        for v in section.get("videos", []):
            name = v.get("file")
            if not isinstance(name, str) or not FILE_RE.match(name):
                errors.append(f"file {name!r} is not a lowercase slug")
            elif name in seen:
                errors.append(f"duplicate file '{name}'")
            elif stem(name) in stems:
                errors.append(f"'{name}' shares the name '{stem(name)}' with '{stems[stem(name)]}';"
                              " a -vN suffix marks a replacement")
            seen.add(name)
            if isinstance(name, str):
                stems.setdefault(stem(name), name)
            date = v.get("date")
            if order == "chronological" and not date:
                errors.append(f"'{name}' has no date, which its chronological section sorts by")
            if date and not DATE_RE.match(str(date)):
                errors.append(f"'{name}' has date {date!r}, not YYYY-MM-DD")
    return errors


def _find(cat, file):
    for s, section in enumerate(cat["sections"]):
        for i, v in enumerate(section["videos"]):
            if v["file"] == file:
                return s, i
    return None


def upsert(cat, section_id, entry, replaces=None):
    """Add `entry` to section `section_id`, or put it in the place of `replaces`.

    A replacement keeps the old entry's texts unless `entry` gives them, but
    never its subtitles: they belong to the old recording.
    """
    out = copy.deepcopy(cat)
    for target in (replaces, entry["file"]):
        found = target and _find(out, target)
        if found:
            s, i = found
            merged = {k: v for k, v in out["sections"][s]["videos"][i].items() if target == entry["file"] or k != "subtitles"}
            merged.update(copy.deepcopy(entry))
            out["sections"][s]["videos"][i] = merged
            return out
    for section in out["sections"]:
        if section["id"] == section_id:
            section["videos"].append(copy.deepcopy(entry))
            return out
    raise KeyError(f"no section '{section_id}'")


def remove_file(cat, file):
    out = copy.deepcopy(cat)
    for section in out["sections"]:
        section["videos"] = [v for v in section["videos"] if v["file"] != file]
    return out


def set_subtitles(cat, file, langs):
    out = copy.deepcopy(cat)
    found = _find(out, file)
    if not found:
        raise KeyError(f"no video '{file}'")
    s, i = found
    out["sections"][s]["videos"][i]["subtitles"] = list(langs)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("validate", help="exit 1 and list the errors of a broken catalog")
    p.add_argument("path", nargs="?", default=DEFAULT_PATH)
    p = sub.add_parser("set-subtitles", help="record the subtitle languages a video has")
    p.add_argument("file")
    p.add_argument("langs")
    p.add_argument("--catalog", default=DEFAULT_PATH)
    args = parser.parse_args(argv)
    if args.cmd == "validate":
        errors = validate(load(args.path))
        for e in errors:
            print(f"::error::{args.path}: {e}")
        sys.exit(1 if errors else 0)
    cat = set_subtitles(load(args.catalog), args.file, [x for x in args.langs.split(",") if x])
    save(cat, args.catalog)


if __name__ == "__main__":
    main()
