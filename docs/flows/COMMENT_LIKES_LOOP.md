# Flow: comment_likes_loop (target choreography)

**ID:** `reels_comment_likes`  
**Goal:** Per reel — open comments, like N comments (scroll as needed), close, next reel.

## Loop

```
open_reels
  └─ for reel in 1..reels_max:
        dwell (1.2–2.8s)
        open_comments          ← teach step: AFTER = proof in comments
        like_comment           ← teach: BEFORE = previous AFTER
        scroll comments_sheet  ← teach: BETWEEN likes
        like_comment           ← teach: BEFORE = previous AFTER
        close_comments (back)  ← teach evidence
        next_reel (swipe up)   ← teach evidence
```

Teach mode (`python -m adb.teach record --skill full_loop`) chains screenshots:
each step’s AFTER becomes the next step’s BEFORE.

## Phases (`comment_likes_phase`)

| Phase | Meaning | Typical action |
|-------|---------|----------------|
| `on_reels` | Viewing reel | wait → open_comments / next swipe |
| `in_comments` | Sheet open | like_comment / scroll comments_sheet |
| `closing` | Done with sheet | press back |

## Per-reel like policy

- Target likes: random 2–5 (or fixed via `--comment-likes-per-reel`)
- After every 2 likes: scroll comments sheet (`zone=comments_sheet`)
- Max sheet scrolls: 3; then close even if under target

## Anchors

| Anchor | Meaning |
|--------|---------|
| `comments_icon` | Right-rail speech bubble |
| `comment_heart` | Small heart on a **comment row** (sheet), not reel like |

## Success / wrong-flow evaluation

Each step must classify **after** observe:

| Expected | Pass | Fail |
|----------|------|------|
| open_reels | `reels_viewer` | home / other |
| open_comments | `comments_sheet` | `wrong_sheet` (share) / still reels |
| like_comment | still comments sheet | left sheet / wrong surface |
| close | `reels_viewer` | still sheet |
| next reel | `reels_viewer` + scrolled++ | stuck |

Failures update memory (`fail_count`) and flow offsets so the agent is not stuck repeating the same bad tap.
