# Help tutorials in sy-help, managed from the portal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move every tutorial field, file and the subtitle pipeline into sy-help behind one `catalog.json`, and let the owner edit texts and add/replace/remove videos from the portal's help sheet.

**Architecture:** sy-help holds `catalog.json`, `subs/`, scrambled `.bin` files in the `media` release, and three workflows (deploy, ingest, subtitles). The portal fetches `catalog.json` from Pages after the passphrase gate and renders it; an admin mode (shown on `permissions.push` for the help repo) rewrites `catalog.json` via the Contents API and uploads raw files as 30 MiB blobs to an `inbox/<file>` branch that `ingest.yml` turns into a release asset.

**Tech Stack:** Python 3.12 + pytest (sy-help tools), GitHub Actions, plain-ES5 browser modules tested with `node --test` (portal), Playwright smoke (portal).

**Spec:** `sy-help/docs/superpowers/specs/2026-11-23-help-admin-design.md`

## Global Constraints

- Repos: help content `sy-tools/sy-help`; staging `sy-tools/sy-help-staging`; portal `sy-tools/sy-subtitles` (branch `feat/help-videos`, PR #1522). PR #1524 is closed, not merged.
- Every repo name is configuration: portal default `sy-tools/sy-help`, override `window.__SY_HELP_REPO` (injected by `serve_auth_local --help-repo`); workflows use `${{ github.repository }}`.
- Pages URL of a help repo `owner/name` is `https://<owner>.github.io/<name>/`; videos `v/<file>.mp4`; subtitles `subs/<file>.<lang>.vtt`; release asset `<file>.bin` in release `media`.
- `file` matches `^[a-z0-9]+(?:-[a-z0-9]+)*$`; a replaced video gets the next `-N` suffix; a URL never changes content.
- Chunk size 30 MiB (31457280 bytes); files over 1 GiB (1073741824 bytes) refused.
- Encode: `ffmpeg -i in -map 0:v:0 -map 0:a:0 -r 30 -c:v libx264 -preset slow -crf 30 -pix_fmt yuv420p -profile:v high -c:a aac -b:a 96k -ac 1 -map_metadata -1 -movflags +faststart out.mp4`.
- Scramble: XOR with SHA-256(`b"sy-help/scramble/v1"` + counter as 8-byte big-endian) blocks; same function both ways.
- Only `subtitles.yml` declares `environment: main` (holds `CLAUDE_CODE_OAUTH_TOKEN`); `ingest.yml` declares no environment.
- Help sheet opens only through `ensureUnlocked()`; the catalog is fetched after it resolves true.
- Numbering derived: sections `1..n`; videos in `manual` sections `s.i`; `chronological` sections sorted by `date` ascending, titled `Оновлення на DD.MM.YYYY` / `Update of DD.MM.YYYY`.
- English in code, commits, PRs; signed commits; `gh auth status` = SlavaSubotskiy before every push; never merge without the owner's approval.

## Review Focus

1. Catalog saved from a stale copy (another device or a finished ingest wrote first) → 409 must surface as "changed, reloaded", never overwrite. Test in Task 8.
2. Upload interrupted midway (tab closed, network drop) → re-picking the same file resumes or restarts cleanly; a half-written inbox branch must not trigger ingest (ref is created last). Test in Task 8.
3. A catalog entry whose video has no subtitles yet, or whose `en` texts are empty → sheet renders with Ukrainian fallback and no `<track>`. Test in Task 6.
4. Ingest re-run on the same inbox branch (retry after a red run) → idempotent: asset upload uses `--clobber`, catalog upsert by `file`. Test in Task 3.
5. Portal on localhost (cross-origin to Pages) → `<video crossorigin="anonymous">` so tracks load; Pages sends `access-control-allow-origin: *`. Test in Task 6.

---

## Part A — sy-help (worktree on branch `feat/catalog`)

### Task 1: Catalog model and scrambler

**Files:**
- Create: `tools/__init__.py`, `tools/catalog.py`, `tools/scramble.py`, `tests/test_catalog.py`, `tests/test_scramble.py`, `requirements-dev.txt` (`pytest`), `.github/workflows/ci.yml` (pytest + `node --test` none here)

**Interfaces — Produces:**
- `scramble.transform(data: bytes, offset: int = 0) -> bytes`; CLI `python -m tools.scramble IN OUT` (streams 1 MiB blocks).
- `catalog.load(path) -> dict`, `catalog.validate(cat: dict) -> list[str]` (errors), `catalog.files(cat) -> list[str]`, `catalog.upsert(cat, section_id: str, entry: dict, replaces: str | None) -> dict`, `catalog.remove_file(cat, file) -> dict`, `catalog.set_subtitles(cat, file, langs: list[str]) -> dict`, `catalog.dump(cat) -> str` (2-space JSON, `ensure_ascii=False`, trailing newline).
- Entry keys: `file, title{uk,en}, description{uk,en}, date (YYYY-MM-DD|absent), duration (float), notes{uk:[],en:[]}, subtitles [langs]`. Section keys: `id, title{uk,en}, order ('manual'|'chronological'), videos[]`.

- [ ] Tests: `transform(transform(x)) == x` for random 3 MiB; `transform(x)[:8] != x[:8]`; streaming CLI equals one-shot; `validate` flags duplicate `file`, bad `file` pattern, unknown `order`, chronological entry without `date`, `version != 1`; `upsert` replacing `a-2` puts the new entry at the same index keeping texts unless given; `upsert` new appends; `remove_file` drops it.
- [ ] Run `pytest -q` → fail; implement; pass; commit `Add catalog model and the release scrambler`.

### Task 2: Deploy from catalog

**Files:** Modify `.github/workflows/deploy.yml`; Create `tools/publish.py`, `tests/test_publish.py`

**Interfaces — Consumes:** Task 1. **Produces:** `publish.plan(cat, assets: list[str]) -> {"publish": [file], "missing": [file], "orphans": [asset]}`; CLI `python -m tools.publish --catalog catalog.json --assets DIR --out site` (writes `site/v/<file>.mp4` decoded, copies `catalog.json`, `subs/`; exits 1 on any `missing` or validate error; prints orphans).

- [ ] Tests: plan with an orphan asset and a missing one; asset names not matching `^[a-z0-9-]+\.bin$` are refused (exit 1).
- [ ] deploy.yml: `gh release download media --pattern '*.bin'` → `publish` → size guard (<1000 MiB) → pages upload; triggers `push: main`, `workflow_dispatch`.
- [ ] Commit `Publish only what the catalog lists, decoded from the release`.

### Task 3: Ingest

**Files:** Create `.github/workflows/ingest.yml`, `tools/ingest.py`, `tests/test_ingest.py`

**Interfaces — Produces:** inbox branch layout `inbox/entry.json` + `inbox/parts/000..NNN`; `entry.json = {section, file, replaces|null, title, description, date|null, notes, size, sha256}`. `ingest.assemble(parts_dir, out, size, sha256)` raises on mismatch; `ingest.apply(cat, entry, duration) -> dict` (calls `catalog.upsert`, sets `duration`, keeps existing `subtitles` only when not replacing).

- [ ] Tests: assemble ok / size mismatch / sha mismatch; apply new and replace; apply twice is idempotent.
- [ ] ingest.yml (on push `inbox/**`; `permissions: contents: write, actions: write`; no environment): checkout ref → assemble → ffprobe duration → encode → scramble → `gh release upload media <file>.bin --clobber` → checkout `main` into `main/`, `ingest apply`, commit + push with 3 rebase retries → on replace delete old asset and `subs/<old>.*` → `git push origin --delete <ref>` → `gh workflow run deploy.yml --ref main` → `gh workflow run subtitles.yml --ref main -f select=<file>`.
- [ ] Commit `Turn an inbox branch into a published video`.

### Task 4: Subtitles pipeline moved

**Files:** Create from sy-subtitles#1524: `tools/help_subtitles.py`, `tests/test_help_subtitles.py`, `templates/help_subtitles_prompt.md`, `.github/workflows/subtitles.yml`

**Interfaces — Consumes:** Task 1 (`set_subtitles`). **Changes from #1524:** refs → `file`; `pending(files, catalog, select)` reads `subtitles` from the catalog instead of a directory manifest (`manifest` subcommand removed); `is_hallucination` inlined (text empty or only `.… `); `meta.json = {title (uk, derived for updates), file}`; video from Pages `v/<file>.mp4`.

- [ ] Port the 24 tests with renamed fields; add `pending` tests against a catalog; pass.
- [ ] subtitles.yml: `workflow_dispatch` (`select`, `model`, `oauth_token`), jobs discover → subtitles (`environment: main`, checks out `sy-tools/sy-subtitles` to `portal/` for `tools.whisper_run`, `site/index.html`, `glossary/`; agent `--allowedTools "Read,Glob,Grep,Edit(help-work/**),Write(help-work/**)"`) → commit (`subs/*.vtt`, `catalog set-subtitles`, push to main with retries, then `gh workflow run deploy.yml`).
- [ ] Commit `Move the tutorial subtitle pipeline here`.

### Task 5: Migration of the 13 videos

**Files:** Create `catalog.json`, `subs/*.vtt` (renamed from #1524), `tools/migrate_once.py` is NOT committed (scratchpad).

- [ ] Map old id → new `file` (slugs: `motivation-and-limits`, `components-github-glossary-automation`, `components-translation-portal`, `security`, `github-sign-up`, `taking-material-into-work`, `adding-materials-and-autotranslation`, `view-translation-mode`, `review-translation-mode`, `finalization-and-amruta-delivery`, `login`, `update-2026-09-05`, `update-2026-11-22`); titles without number prefixes; English titles; updates `chronological` with notes uk/en; `subtitles: ["uk","en"]` on all.
- [ ] `python -m tools.catalog` validate passes; scramble each mp4 from scratchpad `media/` → upload `.bin` to staging, deploy staging, verify a video and a VTT over HTTP; then the same on sy-help, delete old `<id>.mp4` assets.
- [ ] README rewritten (catalog, admin, ingest, scramble, staging, secrets/environment). Commit `Catalog the thirteen tutorials under readable names`; open PR, CI green.

## Part B — portal (worktree `.worktrees/help-videos`, branch `feat/help-videos`)

### Task 6: Catalog rendering

**Files:** Modify `site/js/help_videos.js`, `site/js/help_sheet.js`, `tests/test_help_videos.js`, `tests/test_help_sheet.js`

**Interfaces — Produces (`HelpVideos`):** `helpRepo() -> 'owner/name'` (from `window.__SY_HELP_REPO` or default), `pagesBase(repo) -> url`, `catalogUrl(repo)`, `videoUrl(repo, file)`, `subtitleUrl(repo, file, lang)`, `localized(field, lang) -> string|array` (uk fallback), `orderedSections(cat) -> sections with videos sorted and each video given `number` ('3.2') and `displayTitle{uk,en}`)`, `formatDuration(s)`. Removed: `encodeHelpRef`, `decodeHelpRef`, `HELP_SECTIONS`, `helpVideoUrl`.
`HelpSheet.render(root, cat, uiLang, repo)`; `subtitleTracks(repo, file, langs, uiLang)`; `applySubtitleLanguage` unchanged.

- [ ] Tests: numbering `1`, `2.1`…; chronological sorts oldest first and derives the title; uk fallback for empty en; track default only for `en` UI; video has `crossorigin=anonymous` (jsdom-free: assert via a fake `document` as existing tests do); entry without `subtitles` → no tracks.
- [ ] Commit `Render the help sheet from the sy-help catalog`.

### Task 7: Wiring, gate, SW, smoke

**Files:** Modify `site/index.html` (`SPA.openHelp` → `ensureUnlocked().then(ok => ok && open)`; fetch catalog with `cache: 'no-cache'`, error state text `help.error`), `site/sw.js` (cache version +1, precache unchanged), `tests/test_spa_boot_smoke.py` (route `**/catalog.json` to a fixture with 3 videos; gate test: locked → prompt, cancel keeps sheet closed), `tools/serve_auth_local.py` (+`--help-repo`, injects `window.__SY_HELP_REPO`), its test.

- [ ] Smoke + JS + fast lane green; open in browser against staging.
- [ ] Commit `Open the tutorials through the passphrase gate, from the catalog`.

### Task 8: Admin logic

**Files:** Create `site/js/help_admin.js`, `tests/test_help_admin.js`

**Interfaces — Produces (`HelpAdmin`):**
- Edits (pure, return new catalog): `moveVideo(cat, file, delta)`, `moveToSection(cat, file, sectionId)`, `setText(cat, path: [sectionId, file|null, field, lang], value)`, `addSection(cat, {id,title,order})`, `removeSection(cat, id)` (only empty), `removeVideo(cat, file)`.
- `slugify(title) -> string` (Ukrainian → Latin per the national transliteration table, lowercase, `-` joined, ≤ 48 chars), `nextFile(cat, base, replaces|null) -> string`.
- `loadCatalog(api, token, f) -> {cat, sha}` (Contents API on `main`), `saveCatalog(api, token, cat, sha, message, f) -> newSha`; 409/422 → `Error{code:'stale'}`.
- `uploadVideo(api, token, file: Blob, entry, onProgress, f) -> branch`: sha256 of file (streamed via `crypto.subtle` over parts, whole-file digest computed with an incremental JS SHA-256 since SubtleCrypto is one-shot), blobs per 30 MiB part with 3 retries, tree with `base_tree` = main's tree adding `inbox/entry.json` + `inbox/parts/NNN`, commit with parent main head, ref `inbox/<file>` created LAST.
- `ingestStatus(api, token, branch, f) -> 'queued'|'running'|'failed'|'done'` (runs on that branch; branch gone + catalog has file = done).
- [ ] Tests with a fake fetch: edits; slugify(`Оновлення на 22.11.2026`) = `onovlennia-na-22-11-2026`; nextFile bumps `x-2`→`x-3` and avoids collisions; save 409 → stale; upload makes N blob calls for N parts, ref call last, retries a failed blob, refuses > 1 GiB before any request; status mapping.
- [ ] Commit `Add the help admin's catalog edits and video upload`.

### Task 9: Admin UI

**Files:** Modify `site/js/help_sheet.js` (admin render), `site/index.html` (Edit toggle shown when `getRepoPermissions(helpApi).push`, i18n keys `help.admin.*` uk/en), `site/css/components.css` (`.help-admin*`), `site/styleguide.html` ("Help admin" section), `tests/test_spa_boot_smoke.py` (admin hidden without push; with mocked push: edit title → PUT body carries it; upload form refuses > 1 GiB).

- [ ] UI: Edit toggle; per video: title/description/notes fields (uk/en tabs), ↑ ↓, section select, Replace, Remove; per section: title, add/remove; "Add video" form (file, section, title, description, date for chronological); Save button with dirty state; upload progress bar and status line with run link.
- [ ] Smoke + browser check on staging with a real 60 MB upload end to end (ingest → deploy → subtitles → visible with tracks).
- [ ] Commit `Manage the tutorials from the help sheet`.

### Task 10: Close out

- [ ] sy-subtitles: remove `site/help/subs/`, `help-subtitles.yml`, `tools/help_subtitles.py` from #1522's branch if present; CLAUDE.md/ARCHITECTURE.md entries point to sy-help; `tests/test_claude_md_lockstep.py` green.
- [ ] Close #1524 with a comment linking the sy-help PR. Update #1522 body.
- [ ] Delete `SY Subtitles Portal/Tutorials/sy-help-videos.json`. Update memory.
