# Messenger previews for tutorial links — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a tutorial link shared in Telegram/WhatsApp shows the video's title and first frame, and opens the video in the portal.

**Architecture:** a new `tools/share_pages.py` in sy-help runs in the deploy after `tools.publish`, and writes `s/<stem>/index.html` (OG tags + redirect) and `s/<stem>/<file>.jpg` (frame 0) for the newest version of every catalogued video. The portal's share button then copies that URL.

**Tech Stack:** Python 3.12 + pytest, ffmpeg/ffprobe (sy-help); plain JS + `node --test`, pytest smoke (sy-subtitles).

**Spec:** `docs/superpowers/specs/2026-11-28-share-previews-design.md` (sy-help)

## Global Constraints

- Share URL: `https://sy-tools.github.io/sy-help/s/<stem>/`; `<stem>` = file without `-vN`.
- Portal target: `https://sy-tools.github.io/sy-subtitles/#/help/<stem>`, carrying only `q` and `f`.
- Image: frame 0, 1200 px wide, JPEG, < 300 KB, named `<file>.jpg` (not by stem).
- Page text in Ukrainian; every catalog string HTML-escaped; `<meta name="robots" content="noindex">`.
- No silent fallbacks: a frame that cannot be extracted fails the deploy.
- All code, comments, commit messages in English.

## Review Focus

1. A chronological "update" video with no title → page title `Оновлення на DD.MM.YYYY`, as the portal shows it (Task 1 test).
2. A title or description with `"`, `<`, `&` → escaped inside attributes and text (Task 1 test).
3. Both `intro` and `intro-v2` in the catalog → one page `s/intro/`, describing `intro-v2` (Task 1 test).
4. A shared `?q=` with Cyrillic or `&` → reaches the portal encoded, decoded back to the same query (Task 1 test on the redirect script: it uses `URLSearchParams`, never string concatenation of raw values).
5. A frame over 300 KB or an unreadable mp4 → exit 1 with `::error::` naming the file (Task 2 test).

---

## Part 1 — sy-help (worktree `sy-help-wt-share-previews`, branch `feat/share-previews`)

### Task 1: page model and HTML

**Files:**
- Create: `tools/share_pages.py`
- Test: `tests/test_share_pages.py`

**Interfaces:**
- Produces:
  - `stem(file: str) -> str` (`intro-v2` → `intro`)
  - `latest_by_stem(cat: dict) -> dict[str, tuple[dict, dict]]` — stem → (video, its section), newest version wins.
  - `page_title(video: dict) -> str`, `page_description(video: dict, section: dict) -> str`
  - `page_html(*, stem: str, video: dict, section: dict, image: str, width: int, height: int, help_base: str, portal: str) -> str`
  - constants `HELP_BASE = "https://sy-tools.github.io/sy-help/"`, `PORTAL = "https://sy-tools.github.io/sy-subtitles/"`

- [ ] **Step 1: failing tests**
  - `test_stem_strips_version_suffix`: `stem("intro-v2") == "intro"`, `stem("intro") == "intro"`, `stem("v2-intro") == "v2-intro"`.
  - `test_latest_by_stem_keeps_newest_version`: catalog with `intro`, `intro-v3`, `intro-v2`, `other` → keys `{"intro","other"}`, `intro` maps to `intro-v3`.
  - `test_title_falls_back_to_update_date`: `{"file":"u","date":"2026-11-23","title":{"uk":""}}` → `"Оновлення на 23.11.2026"`; no title and no date → the file name.
  - `test_description_uses_catalog_text_or_section_and_duration`: description.uk `"Текст"` → `"Текст"`; empty → `"Як працювати з порталом · 5:36 · SY Subtitles"` for `duration: 335.9`; no duration → `"Як працювати з порталом · SY Subtitles"`; 3725 s → `"1:02:05"`.
  - `test_page_carries_open_graph_tags`: `og:title`, `og:description`, `og:image` = `https://sy-tools.github.io/sy-help/s/intro/intro-v2.jpg`, `og:image:width` 1200, `og:image:height` 672 (as passed in), `og:image:type` `image/jpeg`, `og:url` = `.../s/intro/`, `og:type` `website`, `og:site_name` `SY Subtitles`, `twitter:card` `summary_large_image`, `robots` `noindex`, `<html lang="uk">`.
  - `test_page_redirects_to_portal_help_route`: contains `<meta http-equiv="refresh" content="0;url=https://sy-tools.github.io/sy-subtitles/#/help/intro">`, a visible `<a href=` to the same, and a script that builds the target with `URLSearchParams` keeping only `q` and `f`.
  - `test_page_escapes_catalog_text`: title `Він сказав "так" <b>&` → no raw `<b>` in output; attribute holds `&quot;так&quot; &lt;b&gt;&amp;`.
- [ ] **Step 2:** `python -m pytest tests/test_share_pages.py -q` → FAIL (module missing).
- [ ] **Step 3:** implement with `html.escape(..., quote=True)`; duration format identical to the portal's `formatDuration` (`m:ss`, `h:mm:ss`). The redirect script, inline, is the only JS:
  ```html
  <script>
  var from = new URLSearchParams(location.search), kept = new URLSearchParams();
  ['q', 'f'].forEach(function (k) { if (from.get(k)) kept.set(k, from.get(k)); });
  var qs = kept.toString();
  location.replace(PORTAL + (qs ? '?' + qs : '') + '#/help/' + STEM);
  </script>
  ```
  (`PORTAL`/`STEM` written in as JSON string literals via `json.dumps`.)
- [ ] **Step 4:** tests PASS.
- [ ] **Step 5:** commit `Add share-page model and HTML for tutorial previews`.

### Task 2: frames and CLI

**Files:**
- Modify: `tools/share_pages.py`
- Test: `tests/test_share_pages.py`

**Interfaces:**
- Consumes: Task 1.
- Produces: `extract_frame(mp4: Path, jpg: Path) -> tuple[int, int]` (writes frame 0 scaled `1200:-2`, returns ffprobe'd width/height, raises `RuntimeError` naming the file on ffmpeg failure or size ≥ `MAX_IMAGE_BYTES = 300_000`); CLI `python -m tools.share_pages --site DIR [--help-base URL] [--portal URL]` that reads `DIR/catalog.json` and `DIR/v/<file>.mp4`, writes `DIR/s/<stem>/{index.html,<file>.jpg}`, prints `::error::` and exits 1 on any `RuntimeError`.

- [ ] **Step 1: failing tests** (a fixture makes a 2 s `testsrc` mp4 at 1920×1076 with `ffmpeg -f lavfi`):
  - `test_extract_frame_writes_a_1200px_jpeg`: returns `(1200, 672)` (`-2` rounds to even), file starts with `\xff\xd8`, < 300 KB.
  - `test_extract_frame_fails_on_unreadable_video`: random bytes → `RuntimeError` containing the file name.
  - `test_cli_writes_a_page_and_frame_per_stem`: site with catalog `intro`, `intro-v2` and both mp4s → `s/intro/index.html` and `s/intro/intro-v2.jpg` exist, no `s/intro/intro.jpg`, page `og:image:height` = 672.
  - `test_cli_fails_when_a_frame_cannot_be_made`: one mp4 of random bytes → exit 1, `::error::` with the file name in stdout.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** implement (`subprocess.run([... "ffmpeg", "-v", "error", "-y", "-i", mp4, "-frames:v", "1", "-vf", "scale=1200:-2", "-q:v", "3", jpg])`, `ffprobe -show_entries stream=width,height`).
- [ ] **Step 4:** full suite `python -m pytest -q` → PASS.
- [ ] **Step 5:** commit `Write share pages and first-frame images in a CLI`.

### Task 3: deploy, CI, README

**Files:**
- Modify: `.github/workflows/deploy.yml`, `.github/workflows/ci.yml`, `README.md`

`robots.txt` stays as it is: crawlers read only `https://sy-tools.github.io/robots.txt`,
which is 404, so nothing blocks them (checked 2026-11-28).

- [ ] **Step 1:** deploy: after `tools.publish`, `command -v ffmpeg || (sudo apt-get update && sudo apt-get install -y ffmpeg)`, then `python -m tools.share_pages --site site`. CI: same install before pytest.
- [ ] **Step 2:** README "What is where": row `Share pages (messenger previews) | s/<stem>/ on the published site, built by tools/share_pages.py`; one "Why this shape" bullet: the hash never reaches a crawler, so a preview needs its own path.
- [ ] **Step 3:** `python -m pytest -q` PASS; run the CLI on a local copy of the real site (catalog + real mp4s from Pages) and inspect the output.
- [ ] **Step 4:** commit, push, open PR (sy-help). Merge only with the owner's explicit approval.

## Part 2 — sy-subtitles (worktree off `origin/main`, branch `feat/help-share-previews`)

### Task 4: share button copies the preview URL

**Files:**
- Modify: `site/js/help_videos.js` (`shareUrl`), `site/index.html:10553` (call site)
- Test: `tests/test_help_videos.js`

**Interfaces:**
- Produces: `shareUrl(origin, pathname, search, file, helpRepo)` — when `search` has neither `repo` nor `branch`: `pagesBase(helpRepo || DEFAULT_HELP_REPO) + 's/' + stem(file) + '/' + (q/f ? '?' + qs : '')`; otherwise today's portal-hash URL.

- [ ] **Step 1: failing tests** (rewrite the two existing cases):
  - production: `shareUrl('https://sy-tools.github.io', '/sy-subtitles/', '', 'intro')` → `https://sy-tools.github.io/sy-help/s/intro/`.
  - q/f carried: `'?q=puja&f=approved&state=x'` → `https://sy-tools.github.io/sy-help/s/intro/?q=puja&f=approved`.
  - versioned file: `'intro-v2'` → `.../s/intro/`.
  - other help repo: `helpRepo = 'me/help-test'` → `https://me.github.io/help-test/s/intro/`.
  - local stand unchanged: `?repo=…&code=abc&branch=dev` → `http://localhost:8000/?repo=sy-tools%2Fsy-subtitles&branch=dev#/help/intro`.
- [ ] **Step 2:** `node --test tests/test_help_videos.js` → FAIL.
- [ ] **Step 3:** implement; call site passes `HelpVideos.helpRepo(window)`.
- [ ] **Step 4:** `node --test tests/test_*.js`, `python -m pytest tests/ -m "not e2e"`, `pytest -m smoke` → PASS; open the help sheet via `tools.serve_auth_local`, press the link button, check the copied URL.
- [ ] **Step 5:** commit, push, PR — opened after the sy-help PR is merged and deployed (the URL must resolve before the button hands it out).

### Task 5: live check (after both merges)

- [ ] `curl -A "TelegramBot (like TwitterBot)"` and `curl -A "WhatsApp/2.23"` on `https://sy-tools.github.io/sy-help/s/motivation-and-limits/` → 200 with the OG tags; the image URL → 200 `image/jpeg`.
- [ ] Send the link to oneself in Telegram and WhatsApp; screenshot both cards.
