package com.miguelbits.fridayugc

import android.util.DisplayMetrics
import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenState
import com.miguelbits.fridayugc.model.StepResponse
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive

/**
 * Step-by-step comment-likes on Reels — avoids reel-like / comment-like confusion.
 *
 * Reels right rail (top→bottom): profile, **like ~48%**, **comments ~61%**, share…
 * Comment hearts live in the **bottom sheet** (y > 55%) — never tap the reel like zone.
 */
object CommentLikesRoutine {

    const val PHASE_ON_REELS = "on_reels"
    const val PHASE_IN_COMMENTS = "in_comments"
    const val PHASE_CLOSING = "closing"

    private const val RAIL_X = 0.92f
    private const val REEL_LIKE_Y_MAX = 0.54f
    private const val COMMENTS_ICON_Y = 0.58f
    private const val SHEET_MIN_Y = 0.55f
    private const val COMMENT_HEART_X = 0.86f

    fun nextStep(
        tracker: SessionTracker,
        screen: Screen,
        screenState: ScreenState,
        dm: DisplayMetrics,
    ): StepResponse? {
        if (tracker.phase != "reels_comment_likes") return null

        val w = dm.widthPixels
        val h = dm.heightPixels

        return when (tracker.commentLikesPhase) {
            PHASE_CLOSING -> StepResponse(
                action = "press",
                params = mapOf("key" to JsonPrimitive("back")),
                say = "Closing comments.",
                reason = "routine closing — ${tracker.commentLikesThisReel} likes done",
            )

            PHASE_IN_COMMENTS -> {
                if (tracker.commentLikesThisReel >= tracker.commentLikesPerReel) {
                    tracker.commentLikesPhase = PHASE_CLOSING
                    return StepResponse(
                        action = "press",
                        params = mapOf("key" to JsonPrimitive("back")),
                        say = "Closing comments.",
                        reason = "routine per-reel budget met",
                    )
                }
                val row = tracker.commentLikesThisReel
                val heartY = (h * (SHEET_MIN_Y + 0.07f * row + 0.03f)).toInt().coerceIn(
                    (h * SHEET_MIN_Y).toInt(),
                    (h * 0.92f).toInt(),
                )
                val heartX = (w * COMMENT_HEART_X).toInt()
                findSheetHeart(screen, row, w, h)?.let { params ->
                    StepResponse(
                        action = "like_comment",
                        params = params,
                        say = "Like comment ${row + 1}/${tracker.commentLikesPerReel}.",
                        reason = "routine in_comments — sheet heart row $row",
                    )
                } ?: StepResponse(
                    action = "like_comment",
                    params = mapOf(
                        "x" to JsonPrimitive(heartX),
                        "y" to JsonPrimitive(heartY),
                    ),
                    say = "Like comment ${row + 1}/${tracker.commentLikesPerReel}.",
                    reason = "routine in_comments — coord row $row (sheet zone)",
                )
            }

            else -> { // PHASE_ON_REELS
                if (tracker.readyForNextReel) {
                    tracker.readyForNextReel = false
                    if (tracker.reelsScrolled >= tracker.reelsMax) {
                        return StepResponse(
                            action = "done",
                            say = "Comment-likes routine complete.",
                            reason = "reels_max reached",
                            done = true,
                        )
                    }
                    return StepResponse(
                        action = "swipe",
                        params = mapOf(
                            "direction" to JsonPrimitive("up"),
                            "zone" to JsonPrimitive("reels_rail"),
                        ),
                        say = "Next reel.",
                        reason = "routine next_reel",
                    )
                }
                if (screenState.screenType == "comments_sheet" || tracker.commentsSheetOpen) {
                    tracker.commentLikesPhase = PHASE_IN_COMMENTS
                    tracker.commentsSheetOpen = true
                    return nextStep(tracker, screen, screenState, dm)
                }
                openCommentsTap(screen, w, h)
            }
        }
    }

    /** Tap comments bubble — 3rd rail icon (below like, above share/audio). */
    private fun openCommentsTap(screen: Screen, w: Int, h: Int): StepResponse {
        val params: Map<String, JsonElement> = ReelsTargetFinder.commentsTapParams(screen, w, h)
            ?: mapOf(
                "x" to JsonPrimitive((w * RAIL_X).toInt()),
                "y" to JsonPrimitive((h * COMMENTS_ICON_Y).toInt()),
            )
        return StepResponse(
            action = "tap",
            params = params,
            say = "Open comments.",
            reason = "routine open_comments — rail slot (not audio/share)",
        )
    }

    /** Hearts inside bottom sheet only — exclude reel-like rail zone. */
    private fun findSheetHeart(screen: Screen, row: Int, w: Int, h: Int): Map<String, JsonElement>? {
        val sheetMinY = (h * SHEET_MIN_Y).toInt()
        val reelLikeMaxY = (h * REEL_LIKE_Y_MAX).toInt()
        val candidates = screen.elements.filter { e ->
            if (!e.clickable || e.w <= 0 || e.h <= 0) return@filter false
            val cy = e.y + e.h / 2
            val cx = e.x + e.w / 2
            if (cy < sheetMinY) return@filter false
            if (cx > w * 0.88f && cy < reelLikeMaxY) return@filter false
            val t = e.text.lowercase()
            t.contains("like") || t.contains("heart") ||
                (e.w <= 120 && e.h <= 120 && cx > w * 0.72f)
        }.sortedBy { it.y }
        if (candidates.isEmpty()) return null
        val pick = candidates[row.coerceAtMost(candidates.lastIndex)]
        return mapOf("target_id" to JsonPrimitive(pick.id))
    }

    fun onActionCompleted(tracker: SessionTracker, action: String, ok: Boolean) {
        if (!ok) return
        when (action) {
            "tap" -> {
                tracker.commentsSheetOpen = true
                tracker.commentLikesPhase = PHASE_IN_COMMENTS
            }
            "like_comment" -> { /* counts via SessionTracker.record */ }
            "press" -> {
                tracker.commentsSheetOpen = false
                tracker.commentLikesThisReel = 0
                tracker.commentLikesPhase = PHASE_ON_REELS
                tracker.readyForNextReel = true
            }
            "swipe" -> {
                tracker.commentsSheetOpen = false
                tracker.commentLikesThisReel = 0
                tracker.commentLikesPhase = PHASE_ON_REELS
                tracker.readyForNextReel = false
            }
        }
    }

    fun isReelLikeZone(x: Int, y: Int, w: Int, h: Int): Boolean =
        x > w * 0.85f && y < h * REEL_LIKE_Y_MAX
}
