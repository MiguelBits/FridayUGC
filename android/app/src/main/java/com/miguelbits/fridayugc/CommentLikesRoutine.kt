package com.miguelbits.fridayugc

import android.util.DisplayMetrics
import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenState
import com.miguelbits.fridayugc.model.StepResponse
import kotlinx.serialization.json.JsonPrimitive

/**
 * Step-by-step comment-likes on Reels — vision-only for tap targets.
 * Gestures (swipe next reel, scroll sheet, back) stay fixed/coarse.
 */
object CommentLikesRoutine {

    const val PHASE_ON_REELS = "on_reels"
    const val PHASE_IN_COMMENTS = "in_comments"
    const val PHASE_CLOSING = "closing"

    private const val REEL_LIKE_Y_MAX = 0.54f
    /** Hearts to like on the current viewport before scrolling the sheet. */
    private const val LIKES_PER_SCROLL = 2
    /** Max scrolls inside the comments sheet per reel. */
    private const val MAX_SHEET_SCROLLS = 3

    fun nextStep(
        tracker: SessionTracker,
        screen: Screen,
        screenState: ScreenState,
        dm: DisplayMetrics,
    ): StepResponse? {
        if (tracker.phase != "reels_comment_likes") return null

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

                if (tracker.commentLikesSinceScroll >= LIKES_PER_SCROLL &&
                    tracker.commentSheetScrolls < MAX_SHEET_SCROLLS &&
                    tracker.commentLikesThisReel < tracker.commentLikesPerReel
                ) {
                    return StepResponse(
                        action = "scroll",
                        params = mapOf(
                            "direction" to JsonPrimitive("up"),
                            "zone" to JsonPrimitive("comments_sheet"),
                        ),
                        say = "Scrolling comments for more hearts.",
                        reason = "routine in_comments — scroll sheet",
                    )
                }

                if (tracker.commentLikesThisReel > 0 &&
                    tracker.commentLikesSinceScroll >= LIKES_PER_SCROLL &&
                    tracker.commentSheetScrolls >= MAX_SHEET_SCROLLS
                ) {
                    tracker.commentLikesPhase = PHASE_CLOSING
                    return StepResponse(
                        action = "press",
                        params = mapOf("key" to JsonPrimitive("back")),
                        say = "Closing comments.",
                        reason = "routine in_comments — done liking, leave sheet",
                    )
                }

                StepResponse(
                    action = "intent",
                    params = mapOf("name" to JsonPrimitive("engage_comments")),
                    say = "Like comment ${tracker.commentLikesThisReel + 1}/${tracker.commentLikesPerReel}.",
                    reason = "routine in_comments — vision engage",
                    needsScreenshot = true,
                )
            }

            else -> { // PHASE_ON_REELS
                if (!ScreenClassifier.likelyReelsSurface(screenState, screen) &&
                    !ScreenClassifier.isFullCommentsSheet(screen, screenState.activityClass)
                ) {
                    return StepResponse(
                        action = "intent",
                        params = mapOf("name" to JsonPrimitive("enter_reels")),
                        say = "Opening Reels first.",
                        reason = "routine enter_reels before comments",
                        needsScreenshot = true,
                    )
                }
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
                if (ScreenClassifier.isFullCommentsSheet(screen, screenState.activityClass) ||
                    tracker.commentsSheetOpen
                ) {
                    tracker.commentLikesPhase = PHASE_IN_COMMENTS
                    tracker.commentsSheetOpen = true
                    return nextStep(tracker, screen, screenState, dm)
                }
                StepResponse(
                    action = "intent",
                    params = mapOf("name" to JsonPrimitive("open_comments")),
                    say = "Open comments.",
                    reason = "routine open_comments — vision",
                    needsScreenshot = true,
                )
            }
        }
    }

    fun onActionCompleted(tracker: SessionTracker, action: String, ok: Boolean, params: Map<String, kotlinx.serialization.json.JsonElement> = emptyMap()) {
        if (!ok) return
        when (action) {
            "tap" -> {
                tracker.commentsSheetOpen = true
                tracker.commentLikesPhase = PHASE_IN_COMMENTS
                tracker.commentLikesSinceScroll = 0
                tracker.commentSheetScrolls = 0
            }
            "like_comment" -> { /* counts via SessionTracker.record */ }
            "scroll" -> {
                val zone = (params["zone"] as? JsonPrimitive)?.content?.lowercase()
                if (zone == "comments_sheet") {
                    tracker.commentLikesSinceScroll = 0
                    tracker.commentSheetScrolls++
                }
            }
            "press" -> {
                tracker.commentsSheetOpen = false
                tracker.commentLikesThisReel = 0
                tracker.commentLikesSinceScroll = 0
                tracker.commentSheetScrolls = 0
                tracker.commentLikesPhase = PHASE_ON_REELS
                tracker.readyForNextReel = true
            }
            "swipe" -> {
                val zone = (params["zone"] as? JsonPrimitive)?.content?.lowercase()
                if (zone == "reels_rail") {
                    tracker.commentsSheetOpen = false
                    tracker.commentLikesThisReel = 0
                    tracker.commentLikesSinceScroll = 0
                    tracker.commentSheetScrolls = 0
                    tracker.commentLikesPhase = PHASE_ON_REELS
                    tracker.readyForNextReel = false
                }
            }
        }
    }

    fun isReelLikeZone(x: Int, y: Int, w: Int, h: Int): Boolean =
        x > w * 0.85f && y < h * REEL_LIKE_Y_MAX
}
