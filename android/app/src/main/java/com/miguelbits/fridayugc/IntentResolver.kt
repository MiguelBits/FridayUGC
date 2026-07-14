package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenState
import com.miguelbits.fridayugc.model.StepResponse
import kotlinx.serialization.json.JsonPrimitive
import kotlin.random.Random

/**
 * Translates brain intents into concrete motor actions at execution time.
 * Binds targets from fresh accessibility tree + device memory — no hardcoded coordinates.
 */
class IntentResolver(
    private val service: FridayAccessibilityService,
    private val memoryStore: DeviceMemoryStore,
) {
    data class ResolveResult(
        val response: StepResponse,
        val needsScreenshot: Boolean = false,
    )

    suspend fun resolve(
        intent: StepResponse,
        screen: Screen,
        screenState: ScreenState,
        tracker: SessionTracker,
    ): ResolveResult {
        val name = (intent.params["name"] as? JsonPrimitive)?.content?.lowercase().orEmpty()
        return when (name) {
            "enter_reels" -> resolveEnterReels(screenState)
            "watch_reel", "dwell" -> resolveDwell(intent)
            "open_comments" -> resolveOpenComments(screen, screenState)
            "engage_comments" -> resolveEngageComments(screen, tracker)
            "next_reel" -> ResolveResult(
                StepResponse(action = "swipe", params = mapOf("direction" to JsonPrimitive("up"))),
            )
            "browse_feed" -> {
                val dir = (intent.params["direction"] as? JsonPrimitive)?.content ?: "up"
                ResolveResult(
                    StepResponse(action = "swipe", params = mapOf("direction" to JsonPrimitive(dir))),
                )
            }
            "go_back" -> ResolveResult(
                StepResponse(action = "press", params = mapOf("key" to JsonPrimitive("back"))),
            )
            "check_inbox" -> ResolveResult(
                StepResponse(action = "navigate", params = mapOf("tab" to JsonPrimitive("inbox"))),
            )
            "open_profile" -> ResolveResult(
                StepResponse(action = "navigate", params = mapOf("tab" to JsonPrimitive("profile"))),
            )
            else -> ResolveResult(
                StepResponse(
                    action = "wait",
                    params = mapOf("ms" to JsonPrimitive(400)),
                    reason = "unknown intent: $name",
                ),
            )
        }
    }

    private suspend fun resolveEnterReels(screenState: ScreenState): ResolveResult {
        if (screenState.screenType == "reels_viewer" && screenState.confidence >= 0.55f) {
            return ResolveResult(
                StepResponse(
                    action = "wait",
                    params = mapOf("ms" to JsonPrimitive(300)),
                    reason = "already on reels_viewer",
                ),
            )
        }
        if (screenState.screenType == "story_viewer") {
            return ResolveResult(
                StepResponse(action = "press", params = mapOf("key" to JsonPrimitive("back"))),
            )
        }
        return ResolveResult(
            StepResponse(action = "navigate", params = mapOf("tab" to JsonPrimitive("reels"))),
        )
    }

    private fun resolveDwell(intent: StepResponse): ResolveResult {
        val ms = (intent.params["dwell_ms"] as? JsonPrimitive)?.content?.toLongOrNull()
            ?: Random.nextLong(1800, 5200)
        return ResolveResult(
            StepResponse(action = "wait", params = mapOf("ms" to JsonPrimitive(ms.coerceIn(500, 8000)))),
        )
    }

    private fun resolveOpenComments(screen: Screen, screenState: ScreenState): ResolveResult {
        if (screenState.screenType == "comments_sheet") {
            return ResolveResult(
                StepResponse(action = "wait", params = mapOf("ms" to JsonPrimitive(200))),
            )
        }
        val root = service.rootInActiveWindow
        ScreenReader.indexByText(root, "comment", "comments")?.let { idx ->
            return ResolveResult(
                StepResponse(action = "tap", params = mapOf("target_id" to JsonPrimitive(idx))),
            )
        }
        memoryStore.lookup("comments_icon")?.let { (x, y) ->
            return ResolveResult(
                StepResponse(action = "tap", params = mapOf("x" to JsonPrimitive(x), "y" to JsonPrimitive(y))),
            )
        }
        for (e in screen.elements) {
            if (!e.clickable || e.w <= 0 || e.h <= 0) continue
            val cx = e.x + e.w / 2
            val screenW = screen.elements.maxOfOrNull { it.x + it.w } ?: 0
            if (screenW > 0 && cx > screenW * 0.72) {
                return ResolveResult(
                    StepResponse(action = "tap", params = mapOf("target_id" to JsonPrimitive(e.id))),
                )
            }
        }
        return ResolveResult(
            StepResponse(
                action = "wait",
                params = mapOf("ms" to JsonPrimitive(300)),
                needsScreenshot = true,
                reason = "open_comments needs vision",
            ),
            needsScreenshot = true,
        )
    }

    private fun resolveEngageComments(screen: Screen, tracker: SessionTracker): ResolveResult {
        if (tracker.commentLikesThisReel >= tracker.commentLikesPerReel) {
            return ResolveResult(
                StepResponse(action = "press", params = mapOf("key" to JsonPrimitive("back"))),
            )
        }
        val hearts = screen.elements.filter { e ->
            e.clickable && (
                e.text.lowercase().let { t ->
                    t.contains("like") || t.contains("heart") || t.contains("favorite")
                } || (e.w in 1..140 && e.h in 1..140 && e.x > (screen.elements.maxOfOrNull { it.x + it.w } ?: 0) * 0.7)
                )
        }.sortedBy { it.y }
        val idx = tracker.commentLikesThisReel.coerceAtMost((hearts.size - 1).coerceAtLeast(0))
        if (hearts.isNotEmpty()) {
            return ResolveResult(
                StepResponse(
                    action = "like_comment",
                    params = mapOf("target_id" to JsonPrimitive(hearts[idx].id)),
                ),
            )
        }
        memoryStore.lookup("like_comment")?.let { (x, y) ->
            return ResolveResult(
                StepResponse(action = "like_comment", params = mapOf("x" to JsonPrimitive(x), "y" to JsonPrimitive(y))),
            )
        }
        return ResolveResult(
            StepResponse(
                action = "wait",
                params = mapOf("ms" to JsonPrimitive(400)),
                needsScreenshot = true,
                reason = "engage_comments needs vision",
            ),
            needsScreenshot = true,
        )
    }
}
