package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.Screen

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
    ): Result {
        val change = ScreenValidator.changeScore(before, after, beforeFp, afterFp)
        if (!executorOk) return Result("failed", change)
        return when (action) {
            "done", "fail" -> Result(if (executorOk) "verified" else "failed", change)
            "wait", "press" -> Result("unknown", change)
            "open_app" -> {
                val opened = after.app.contains("instagram", ignoreCase = true)
                Result(if (opened) "verified" else "unverified", change)
            }
            "swipe", "scroll", "view_story" -> {
                val moved = change >= 0.12f || ScreenValidator.screenChanged(beforeFp, afterFp)
                Result(if (moved) "verified" else "unverified", change)
            }
            "navigate" -> {
                val moved = change >= 0.08f || ScreenValidator.screenChanged(beforeFp, afterFp)
                Result(if (moved) "verified" else "unverified", change)
            }
            "tap", "like", "like_story", "like_comment", "comment", "dm", "follow", "save", "type" -> {
                val moved = change >= 0.06f || ScreenValidator.screenChanged(beforeFp, afterFp)
                Result(if (moved) "verified" else "unverified", change)
            }
            else -> Result(if (change >= 0.05f) "verified" else "unknown", change)
        }
    }
}
