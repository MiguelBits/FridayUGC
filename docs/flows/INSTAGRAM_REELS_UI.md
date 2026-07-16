# Instagram Reels UI — what the screenshots mean

## Surfaces we care about

| Surface | What you see | Brain `screen_type` |
|---------|--------------|---------------------|
| Reels viewer | Full-bleed video, right action rail, bottom caption/audio | `reels_viewer` |
| Comments sheet | Light bottom sheet over reel; composer “Add a comment…”; Reply rows | `comments_sheet` |
| Share / repost sheet | “Share”, “Add to story”, “Repost”, “Copy link”, contacts | treated as **wrong_sheet** |
| Home feed | “For you” / “Following” tabs | `home_feed` |

ADB observe often returns **empty accessibility trees** on Reels. Classification must use activity class + **screenshot heuristics**, not a11y text alone.

## Right rail (typical portrait order, top → bottom)

```
+-----------------------------+
|                     [avatar]|
|                     heart   |  ~46-50% H   reel like
|                     bubble  |  ~50-55% H   COMMENTS (target)
|                     share   |  ~56-62% H   share/repost (fail)
|                     more    |
|                     audio   |  ~70%+ H
+-----------------------------+
```

Fractions vary by IG version, phone aspect ratio, and caption height. **Share sits immediately below comments** — a few percent of height separates success from “Repost”.

## Screenshot signatures

### Reels viewer (success enter)

- Dark / video-dominated frame
- Right-rail icons visible as light glyphs
- Bottom nav may show Reels selected
- Activity often contains `clips` / `Reel` / `ClipsViewer`

### Comments sheet (success open)

- Large **light** panel covering roughly the **bottom 40–55%** of the frame
- Dark dimmed reel still visible on the top strip
- Composer bar near the bottom of the sheet
- Rows of comment text + small hearts per row

### Share / repost sheet (wrong open — current bug)

- Bottom sheet with share destinations (story, repost, copy link, apps)
- Not a comment thread; no “Add a comment…” composer for the reel
- Opening this must **not** set `comments_sheet_open=1`

## Why vision clicks republish

1. Model sees “icon on right rail” and picks **share** (paper plane / arrows).
2. Grounding band historically allowed Y up to ~60% H — overlaps share.
3. Soft verify (`change_score >= 0.10`) accepted any overlay as success.
4. Session then believed comments were open and planned likes on the wrong sheet.

## Deterministic anchors (percent of display)

| Anchor | X | Y | Notes |
|--------|---|---|-------|
| `nav_reels` | **0.50** | **0.955** tall / 0.965 std | Center clapperboard (deeplink first); legacy fallback X 0.30 |
| `comments_icon` | 0.90 | **0.52** | Between like and share; memory may override |
| `reel_like` | 0.92 | 0.48 | Not comment hearts |
| Share (avoid) | 0.90 | ≥0.56 | Rejected by band check |

Device memory stores **verified** `(x,y)` per `device_id` + `ui_key` after probe/routine success.
