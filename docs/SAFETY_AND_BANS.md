# Safety & Ban-Avoidance (read before touching @itslorenamor)

`@itslorenamor` is a **real 2K-follower account**. Automation of a real IG account violates
Instagram's Terms of Use and carries a genuine risk of **action blocks, shadowbans, or permanent
bans**. This document is about reducing — not eliminating — that risk. You accept the risk.

## Golden rules

1. **Test on a throwaway account first.** Always. Prove the flow before risking the real one.
2. **Approval-gate the dangerous stuff.** `post`, `comment`, `dm`, `follow`, `unfollow` require a
   tap-to-approve by default (enforced in `brain/app/agent/loop.py` AND `AgentController.kt`).
3. **Move like a human.** Randomized delays are built into `AgentController.humanDelayMs()`.
   Don't lower them to spam levels.
4. **Volume caps.** Keep engagement conservative. Suggested daily ceilings for a 2K account:

   | Action | Suggested max/day | Notes |
   |--------|-------------------|-------|
   | Likes | 60–100 | spread out, not bursts |
   | Comments | 10–20 | must be genuine, in-voice, varied |
   | Follows | 15–30 | avoid follow/unfollow churn |
   | DMs | 5–10 | never to strangers unsolicited |
   | Posts | 1–3 | you approve each one |

5. **Never auto-DM strangers.** Fast track to a ban and it's spammy.
6. **Vary content.** The persona pack enforces phrase cooldowns; keep them on.

## What triggers Instagram's systems

- Bursty, machine-timed actions (perfectly spaced likes/follows).
- Identical/near-identical comments or captions.
- New device + immediate high-volume automation.
- Rooted device / known automation frameworks / emulator fingerprints.
- Rapid follow → unfollow cycles.

## Recommended rollout for the real account

1. Week 0: throwaway account only; validate loop + posting.
2. Week 1: real account, **read-only** (scroll, observe, draft captions/comments for you to post
   manually).
3. Week 2: enable **approved** likes at low volume.
4. Week 3+: enable **approved** comments/posts. Keep DMs manual for a while.

## Handling checkpoints

- If IG shows a login/security checkpoint, **stop automation** and resolve it manually.
- Log into the account normally (human) periodically so the account has organic activity.

## Content safety (built in)

The brain runs every audience-facing string through `brain/app/ugc/safety.py`:
- Visual generation prompts: banned terms → platform-safe swaps.
- Dialogue/captions: banned terms → safe swaps; filler flagged.
- Device wording (phone-in-hand) flagged for the phone-safe generation rule.

## Legal / ToS

This is a personal-assistant tool for an account you own and operate. It is not for spam, growth
farming, or operating accounts you don't control. Automating Instagram may still breach their ToS
regardless of intent — proceed knowingly.
