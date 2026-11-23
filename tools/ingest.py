"""Turn an upload from the portal's help admin into a catalogued video (ingest.yml).

    python -m tools.ingest assemble --inbox inbox --out raw.video
    python -m tools.ingest apply --inbox inbox --duration SECONDS --catalog catalog.json

The admin cannot upload a release asset from a browser (uploads.github.com
answers no CORS preflight), so it commits the raw file as 30 MiB parts to an
`inbox/<file>` branch, with `inbox/entry.json` describing it. This rebuilds the
file, checks it is the one the browser hashed, and puts the entry into the
catalog once the video is published.
"""

import argparse
import hashlib
import json
from pathlib import Path

from tools import catalog

# Fields of entry.json that describe the upload, not the tutorial.
UPLOAD_FIELDS = ("section", "replaces", "size", "sha256")


def assemble(parts_dir, out, size, sha256):
    digest = hashlib.sha256()
    total = 0
    with open(out, "wb") as f:
        for part in sorted(Path(parts_dir).iterdir()):
            data = part.read_bytes()
            digest.update(data)
            total += len(data)
            f.write(data)
    if total != size:
        raise ValueError(f"the parts add up to {total} bytes, the upload had {size}")
    if digest.hexdigest() != sha256:
        raise ValueError(f"sha256 {digest.hexdigest()} is not the upload's {sha256}")


def apply(cat, entry, duration):
    video = {k: v for k, v in entry.items() if k not in UPLOAD_FIELDS and v is not None}
    video["duration"] = round(float(duration), 2)
    return catalog.upsert(cat, entry["section"], video, replaces=entry.get("replaces"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("assemble", help="rebuild the uploaded file from its parts")
    p.add_argument("--inbox", default="inbox")
    p.add_argument("--out", required=True)
    p = sub.add_parser("apply", help="put the upload's entry into the catalog")
    p.add_argument("--inbox", default="inbox")
    p.add_argument("--duration", type=float, required=True)
    p.add_argument("--catalog", default=catalog.DEFAULT_PATH)
    args = parser.parse_args(argv)

    entry = json.loads((Path(args.inbox) / "entry.json").read_text(encoding="utf-8"))
    if args.cmd == "assemble":
        assemble(Path(args.inbox) / "parts", args.out, entry["size"], entry["sha256"])
        return
    cat = apply(catalog.load(args.catalog), entry, args.duration)
    errors = catalog.validate(cat)
    if errors:
        raise SystemExit("\n".join(f"::error::{e}" for e in errors))
    catalog.save(cat, args.catalog)


if __name__ == "__main__":
    main()
