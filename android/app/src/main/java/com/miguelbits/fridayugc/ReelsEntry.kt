package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.StepResponse
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonPrimitive

/**
 * Autonomous Reels entry — bottom nav → deep link → memory → ONE controlled pager swipe LEFT.
 * Never swipe RIGHT (opens Stories). Never use untagged horizontal swipes.
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
        memoryStore: DeviceMemoryStore,
        onSay: (String) -> Unit,
    ): Result {
        val executor = svc.executor.apply { attachMemory(memoryStore) }
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

        memoryStore.lookup("nav_reels")?.let { (x, y) ->
            onSay("Reels entry — memory tap nav_reels…")
            lastAction = "tap"
            executor.execute(
                StepResponse(
                    action = "tap",
                    params = mapOf(
                        "x" to JsonPrimitive(x),
                        "y" to JsonPrimitive(y),
                        "ui_key" to JsonPrimitive("nav_reels"),
                    ),
                    reason = "enter_reels memory",
                ),
            )
            delay(2200)
            state = classify()
            if (ScreenClassifier.likelyReelsSurface(state, svc.readScreen())) {
                return Result(true, true, lastAction, state.screenType)
            }
        }

        onSay("Reels entry — bottom nav / deep link…")
        lastAction = "navigate"
        executor.execute(
            StepResponse(
                action = "navigate",
                params = mapOf(
                    "tab" to JsonPrimitive("reels"),
                    "ui_key" to JsonPrimitive("nav_reels"),
                ),
                reason = "enter_reels navigate",
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

        if (state.screenType == "home_feed" || state.screenType == "unknown") {
            onSay("Reels entry — one controlled swipe LEFT on feed pager…")
            lastAction = "swipe"
            GestureHelper.swipeFeedPager(svc, "left")
            delay(2400)
            state = classify()
            if (state.screenType == "story_viewer") {
                onSay("Swipe opened Stories — back…")
                executor.execute(StepResponse(action = "press", params = mapOf("key" to JsonPrimitive("back"))))
                delay(900)
                state = classify()
            }
        }

        val opened = ScreenClassifier.likelyReelsSurface(state, svc.readScreen())
        return Result(opened, opened, lastAction, state.screenType)
    }
}
