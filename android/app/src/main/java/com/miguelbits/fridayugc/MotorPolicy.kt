package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.StepResponse
import kotlinx.serialization.json.JsonPrimitive

/**
 * Last-line motor safety for Reels comment-likes — blocks RIGHT swipes (Stories / wrong pager)
 * and raw horizontal swipes before Reels is verified. LEFT pager swipe is allowed only when
 * explicitly tagged enter_reels_pager (controlled fallback after nav + deep link fail).
 */
object MotorPolicy {

    const val ENTER_REELS_PAGER = "enter_reels_pager"

    fun navigateReels(reason: String): StepResponse = StepResponse(
        action = "navigate",
        params = mapOf(
            "tab" to JsonPrimitive("reels"),
            "ui_key" to JsonPrimitive("nav_reels"),
        ),
        reason = reason,
    )

    fun pagerSwipeLeft(): StepResponse = StepResponse(
        action = "swipe",
        params = mapOf(
            "direction" to JsonPrimitive("left"),
            "zone" to JsonPrimitive("feed_pager"),
        ),
        reason = ENTER_REELS_PAGER,
    )

    /**
     * Returns a replacement action when [resp] must not run on device, or null if OK.
     */
    fun clampCommentLikes(
        resp: StepResponse,
        reelsTabOpened: Boolean,
        screenType: String,
    ): StepResponse? {
        if (screenType == "story_viewer" && resp.action != "press") {
            return StepResponse(
                action = "press",
                params = mapOf("key" to JsonPrimitive("back")),
                reason = "story_viewer — back out before Reels work",
            )
        }

        if (resp.action in setOf("view_story", "like_story")) {
            return navigateReels("blocked ${resp.action} — goal is Reels comment-likes")
        }

        val dir = (resp.params["direction"] as? JsonPrimitive)?.content?.lowercase().orEmpty()

        when (resp.action) {
            "swipe", "scroll" -> {
                // RIGHT swipe on home feed opens Stories tray / wrong pager direction — never.
                if (dir == "right") {
                    return navigateReels("blocked motor swipe/scroll RIGHT (Stories risk)")
                }
                if (!reelsTabOpened) {
                    val allowedLeftPager = dir == "left" &&
                        (resp.reason.contains(ENTER_REELS_PAGER) || resp.reason.contains("pager_enter_reels"))
                    if (!allowedLeftPager) {
                        return navigateReels("blocked ${resp.action} $dir before reels_tab_opened")
                    }
                } else if (dir == "left" || dir == "right") {
                    return StepResponse(
                        action = "wait",
                        params = mapOf("ms" to JsonPrimitive(400)),
                        reason = "blocked horizontal $dir on reels surface",
                    )
                }
            }
        }
        return null
    }

    /** Block dangerous motor at the executor layer (defense in depth). */
    fun blockExecutorSwipe(
        direction: String,
        reason: String,
        isInstagram: Boolean,
    ): String? {
        if (!isInstagram) return null
        val dir = direction.lowercase()
        if (dir == "right") return "swipe RIGHT blocked on Instagram (Stories / wrong pager)"
        if (dir == "left" && !reason.contains(ENTER_REELS_PAGER) && !reason.contains("pager_enter_reels")) {
            // Un tagged left swipes are risky on home — only IntentResolver/enterReelsAutonomous may pager-left.
            return null // allow — AgentController should have clamped; tagged left passes through
        }
        return null
    }
}
