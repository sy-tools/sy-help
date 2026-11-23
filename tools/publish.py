"""Lay out the Pages site from the catalog and the `media` release.

    python -m tools.publish --catalog catalog.json --assets DIR --subs subs --out site

Only the videos the catalog lists are published, decoded from their scrambled
release asset to `v/<file>.mp4`: an asset nobody lists (a replaced recording,
a removed tutorial) never becomes public. The catalog and the subtitles go
along beside them, so the portal reads everything from one origin.
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

from tools import catalog
from tools.scramble import main as unscramble

ASSET_RE = re.compile(r"^(?P<file>[a-z0-9]+(?:-[a-z0-9]+)*)\.bin$")


def plan(cat, assets):
    names = {}
    for asset in assets:
        m = ASSET_RE.match(asset)
        if not m:
            raise ValueError(f"release asset '{asset}' is not <file>.bin")
        names[m["file"]] = asset
    listed = catalog.files(cat)
    return {
        "publish": [f for f in listed if f in names],
        "missing": [f for f in listed if f not in names],
        "orphans": sorted(f for f in names if f not in listed),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--catalog", default=catalog.DEFAULT_PATH)
    parser.add_argument("--assets", required=True, help="the downloaded release assets")
    parser.add_argument("--subs", default="subs")
    parser.add_argument("--out", default="site")
    args = parser.parse_args(argv)

    cat = catalog.load(args.catalog)
    errors = catalog.validate(cat)
    for e in errors:
        print(f"::error::{args.catalog}: {e}")
    try:
        p = plan(cat, sorted(x.name for x in Path(args.assets).iterdir()))
    except ValueError as e:
        print(f"::error::{e}")
        sys.exit(1)
    for f in p["missing"]:
        print(f"::error::'{f}' is in the catalog but the media release has no {f}.bin")
    if errors or p["missing"]:
        sys.exit(1)
    for f in p["orphans"]:
        print(f"::notice::{f}.bin is in the release but not in the catalog; not published")

    out = Path(args.out)
    (out / "v").mkdir(parents=True, exist_ok=True)
    for f in p["publish"]:
        unscramble([str(Path(args.assets) / f"{f}.bin"), str(out / "v" / f"{f}.mp4")])
    shutil.copyfile(args.catalog, out / "catalog.json")
    # Only the subtitles of listed videos: a removed one's stay in git
    # but stop being public with its video.
    listed = set(catalog.files(cat))
    (out / "subs").mkdir(exist_ok=True)
    for vtt in sorted(Path(args.subs).glob("*.vtt")) if Path(args.subs).is_dir() else []:
        if vtt.name.split(".")[0] in listed:
            shutil.copyfile(vtt, out / "subs" / vtt.name)
    print(f"published {len(p['publish'])} videos")


if __name__ == "__main__":
    main()
