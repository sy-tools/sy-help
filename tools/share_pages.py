"""Share pages: one link per tutorial that a messenger can preview.

    python -m tools.share_pages --site site

The portal opens a tutorial at `#/help/<file>`, and a fragment never reaches
a server: Telegram's and WhatsApp's crawlers fetch the same portal page for
every video, and that page draws its UI in JavaScript they do not run. So
each tutorial also gets a static page of its own, `s/<stem>/`, carrying the
Open Graph tags and its first frame, which sends a person on to the portal.

`<stem>` is the file name without its `-vN` suffix: a replaced recording
keeps its link, and the page describes the newest version, the same rule the
portal follows for `#/help/` links. The frame is named by the file, not the
stem, so a replacement gets a new image URL (a name never changes content).
"""

import argparse
import html
import json
import re
import subprocess
import sys
from pathlib import Path

from tools import catalog

HELP_BASE = "https://sy-tools.github.io/sy-help/"
PORTAL = "https://sy-tools.github.io/sy-subtitles/"
SITE_NAME = "SY Subtitles"
FRAME_WIDTH = 1200
# WhatsApp drops the image from a preview when it is much larger than this.
MAX_IMAGE_BYTES = 300_000

_VERSION_RE = re.compile(r"-v(\d+)$")


def stem(file):
    return _VERSION_RE.sub("", file)


def _version(file):
    m = _VERSION_RE.search(file)
    return int(m.group(1)) if m else 1


def latest_by_stem(cat):
    """stem -> (video, its section), the newest version of each video."""
    out = {}
    for section in cat.get("sections", []):
        for v in section.get("videos", []):
            key = stem(v["file"])
            if key not in out or _version(v["file"]) > _version(out[key][0]["file"]):
                out[key] = (v, section)
    return out


def _uk(field):
    return (field or {}).get("uk") or ""


def page_title(video):
    """The title as the portal's help sheet shows it."""
    title = _uk(video.get("title"))
    if title:
        return title
    if video.get("date"):
        y, m, d = video["date"].split("-")
        return f"Оновлення на {d}.{m}.{y}"
    return video["file"]


def _duration(seconds):
    if not isinstance(seconds, (int, float)):
        return ""
    total = round(seconds)
    h, m, s = total // 3600, total % 3600 // 60, total % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def page_description(video, section):
    text = _uk(video.get("description"))
    if text:
        return text
    parts = [_uk(section.get("title")), _duration(video.get("duration")), SITE_NAME]
    return " · ".join(p for p in parts if p)


_REDIRECT = """var from = new URLSearchParams(location.search), kept = new URLSearchParams();
['q', 'f'].forEach(function (k) { if (from.get(k)) kept.set(k, from.get(k)); });
var qs = kept.toString();
location.replace(%s + (qs ? '?' + qs : '') + '#/help/' + %s);"""


def _esc(value):
    return html.escape(str(value), quote=True)


def page_html(*, stem, video, section, image, width, height, help_base, portal):
    url = f"{help_base}s/{stem}/"
    target = f"{portal}#/help/{stem}"
    title = _esc(page_title(video))
    tags = [
        ("property", "og:type", "website"),
        ("property", "og:site_name", SITE_NAME),
        ("property", "og:title", page_title(video)),
        ("property", "og:description", page_description(video, section)),
        ("property", "og:url", url),
        ("property", "og:image", url + image),
        ("property", "og:image:type", "image/jpeg"),
        ("property", "og:image:width", width),
        ("property", "og:image:height", height),
        ("name", "twitter:card", "summary_large_image"),
        ("name", "robots", "noindex"),
    ]
    metas = "\n".join(f'<meta {kind}="{key}" content="{_esc(value)}">' for kind, key, value in tags)
    script = _REDIRECT % (json.dumps(portal), json.dumps(stem))
    return f"""<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
{metas}
<meta http-equiv="refresh" content="0;url={_esc(target)}">
<script>{script}</script>
</head>
<body>
<p><a href="{_esc(target)}">{title}</a></p>
</body>
</html>
"""


def _run(cmd, what):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{what}: {result.stderr.strip() or 'exit ' + str(result.returncode)}")
    return result.stdout


def extract_frame(mp4, jpg):
    """Write frame 0 of `mp4` to `jpg`, FRAME_WIDTH wide; return its (width, height)."""
    _run(["ffmpeg", "-v", "error", "-y", "-i", str(mp4), "-frames:v", "1",
          "-vf", f"scale={FRAME_WIDTH}:-2", "-q:v", "3", str(jpg)], f"cannot take a frame from {mp4}")
    size = Path(jpg).stat().st_size
    if size >= MAX_IMAGE_BYTES:
        raise RuntimeError(f"{jpg} is {size} bytes, over the {MAX_IMAGE_BYTES}-byte preview limit")
    out = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                "-of", "csv=p=0", str(jpg)], f"cannot read the size of {jpg}")
    width, height = out.strip().split(",")
    return int(width), int(height)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--site", default="site", help="the laid-out site: catalog.json and v/<file>.mp4")
    parser.add_argument("--help-base", default=HELP_BASE)
    parser.add_argument("--portal", default=PORTAL)
    args = parser.parse_args(argv)

    site = Path(args.site)
    pages = latest_by_stem(catalog.load(site / "catalog.json"))
    try:
        for key, (video, section) in sorted(pages.items()):
            out = site / "s" / key
            out.mkdir(parents=True, exist_ok=True)
            image = f"{video['file']}.jpg"
            width, height = extract_frame(site / "v" / f"{video['file']}.mp4", out / image)
            (out / "index.html").write_text(
                page_html(stem=key, video=video, section=section, image=image, width=width, height=height,
                          help_base=args.help_base, portal=args.portal),
                encoding="utf-8")
    except RuntimeError as e:
        print(f"::error::{e}")
        sys.exit(1)
    print(f"share pages: {len(pages)}")


if __name__ == "__main__":
    main()
