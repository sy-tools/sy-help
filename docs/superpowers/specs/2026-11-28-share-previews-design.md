# Messenger previews for tutorial links — design

## Why

A tutorial is shared as a portal link, `…/sy-subtitles/index.html?q=…&f=…#/help/<file>`.
Telegram and WhatsApp show no preview for it: everything after `#` never reaches
the server, so their crawlers fetch the same portal page for every video; that
page carries no `og:` tags and runs its UI in JavaScript the crawlers do not
execute.

Goal: a shared tutorial link shows, in Telegram and WhatsApp, a card with that
video's title and its first frame, and a click still lands on the video in the
portal, behind the passphrase gate.

## Goals / non-goals / anti-goals

- Goal: one stable share URL per tutorial, with a per-video preview.
- Goal: a newly added or replaced video gets its preview from the same deploy
  that publishes it — nothing to do by hand.
- Non-goal: previews for talk links (preview/review of subtitles).
- Non-goal: other messengers; they may work as a side effect, not tested.
- Anti-goal: anything that lets search engines index the tutorials or the portal.
- Anti-goal: a preview that drifts from the catalog (stale title, old frame).

## Approaches

- **A — share pages built by the sy-help deploy (chosen).** `tools.publish`
  already holds the catalog and the decoded videos; it writes one static page
  and one frame per video. A new video gets its preview from the deploy that
  publishes it.
- B — the same pages on the portal's own site. Rejected: the portal deploys
  only on `site/**` pushes, so a new tutorial would wait for an unrelated portal
  deploy, or need a cross-repo dispatch plus downloading the videos there.
- C — a Cloudflare Worker rendering tags on the fly. Rejected: a new hosting
  dependency and another domain, for what is a static catalog.

## Design

**Share URL:** `https://sy-tools.github.io/sy-help/s/<stem>/`, where `<stem>`
is the file name without its `-vN` suffix. A replaced video (`intro` →
`intro-v2`) keeps the link; the page always describes the newest version,
the same rule the portal's `findLinked` applies.

**What `tools.publish` adds to the site, per stem (newest version only):**

- `s/<stem>/<file>.jpg` — frame 0 of `v/<file>.mp4`, scaled to 1200 px wide,
  JPEG, well under WhatsApp's ~300 KB. Named by `<file>`, not by the stem, so a
  replacement gets a new image URL (the repo's rule: a name never changes
  content). Recordings start straight on screen content, so frame 0 is never
  black (checked on three videos).
- `s/<stem>/index.html` — static, no external resources:
  - `<title>` and `og:title`: the Ukrainian title;
  - `og:description`: the Ukrainian description, or, when empty,
    `<section title> · <duration> · SY Subtitles`;
  - `og:image` (absolute URL), `og:image:width/height/type`, `og:type=website`,
    `og:site_name=SY Subtitles`, `og:url`, `twitter:card=summary_large_image`
    (Telegram uses it to show the large image);
  - `<meta name="robots" content="noindex">`;
  - a redirect to `https://sy-tools.github.io/sy-subtitles/#/help/<stem>`:
    `<meta http-equiv="refresh">` as the fallback, plus a `location.replace`
    that carries the share URL's `?q=`/`?f=` across, so the portal opens over
    the index the sharer had on screen, as today. A visible link for anyone
    whose redirect is blocked.
  - All catalog text HTML-escaped.

The portal URL is a constant in `tools.publish` (overridable by flag for
tests); the deploy does not depend on the portal's deploy.

**robots.txt: no change.** A crawler reads only the origin's root file,
`https://sy-tools.github.io/robots.txt`, and that answers 404 (there is no
`sy-tools.github.io` repository), so nothing on the origin is disallowed.
The project sites' own `robots.txt` files are never consulted. `noindex` on
the share page is therefore what keeps it out of search results.

**Deploy:** frame extraction needs `ffmpeg` on the runner — use it if present,
install it otherwise; a failed extraction fails the deploy (no silent page
without an image).

**Portal (sy-subtitles, second PR):** `shareUrl` in `site/js/help_videos.js`
returns `<help pages base>s/<stem>/` plus the kept `q`/`f`. The help pages base
already follows `__SY_HELP_REPO`, so a local stand pointed at another help repo
shares that repo's pages. The old `#/help/<file>` links keep working — the hash
route is unchanged.

Builder's call: when the address carries `repo` or `branch` (a local stand, or
a portal pointed at another branch), `shareUrl` keeps today's portal-hash link.
A share page can only lead to the production portal on `main`, so it would
drop exactly what those parameters say.

Builder's call: the share page carries no other parameter than `q`/`f`; a
removed video's page disappears with the next deploy (the site is laid out
from scratch), so its old link answers 404, as its video does.

## Order

1. sy-help PR: share pages + frames + deploy; tests first.
   Verify after deploy: `curl` the page with the Telegram and WhatsApp user
   agents, then send a link to oneself in both apps (Telegram's cache is reset
   with @WebpageBot).
2. sy-subtitles PR: the share button emits the new URL; `node --test`,
   `pytest -m smoke`, and the button tried in a browser.

## Left to the builder

- Exact ffmpeg flags and JPEG quality, within the size limit.
- How the page looks for the half-second before the redirect (a plain line
  with the title and a link is enough).
