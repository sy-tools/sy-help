# sy-help

Video hosting for the tutorials embedded in the
[SY Subtitles portal](https://sy-tools.github.io/sy-subtitles/).
The videos are served by GitHub Pages at
`https://sy-tools.github.io/sy-help/v/<id>.mp4`, which is the same origin as
the portal.

## Why this shape

- **GitHub Pages, not release download links.** A release asset is served as
  `application/octet-stream`, and Safari, and so every browser on an iPhone,
  will not play it in a `<video>` element. Pages serves `video/mp4` and answers
  range requests, so seeking works everywhere.
- **Videos live in the `media` release, not in git.** The deploy workflow
  downloads every asset of that release into `v/` and publishes the site. A
  video can be replaced without bloating the repository's history.
- **Names are opaque ids.** A file is named `<12 random [a-z0-9]>.mp4` and
  carries no title or metadata. The mapping from tutorial to id lives in the
  portal, encoded the way it stores `video_ref`. The deploy refuses any other
  name.

This is **obfuscation, not secrecy**: the repository is public (Pages on a free
plan requires it), so anyone can list the release or find a URL in the
browser's developer tools. It keeps the videos from being discoverable by
name or by search engines (`robots.txt` disallows everything), and nothing
more.

## Encoding

Every video is H.264 + AAC with the index at the front of the file, so it
plays in every browser and starts before it has downloaded:

```bash
ffmpeg -i in.mp4 -map 0:v:0 -map 0:a:0 -r 30 \
  -c:v libx264 -preset slow -crf 30 -pix_fmt yuv420p -profile:v high \
  -c:a aac -b:a 96k -ac 1 -map_metadata -1 -movflags +faststart <id>.mp4
```

Screen recordings come out at about 2 MiB per minute, so the 1 GB Pages limit
holds about 9 hours of video. The deploy fails before it crosses that limit.

## Adding or replacing a video

1. Encode it as above, under a **new** id (`python3 -c "import secrets,string;
   print(''.join(secrets.choice(string.ascii_lowercase+string.digits) for _ in
   range(12)))"`). Never reuse an id for different content: browsers and the
   Pages CDN cache by URL.
2. `gh release upload media <id>.mp4 --repo sy-tools/sy-help`
   (to retire one: `gh release delete-asset media <id>.mp4 --repo sy-tools/sy-help`).
3. `gh workflow run deploy.yml --repo sy-tools/sy-help`. An asset upload fires
   no workflow, so the deploy has to be started by hand.
4. Point the portal at the new id.
