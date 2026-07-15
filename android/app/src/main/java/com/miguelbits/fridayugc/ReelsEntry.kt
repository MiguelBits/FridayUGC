package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.StepResponse
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonPrimitive

/**
 * Autonomous Reels entry — deep link → vision ground nav_reels.
 * No a11y-tree targeting, memory coords, fixed coords, or pager swipe.
 */
object ReelsEntry {

    data class Result(
        val ok: Boolean,
        val reelsTabOpened: Boolean,
        val lastAction: String,
        val screenType: String,
    )

    suspend fun enter(
        svc: FridayAccessibilityService,
        brain: BrainClient,
        onSay: (String) -> Unit,
    ): Result {
        val executor = svc.executor
        var lastAction = "none"

        fun classify() = ScreenClassifier.classify(
            svc.readScreen(),
            svc.currentActivityClass(),
        )

        var state = classify()
        if (state.screenType == "story_viewer") {
            onSay("In Stories — going back…")
            executor.execute(StepResponse(action = "press", params = mapOf("key" to JsonPrimitive("back"))))
            delay(900)
            state = classify()
        }

        if (ScreenClassifier.likelyReelsSurface(state, svc.readScreen())) {
            return Result(true, true, "already_on_reels", state.screenType)
        }

        onSay("Reels entry — deep link…")
        lastAction = "open_reels"
        executor.execute(
            StepResponse(
                action = "open_reels",
                params = mapOf("ui_key" to JsonPrimitive("nav_reels")),
                reason = "enter_reels deep link",
            ),
        )
        delay(2400)
        state = classify()
        if (state.screenType == "story_viewer") {
            onSay("Landed in Stories — back…")
            executor.execute(StepResponse(action = "press", params = mapOf("key" to JsonPrimitive("back"))))
            delay(900)
            state = classify()
        }
        if (ScreenClassifier.likelyReelsSurface(state, svc.readScreen())) {
            return Result(true, true, lastAction, state.screenType)
        }

        onSay("Reels entry — vision ground nav_reels…")
        lastAction = "tap"
        val screen = svc.readScreen().copy(activity = svc.currentActivityClass())
        val cap = ScreenCapture.captureForGrounding(svc, screen, useSom = false)
        if (cap != null) {
            val deviceId = FridayPreferences.deviceId(svc.applicationContext)
            val resolved = VisionMotor.groundToStep(
                svc,
                brain,
                "nav_reels",
                screen.copy(screenshotB64 = cap.screenshotB64),
                state,
                cap.screenshotB64,
                deviceId = deviceId,
                imageWidth = cap.imageWidth,
                imageHeight = cap.imageHeight,
            )
            if (!resolved.needsScreenshot) {
                executor.execute(resolved.response)
                delay(2200)
                state = classify()
            }
        }

        val opened = ScreenClassifier.likelyReelsSurface(state, svc.readScreen())
        return Result(opened, opened, lastAction, state.screenType)
    }
}
