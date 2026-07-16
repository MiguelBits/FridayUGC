# Teach findings — comment likes loop (device `555c96f0`)

Snapshot of `brain/data/teach/` after early full_loop + open_comments sessions (2026-07-16).  
Screen: **1440×3216**.

## What we learned

### 1. Comments icon X is stable; Y is not

| Metric | Value |
|--------|--------|
| Taught aggregate `open_comments` | `(1320, 1563)` ≈ `(0.917, 0.486)` |
| `n_ok` | 16 |
| X range | 1293–1347 (tight, right rail) |
| Y range | 1320–2479 (huge vertical spread) |
| Y frac range | **0.41 – 0.77** |

**Implication:** a single median Y will miss many reels. Right-rail icons move with caption length, follow chip, and engagement-count stack. Replay must tolerate Y bands (or pick nearest exemplar), not one point.

### 2. Image / layout types (open_comments BEFORE)

Band by `tap_y_frac` on labeled ok demos:

| Band | y_frac | Count | Typical layout |
|------|--------|------:|----------------|
| **high** | &lt; 0.50 | 9 | Short caption / compact right rail — comments bubble higher |
| **mid-high** | 0.50–0.62 | 2 | Medium rail |
| **mid** | 0.62–0.72 | 4 | Tall caption / more counts — bubble lower |
| **low** | ≥ 0.72 | 1 | Very low bubble (or noisy label — see data quality) |

Example high (clean Reels viewer): `ae2eef6b_*` — organic reel, comments icon mid-right rail.  
Example mid: `7ce3973a_*`, `78845477_*`.  
Example low: `2627ebec_*` (y_frac 0.77) — treat carefully (see quality note).

### 3. Full-loop tryouts (multi-step parents)

Only **4** reel episodes ran the chained flow:

| Parent | Chain | Result |
|--------|-------|--------|
| `a85f5182` | open ok → like ok → scroll ok → like ok → close ok → next ok | **PASS** |
| `fc7ea9a8` | open ok → like ok → scroll **fail** → like ok → close ok → next ok | mostly pass (scroll evidence weak) |
| `621b7d68` | open ok → like ok → scroll ok → like ok → close ok → next **ad** | pass until next reel = ad |
| `c38b4039` | open ok → like ok → scroll ok → like ok → close **ad** | aborted at close/ad |

So: **1 clean full pass**, 1 soft pass, 2 hit ads late in the flow. Not yet enough for a reliable full-loop skill; need more complete reels.

### 4. Ads (`label=ad`) — 3 labeled, 1 clear ad-type

| Episode | Skill when labeled | Notes |
|---------|--------------------|--------|
| `541ce527` | `open_comments` | **True ad-type:** `Patrocinado` + blue **Saber mais** CTA (`gomrycom`). Skip / swipe next — do not teach as ok. |
| `f6472213` | `close_comments` | Labeled ad during close (likely landed on sponsored after prior step) |
| `42132e62` | `next_reel` | Labeled ad after swipe to next |

**Policy:** ads are never aggregated into skill coords. On ad → swipe next reel, do not tap comments as success.

Ad cues seen: `Patrocinado`, CTA bar (`Saber mais` / Shop), optional missing comment count.

### 5. `like_comment` samples

| Metric | Value |
|--------|--------|
| Aggregate | `(1338, 1515)` ≈ `(0.929, 0.471)` |
| `n_ok` | 8 |
| X | ~0.92–0.93 (hearts on **right** of comment rows in this IG build/locale) |
| Y | 1392–2207 (different rows / GIF vs text height) |

Hearts sit on the **right** of each comment row here (not left). One median Y only hits the “first visible” row band; after scroll, need a new Y (or row-index offsets).

### 6. Data quality issues to fix while teaching

1. **BEFORE already comments sheet** for some `open_comments` labels (e.g. `2627ebec`, `7d338f3f` afters/befores look like sheet open). Those coords train the wrong surface — prefer demos where BEFORE is clearly `reels_viewer`.
2. Early sessions used `--skill open_comments` only — likes/scrolls on the phone were **not** labeled until `full_loop`.
3. Close sheet + next reel between open_comments-only episodes, or Y labels drift onto the sheet.

## Recommended next steps

1. Finish more **`full_loop`** reels (target ≥10 clean passes) with BEFORE always on Reels for step 0.
2. Tag or note **high / mid / low** rail when confirming (optional field later).
3. Replay proof:
   - `open_comments` first (Y band or multi-exemplar).
   - then full_loop automation once like + scroll evidence is thicker.
4. Keep labeling ads with `a` — corpus already shows the pattern works.

## Commands

```bash
cd brain && source .venv/Scripts/activate && python -m adb.teach show --skill open_comments
```

```bash
cd brain && source .venv/Scripts/activate && python -m adb.teach show --skill like_comment
```

```bash
cd brain && source .venv/Scripts/activate && python -m adb.teach record --skill full_loop --count 10 --likes 2
```

```bash
cd brain && source .venv/Scripts/activate && python -m adb.teach replay --skill open_comments --trials 10
```
