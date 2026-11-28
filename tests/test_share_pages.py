import json
import os
import re
import shutil
import subprocess
import sys

import pytest

from tools import share_pages

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECTION = {"id": "guide", "title": {"uk": "Як працювати з порталом", "en": "How to work"}, "order": "manual"}


def video(file, **extra):
    v = {"file": file, "title": {"uk": file, "en": file}}
    v.update(extra)
    return v


def catalog(*sections):
    return {"version": 1, "sections": list(sections)}


def meta(html, prop):
    m = re.search(r'<meta (?:property|name)="%s" content="([^"]*)">' % re.escape(prop), html)
    assert m, f"no meta {prop} in page"
    return m.group(1)


def page(**overrides):
    args = dict(stem="intro", video=video("intro-v2", title={"uk": "Вступ"}, duration=335.9),
                section=SECTION, image="intro-v2.jpg", width=1200, height=672,
                help_base=share_pages.HELP_BASE, portal=share_pages.PORTAL)
    args.update(overrides)
    return share_pages.page_html(**args)


def test_stem_strips_version_suffix():
    assert share_pages.stem("intro-v2") == "intro"
    assert share_pages.stem("intro") == "intro"
    assert share_pages.stem("v2-intro") == "v2-intro"


def test_latest_by_stem_keeps_newest_version():
    other = dict(SECTION, id="other", videos=[video("other")])
    cat = catalog(dict(SECTION, videos=[video("intro"), video("intro-v3"), video("intro-v2")]), other)
    out = share_pages.latest_by_stem(cat)
    assert set(out) == {"intro", "other"}
    v, section = out["intro"]
    assert v["file"] == "intro-v3"
    assert section["id"] == "guide"
    assert out["other"][1]["id"] == "other"


def test_title_falls_back_to_update_date():
    assert share_pages.page_title(video("u", date="2026-11-23", title={"uk": ""})) == "Оновлення на 23.11.2026"
    assert share_pages.page_title({"file": "u"}) == "u"
    assert share_pages.page_title(video("intro", title={"uk": "Вступ"})) == "Вступ"


def test_description_uses_catalog_text_or_section_and_duration():
    assert share_pages.page_description(video("a", description={"uk": "Текст"}), SECTION) == "Текст"
    assert (share_pages.page_description(video("a", description={"uk": ""}, duration=335.9), SECTION)
            == "Як працювати з порталом · 5:36 · SY Subtitles")
    assert share_pages.page_description(video("a"), SECTION) == "Як працювати з порталом · SY Subtitles"
    assert share_pages.page_description(video("a", duration=3725), SECTION) == "Як працювати з порталом · 1:02:05 · SY Subtitles"


def test_page_carries_open_graph_tags():
    html = page()
    assert '<html lang="uk">' in html
    assert "<title>Вступ</title>" in html
    assert meta(html, "og:title") == "Вступ"
    assert meta(html, "og:description") == "Як працювати з порталом · 5:36 · SY Subtitles"
    assert meta(html, "og:image") == "https://sy-tools.github.io/sy-help/s/intro/intro-v2.jpg"
    assert meta(html, "og:image:width") == "1200"
    assert meta(html, "og:image:height") == "672"
    assert meta(html, "og:image:type") == "image/jpeg"
    assert meta(html, "og:url") == "https://sy-tools.github.io/sy-help/s/intro/"
    assert meta(html, "og:type") == "website"
    assert meta(html, "og:site_name") == "SY Subtitles"
    assert meta(html, "twitter:card") == "summary_large_image"
    assert meta(html, "robots") == "noindex"


def test_page_redirects_by_script_never_by_meta_refresh():
    html = page()
    target = "https://sy-tools.github.io/sy-subtitles/#/help/intro"
    assert "http-equiv" not in html
    assert f'<a href="{target}">' in html
    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    assert "URLSearchParams" in script
    assert "['q', 'f']" in script
    assert '"https://sy-tools.github.io/sy-subtitles/"' in script
    assert '"intro"' in script


def test_page_escapes_catalog_text():
    html = page(video=video("intro-v2", title={"uk": 'Він сказав "так" <b>&'}))
    assert "<b>" not in html
    assert meta(html, "og:title") == "Він сказав &quot;так&quot; &lt;b&gt;&amp;"


def make_mp4(path, source="testsrc=size=1920x1076:rate=10:duration=1"):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", source, "-pix_fmt", "yuv420p", str(path)],
                   check=True)


@pytest.fixture(scope="module")
def mp4(tmp_path_factory):
    path = tmp_path_factory.mktemp("video") / "intro.mp4"
    make_mp4(path)
    return path


def test_extract_frame_writes_a_1200px_jpeg(mp4, tmp_path):
    jpg = tmp_path / "intro.jpg"
    assert share_pages.extract_frame(mp4, jpg) == (1200, 672)
    data = jpg.read_bytes()
    assert data[:2] == b"\xff\xd8"
    assert len(data) < share_pages.MAX_IMAGE_BYTES == 300_000


def test_extract_frame_fits_a_portrait_video_in_the_box(tmp_path):
    make_mp4(tmp_path / "tall.mp4", "testsrc=size=1080x2340:rate=10:duration=1")
    assert share_pages.extract_frame(tmp_path / "tall.mp4", tmp_path / "tall.jpg") == (554, 1200)


def test_extract_frame_lowers_quality_before_giving_up(tmp_path):
    make_mp4(tmp_path / "noise.mp4", "color=gray:size=1920x1076:rate=10:duration=1,noise=alls=60:allf=t")
    assert share_pages.extract_frame(tmp_path / "noise.mp4", tmp_path / "noise.jpg") == (1200, 672)
    assert (tmp_path / "noise.jpg").stat().st_size < share_pages.MAX_IMAGE_BYTES


def test_extract_frame_fails_on_unreadable_video(tmp_path):
    bad = tmp_path / "broken.mp4"
    bad.write_bytes(os.urandom(4000))
    with pytest.raises(RuntimeError, match="broken.mp4"):
        share_pages.extract_frame(bad, tmp_path / "broken.jpg")


def test_extract_frame_refuses_an_image_over_the_limit(mp4, tmp_path, monkeypatch):
    monkeypatch.setattr(share_pages, "MAX_IMAGE_BYTES", 100)
    with pytest.raises(RuntimeError, match="intro.jpg"):
        share_pages.extract_frame(mp4, tmp_path / "intro.jpg")


def run_cli(site, *extra):
    return subprocess.run([sys.executable, "-m", "tools.share_pages", "--site", str(site), *extra],
                          cwd=ROOT, capture_output=True, text=True)


def site_with(tmp_path, files, mp4_for):
    site = tmp_path / "site"
    (site / "v").mkdir(parents=True)
    (site / "catalog.json").write_text(
        json.dumps(catalog(dict(SECTION, videos=[video(f) for f in files]))), encoding="utf-8")
    for f in files:
        mp4_for(site / "v" / f"{f}.mp4")
    return site


def test_cli_writes_a_page_and_frame_per_stem(mp4, tmp_path):
    site = site_with(tmp_path, ["intro-v2", "other"], lambda p: shutil.copyfile(mp4, p))
    result = run_cli(site)
    assert result.returncode == 0, result.stdout + result.stderr
    html = (site / "s" / "intro" / "index.html").read_text(encoding="utf-8")
    assert (site / "s" / "intro" / "intro-v2.jpg").exists()
    assert (site / "s" / "other" / "other.jpg").exists()
    assert meta(html, "og:image") == "https://sy-tools.github.io/sy-help/s/intro/intro-v2.jpg"
    assert meta(html, "og:image:height") == "672"


def test_cli_publishes_under_the_given_help_base(mp4, tmp_path):
    site = site_with(tmp_path, ["intro"], lambda p: shutil.copyfile(mp4, p))
    result = run_cli(site, "--help-base", "https://me.github.io/help-staging")
    assert result.returncode == 0, result.stdout + result.stderr
    html = (site / "s" / "intro" / "index.html").read_text(encoding="utf-8")
    assert meta(html, "og:url") == "https://me.github.io/help-staging/s/intro/"
    assert meta(html, "og:image") == "https://me.github.io/help-staging/s/intro/intro.jpg"


def test_cli_fails_when_a_frame_cannot_be_made(tmp_path):
    site = site_with(tmp_path, ["broken"], lambda p: p.write_bytes(os.urandom(4000)))
    result = run_cli(site)
    assert result.returncode == 1
    assert "::error::" in result.stdout
    assert "broken.mp4" in result.stdout
