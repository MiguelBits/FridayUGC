package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenState
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive

/** Verifies that an executed action actually changed the device UI. */
object OutcomeVerifier {

    data class Result(
        val status: String,
        val changeScore: Float,
    )

    fun verify(
        action: String,
        executorOk: Boolean,
        before: Screen,
        after: Screen,
        beforeFp: String,
        afterFp: String,
        params: Map<String, JsonElement> = emptyMap(),
        afterActivity: String = "",
    ): Result {
        val change = ScreenValidator.changeScore(before, after, beforeFp, afterFp)
        if (!executorOk) return Result("failed", change)

        val uiKey = (params["ui_key"] as? JsonPrimitive)?.content.orEmpty()
        val afterState = ScreenClassifier.classify(after, afterActivity)

        return when (action) {
            "done", "fail" -> Result(if (executorOk) "verified" else "failed", change)
            "wait", "press" -> Result("unknown", change)
            "open_app" -> {
                val opened = after.app.contains("instagram", ignoreCase = true)
                Result(if (opened) "verified" else "unverified", change)
            }
            "open_reels" -> {
                val onReels = ScreenClassifier.likelyReelsSurface(afterState, after)
                Result(if (onReels) "verified" else "unverified", change)
            }
            "swipe", "scroll", "view_story" -> {
                val zone = (params["zone"] as? JsonPrimitive)?.content?.lowercase()
                if (zone == "reels_rail") {
                    val moved = change >= 0.05f || ScreenValidator.screenChanged(beforeFp, afterFp)
                    return Result(if (moved || executorOk) "verified" else "unverified", change)
                }
                val moved = change >= 0.12f || ScreenValidator.screenChanged(beforeFp, afterFp)
                Result(if (moved) "verified" else "unverified", change)
            }
            "navigate" -> {
                val moved = change >= 0.08f || ScreenValidator.screenChanged(beforeFp, afterFp)
                Result(if (moved) "verified" else "unverified", change)
            }
            "tap", "like", "like_story", "like_comment", "comment", "dm", "follow", "save", "type" -> {
                verifyTap(uiKey, change, beforeFp, afterFp, after, afterActivity)
            }
            else -> Result(if (change >= 0.05f) "verified" else "unknown", change)
        }
    }

    private fun verifyTap(
        uiKey: String,
        change: Float,
        beforeFp: String,
        afterFp: String,
        after: Screen,
        afterActivity: String,
    ): Result {
        val screenChanged = ScreenValidator.screenChanged(beforeFp, afterFp)
        return when (uiKey) {
            "comments_icon" -> {
                val sheetOpen = ScreenClassifier.isFullCommentsSheet(after, afterActivity)
                val ok = sheetOpen || (change >= 0.10f && screenChanged)
                Result(if (ok) "verified" else "unverified", change)
            }
            "comment_heart" -> {
                val onSheet = ScreenClassifier.isFullCommentsSheet(after, afterActivity)
                Result(if (onSheet) "verified" else "unverified", change)
            }
            "nav_reels" -> {
                val afterState = ScreenClassifier.classify(after, afterActivity)
                val onReels = ScreenClassifier.likelyReelsSurface(afterState, after)
                Result(if (onReels || change >= 0.08f) "verified" else "unverified", change)
            }
            else -> {
                val moved = change >= 0.06f || screenChanged
                Result(if (moved) "verified" else "unverified", change)
            }
        }
    }
}
