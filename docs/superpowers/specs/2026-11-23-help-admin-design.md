# Help tutorials: one home in sy-help, managed from the portal

Status: owner answers and passphrase gate folded in (builder check), awaiting approval, 2026-11-23.

## Intent

The SY Subtitles portal shows video tutorials in a sheet over the app (PR
sy-subtitles#1522). Today what a tutorial *is* lives in three places: the video
in sy-help's `media` release under an opaque id, the title/notes/order in the
portal's `site/js/help_videos.js`, the subtitles and their pipeline in the
portal repo (PR #1524), plus a local file mapping titles to ids. Adding one video
means touching all of them by hand.

The owner wants:

1. **One place.** Everything about the tutorials — sections, order, titles,
   descriptions, update notes, the video files, the subtitles and the pipeline
   that writes them — lives in `sy-tools/sy-help`. The portal only renders it.
2. **Managed from the portal.** An admin mode, visible only to the owner's
   signed-in account, edits all texts and order, and adds or replaces a video
   by picking a file — from a desktop or an iPhone.
3. **Readable names, no mapping file.** Opaque ids and `h1` refs are dropped:
   once the catalog is public they hide nothing.
4. **A video does not open in one click from the release page** (protection
   option A, chosen by the owner): the release holds scrambled `.bin` files; the
   Pages deploy restores plain mp4.
5. **Update notes in chronological order** (oldest first).

## Goals / non-goals / anti-goals

Goals: the five above; the subtitle pipeline keeps working unattended for every
new video; the owner never needs a terminal to add, retitle, reorder, replace
or remove a tutorial.

Non-goals (this round): editing subtitle text in the admin (re-run the pipeline
instead; hand edits stay a git operation); several admins or roles; real
secrecy of the videos (the Pages mp4 URL is public by design of option A);
offline admin.

Anti-goals: an admin that only *looks* restricted while anyone could write
(authority must stay with GitHub permissions); a second source of truth for
any tutorial field; new paid or separately-administered infrastructure.

## Constraints (measured 2026-11-23)

- `uploads.github.com` (release asset upload) answers the CORS preflight with
  400 and no CORS headers: **a browser cannot upload a release asset.**
- Git LFS: the batch endpoint's preflight with `Authorization` carries no CORS
  headers, and the S3 upload URL answers the preflight 403: **no LFS from a
  browser.**
- `api.github.com` allows any origin. `POST /git/blobs` accepted 40 MiB of
  random data (12 s) and refused 60/72/90/110 MiB ("input too large"). From
  Chromium on another origin, 30 MiB and 40 MiB blobs returned 201.
  → chunk size **30 MiB** (base64 makes the request ~40 MiB).
- Cloudflare Worker (free) caps a request body at 100 MB: not a relay for raw
  files.
- Release asset `application/octet-stream` + `nosniff` → WebKit will not play it;
  Pages serves `video/mp4` with ranges (why videos are published on Pages).
- Pages site ≤ 1 GB; CRF 30 screen recordings ≈ 2 MiB/min.
- Only `SlavaSubotskiy` has write access to sy-help (sole collaborator, admin);
  `main` is unprotected.
- The portal signs in as a GitHub App user (user-to-server token). Its effective
  permission is the intersection of the user's and the App installation's, so
  **the App must be installed on sy-help with Contents: write** (owner action).

## Approaches for adding a video (owner picked 1)

1. **Chunks into a temporary branch (picked).** The browser cuts the raw file
   into 30 MiB parts, commits them to `inbox/<slug>` via the Git Data API; a
   workflow assembles, encodes, scrambles, releases, catalogs, subtitles, and
   deletes the branch. Any browser, current encode quality, no new services.
   Cost: the raw file plus ~⅓ crosses the wire; unreachable blobs stay in the
   repo until GitHub garbage-collects them.
2. Encode in the browser (WebCodecs) and upload one ≤ 30 MiB file. Ten times
   less upload, but lower quality per byte, browser-dependent, slow on a phone.
3. Cloudflare R2 inbox with presigned URLs minted by the Worker. Clean, any
   size, but a bucket, keys and an authenticated endpoint to maintain.

## Design

### Repository layout (sy-help)

```
catalog.json                 the one source of every tutorial field
subs/<file>.uk.vtt|.en.vtt   subtitles, named after the video file
site/robots.txt              disallow all
tools/help_subtitles.py      moved from sy-subtitles (#1524), + tests
tools/scramble.py            .bin <-> .mp4
templates/help_subtitles_prompt.md
.github/workflows/deploy.yml   catalog + subs + decoded videos -> Pages
.github/workflows/ingest.yml   inbox/** branch -> release asset + catalog
.github/workflows/subtitles.yml  videos short of subtitles -> subs/
```

### Catalog (`catalog.json`)

JSON, not YAML: the browser reads and rewrites it without a parser, and a
round-trip cannot reformat what the owner did not touch.

```json
{
  "version": 1,
  "sections": [
    {
      "id": "guide",
      "title": {"uk": "Як користуватися", "en": "How to use"},
      "order": "manual",
      "videos": [
        {
          "file": "motivation-and-limits-2",
          "title": {"uk": "Мотивація та обмеження", "en": "Motivation and limits"},
          "description": {"uk": "…", "en": "…"},
          "duration": 312,
          "date": "2026-09-05",
          "notes": {"uk": ["…"], "en": ["…"]}
        }
      ]
    },
    {"id": "updates", "title": {…}, "order": "chronological", "videos": [ … ]}
  ]
}
```

- `file` is a readable Latin slug plus a version suffix. Pages serves
  `v/<file>.mp4`; the release holds `<file>.bin`; subtitles are
  `subs/<file>.<lang>.vtt`. Replacing a video bumps the suffix (`-2`, `-3`):
  browsers and the Pages CDN cache by URL, so a URL never changes content.
- `order: "chronological"` sorts by `date`, oldest first, in the portal;
  `manual` keeps array order. This is how "updates are chronological" is held
  by data, not by whoever typed the list.
- `duration` is written by ingest (ffprobe), never typed.
- English fields may be empty; the portal falls back to Ukrainian.
- **Numbering is derived, never typed** (owner, 2026-11-23: the current uneven
  numbering is not important, automatic is fine). The portal numbers sections
  1, 2, 3… and videos within a section 3.1, 3.2… by position; an update in a
  `chronological` section is titled from its `date` ("Оновлення на
  22.11.2026" / "Update of 22.11.2026") and needs no `title`. Titles hold only
  the subject; migration strips today's prefixes. Reordering in the admin
  therefore never leaves a stale number.

### Scrambling (option A)

`tools/scramble.py`: XOR with a keystream of SHA-256(constant ‖ counter),
same function both ways, constant in the repo. It is obfuscation: the point is
that a `.bin` from the release page is noise to a player, not that it cannot be
decoded. Deploy refuses a release asset not named `^[a-z0-9-]+\.bin$` and
publishes only the files the catalog references (an orphan is never public).

### Portal side (sy-subtitles)

- `help_videos.js` shrinks to: the catalog URL
  (`https://sy-tools.github.io/sy-help/catalog.json`), pure helpers (sort a
  section, pick a language with fallback, video and subtitle URLs), all
  node-tested. `HELP_SECTIONS`, `encodeHelpRef`/`decodeHelpRef` go.
- `help_sheet.js` renders from the fetched catalog; subtitles from
  `subs/<file>.<lang>.vtt` of the same origin. The auto-English/Ukrainian-off
  behaviour from #1524 stays.
- #1522 is reduced to sheet + SW media bypass + catalog fetch; #1524 is closed,
  its pipeline and VTTs move to sy-help.

### Passphrase gate

Opening the help sheet goes through the portal's existing passphrase gate
(`ensureUnlocked()` in `site/index.html`, `site/js/passphrase_gate.js`), the same phrase that
guards the translation pages (owner, 2026-11-23): locked → the gate prompt;
correct phrase → the sheet opens; cancel → nothing opens. An unlock is shared
with the rest of the portal (same `sy_gate` record), so a reviewer who already
entered it is not asked again. Like the rest of the gate this is soft: the
catalog and the Pages mp4 stay public files; it hides the tutorials from the
portal's casual visitor, not from someone with the URLs. The catalog is
fetched only after the gate opens, so a locked visitor's browser never even
requests it.

### Admin mode

Shown when the signed-in user has `permissions.push` on `sy-tools/sy-help`
(`GET /repos/sy-tools/sy-help`). That is GitHub's own answer, so the UI and the
real authority cannot disagree; nobody else ever sees the controls, and a forged
UI still cannot write.

In the help sheet, an "Edit" toggle switches to admin mode:

- **Texts:** inline edit of section and video titles, descriptions and notes,
  per language (uk/en tabs).
- **Order:** move up/down for videos in `manual` sections; date field for
  `chronological` ones; move a video between sections; add/rename/remove a
  section.
- **Save:** one commit of `catalog.json` via `PUT /contents` with the blob sha
  it was loaded from. A 409 means it changed underneath (another device, or an
  ingest finished): reload, show what changed, let the owner re-apply.
  Admin mode reads the catalog through the API (current `main`), not Pages, so
  it never edits a version older than what is committed.
- **Add video:** pick a file, fill section/title/description. The browser
  computes SHA-256 of the whole file, cuts it into 30 MiB parts, creates one
  blob per part (sequential, with retry per part and a progress bar), then one
  tree + commit + ref `inbox/<slug>` holding `parts/000…` and `entry.json`
  (target section, texts, sha256, size, and `replaces: <file>` when replacing).
  A file is read part by part (`Blob.slice`), so a 300 MB file from an iPhone's
  Photos does not sit in memory whole. Files over **1 GB are refused**; no
  other restriction (owner, 2026-11-23). Raw bytes stay in the repo as
  unreachable blobs after the branch is deleted, until GitHub collects them:
  the owner accepts that growth.
- **Replace video:** same flow from an existing entry; texts stay.
- **Remove video:** removes the catalog entry; deploy stops publishing it;
  ingest's cleanup deletes the orphan asset and subtitles later.
- **Status:** after upload, the entry shows "processing" by polling the
  workflow runs for branch `inbox/<slug>` (needs Actions: read on the App), then
  appears once the catalog commit lands; Pages follows ~1 min later.

### Ingest workflow (`ingest.yml`, on push to `inbox/**`)

1. Concatenate parts; verify size and SHA-256 against `entry.json`; ffprobe.
2. Encode with the recipe in README (H.264 CRF 30, AAC 96k mono, faststart).
3. Scramble to `<file>.bin`, upload to the `media` release.
4. Insert or update the catalog entry (with `duration`), commit to `main` with
   `GITHUB_TOKEN` (no protection on `main`).
5. Delete the `inbox/<slug>` branch; on replace, delete the old asset and its
   subtitles.
6. **Publish first, subtitle after.** Ingest dispatches `deploy.yml` on
   `main` (`workflow_dispatch` with `GITHUB_TOKEN` does start a run; a push
   by it does not, and the `github-pages` environment accepts deployments
   only from `main`, so a reusable call from the inbox branch would be
   refused). It then dispatches `subtitles.yml`, which commits `subs/` and
   dispatches `deploy.yml` again. A video goes live minutes after upload;
   a failed subtitle run never hides it. The portal shows a video without
   subtitle tracks until they exist.

On failure the branch stays (the parts are not lost) and the run is red; the
admin shows the failure with a link to the run.

### Subtitles (`subtitles.yml`)

The #1524 pipeline, moved: whisper → `help_subtitles cues` → Claude writes
`uk.json`/`en.json` (restricted tools, no shell) → `help_subtitles vtt` →
commit `subs/`. It checks out `sy-tools/sy-subtitles` read-only for
`site/index.html` (UI strings, so subtitles name buttons as the reader sees
them) and `glossary/`. Triggered by ingest, and by dispatch (`select:
missing|all|<files>`). Needs the secret `CLAUDE_CODE_OAUTH_TOKEN` in sy-help
(owner action).

### Migration

Re-encode nothing: the 13 current mp4s are renamed to readable `file` slugs,
scrambled and re-uploaded; the old id assets deleted; the catalog is generated
once from today's `help_videos.js` + `Tutorials/sy-help-videos.json`; the 13
VTT pairs from #1524 are renamed to the new files. The local mapping file is
then deleted.

## Staging

Every repo name is configuration, not a constant: the portal's catalog/API
base and the workflows read it. End-to-end checks (real commits, inbox
branches, release assets, Pages deploys, Claude runs) go against
`sy-tools/sy-help-staging` (public, Pages from workflow, owner-approved
2026-11-23), never against the live sy-help; `serve_auth_local` gets a way to
point the local portal at it.

## Owner actions

1. Install the portal's GitHub App on `sy-tools/sy-help` and
   `sy-tools/sy-help-staging` (Contents: write, Actions: read).
2. Add secret `CLAUDE_CODE_OAUTH_TOKEN` to the **`main` environment** of both
   (environment created 2026-11-23, deployment branches: `main` only). Only
   `subtitles.yml`, which runs on `main`, declares `environment: main`;
   `ingest.yml` runs on `inbox/*` branches written from the browser and must
   never see the token, so it needs no secret and declares no environment.

## Left to the builder

Slug generation from the title subject (transliteration) and collision handling; exact
admin layout within the design system (styleguide entries required); retry and
resume details of the upload; how the deploy step's size guard counts decoded
files; test split between node (portal helpers, upload chunking) and pytest
(scramble round-trip, catalog validation, ingest steps).
