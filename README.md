# sy-help

Everything about the video tutorials of the
[SY Subtitles portal](https://sy-tools.github.io/sy-subtitles/): what they are,
the video files, their subtitles and the pipeline that writes them. The portal
only renders what this repository publishes.

The owner manages it from the portal: the help sheet's **Edit** mode (shown to
whoever can push here) edits texts and order and adds, replaces or removes
videos. Nothing below needs doing by hand in normal use.

## What is where

| What | Where |
|---|---|
| Sections, order, titles, descriptions, notes, durations, subtitle languages | `catalog.json` (`tools/catalog.py` is its model and validator) |
| Videos | release `media`, as `<file>.bin` (scrambled) |
| Subtitles | `subs/<file>.<lang>.vtt` |
| Published site | `https://sy-tools.github.io/sy-help/`: `catalog.json`, `subs/`, `v/<file>.mp4` |

The portal and this site share the origin `sy-tools.github.io`, so the portal
reads the catalog and the subtitle tracks without CORS.

## Why this shape

- **Pages, not release download links.** A release asset is served as
  `application/octet-stream` with `nosniff`, and Safari, and so every browser
  on an iPhone, will not play it. Pages serves `video/mp4` and answers range
  requests, so seeking works everywhere.
- **Videos never enter git**; they live in the `media` release and can be
  replaced without growing the history forever.
- **Scrambled in the release.** A plain mp4 on the release page opens in a
  player with one click. `tools/scramble.py` XORs it with a fixed keystream, so
  the `.bin` is noise to a player; the deploy restores the mp4. This is
  obfuscation, not secrecy: the key is in this public repository, and the
  published mp4 is public at its URL. The portal hides the tutorials behind its
  passphrase gate, which is just as soft.
- **Only catalogued files are published.** The deploy decodes the assets the
  catalog lists and nothing else, so a replaced or removed recording stops
  being public with the next deploy.
- **A file name never changes content.** Browsers and the Pages CDN cache by
  URL, so a replacement gets a new name (`intro` → `intro-2`).

## How a video gets here

The portal's admin cannot upload a release asset: `uploads.github.com`
answers no CORS preflight, and neither does Git LFS. `api.github.com` does,
and accepts a blob of up to about 40 MiB. So the admin cuts the raw file into
30 MiB parts and commits them, with `inbox/entry.json`, to a branch
`inbox/<file>`. Then:

1. **`ingest.yml`** (on that push) rebuilds the file, checks its size and
   SHA-256, encodes it (below), uploads it scrambled to `media`, adds the entry
   to `catalog.json` on `main`, deletes the branch, and dispatches the next two.
   It holds no secret: its branch was written from a browser.
2. **`deploy.yml`** lays out the site with `tools/publish.py` and publishes it.
   The video is live a few minutes after the upload.
3. **`subtitles.yml`** writes Ukrainian and English subtitles (whisper cuts the
   cues, Claude writes each cue's text, `tools/help_subtitles.py` puts it back
   on the timings), commits `subs/`, records the languages in the catalog, and
   deploys again. Only this workflow holds `CLAUDE_CODE_OAUTH_TOKEN`, through
   the `main` environment, which accepts runs from `main` alone.

A failed ingest leaves its branch, and so the upload: re-run it from Actions.

Encode recipe (screen recordings come out at about 2 MiB per minute, so the
1 GB Pages limit holds about 9 hours; the deploy fails before crossing it):

```bash
ffmpeg -i in.mp4 -map 0:v:0 -map 0:a:0 -r 30 \
  -c:v libx264 -preset slow -crf 30 -pix_fmt yuv420p -profile:v high \
  -c:a aac -b:a 96k -ac 1 -map_metadata -1 -movflags +faststart out.mp4
```

## By hand

```bash
python -m tools.catalog validate                     # what CI checks
gh workflow run subtitles.yml -f select=all          # redo every subtitle
gh workflow run deploy.yml                           # republish
python -m tools.scramble in.mp4 out.bin              # same command both ways
```

## Staging

`sy-tools/sy-help-staging` is a copy for end-to-end checks of the admin and the
workflows. Point a local portal at it with
`python -m tools.serve_auth_local --help-repo sy-tools/sy-help-staging` in
sy-subtitles. Nothing names the repository: the workflows use
`github.repository`, and the portal reads its help repository from
configuration.

## Setup a new copy needs

- Pages: build from GitHub Actions.
- A release tagged `media`.
- Environment `main` (deployment branches: `main`) with the secret
  `CLAUDE_CODE_OAUTH_TOKEN`.
- The portal's GitHub App (`sy-subtitles-review`) installed on the repository,
  so the admin can write with the owner's sign-in.
