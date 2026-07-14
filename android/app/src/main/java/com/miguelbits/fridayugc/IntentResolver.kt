package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.GroundRequest
import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenState
import com.miguelbits.fridayugc.model.StepResponse
import kotlinx.serialization.json.JsonPrimitive
import kotlin.random.Random

/**
 * Translates brain intents into motor actions at execution time.
 * Binding order: accessibility → device memory → Gemma 3 vision grounding (local, no OpenAI).
 */
class IntentResolver(
    private val service: FridayAccessibilityService,
    private val memoryStore: DeviceMemoryStore,
    private val brain: BrainClient,
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
        screenshotB64: String? = null,
    ): ResolveResult {
        val name = (intent.params["name"] as? JsonPrimitive)?.content?.lowercase().orEmpty()
        return when (name) {
            "enter_reels" -> resolveEnterReels(screenState)
            "watch_reel", "dwell" -> resolveDwell(intent)
            "open_comments" -> resolveOpenComments(screen, screenState, screenshotB64)
            "engage_comments" -> resolveEngageComments(screen, tracker, screenshotB64)
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

    private suspend fun resolveOpenComments(
        screen: Screen,
        screenState: ScreenState,
        screenshotB64: String?,
    ): ResolveResult {
        if (screenState.screenType == "comments_sheet") {
            return ResolveResult(
                StepResponse(action = "wait", params = mapOf("ms" to JsonPrimitive(200))),
            )
        }
        val dm = service.resources.displayMetrics
        ReelsTargetFinder.findCommentsElement(screen, dm.widthPixels, dm.heightPixels)?.let { e ->
            return ResolveResult(
                StepResponse(action = "tap", params = mapOf("target_id" to JsonPrimitive(e.id))),
            )
        }
        memoryStore.lookup("comments_icon")?.let { (x, y) ->
            return ResolveResult(
                StepResponse(action = "tap", params = mapOf("x" to JsonPrimitive(x), "y" to JsonPrimitive(y))),
            )
        }
        return visionGround(
            anchor = "comments_icon",
            screen = screen,
            screenState = screenState,
            rowIndex = 0,
            screenshotB64 = screenshotB64,
            fallbackAction = "tap",
        )
    }

    private suspend fun resolveEngageComments(
        screen: Screen,
        tracker: SessionTracker,
        screenshotB64: String?,
    ): ResolveResult {
        if (tracker.commentLikesThisReel >= tracker.commentLikesPerReel) {
            return ResolveResult(
                StepResponse(action = "press", params = mapOf("key" to JsonPrimitive("back"))),
            )
        }
        val dm = service.resources.displayMetrics
        val w = dm.widthPixels
        val h = dm.heightPixels
        val sheetMinY = (h * 0.55f).toInt()
        val hearts = screen.elements.filter { e ->
            if (!e.clickable || e.w <= 0 || e.h <= 0) return@filter false
            val cy = e.y + e.h / 2
            if (cy < sheetMinY) return@filter false
            e.text.lowercase().let { t -> t.contains("like") || t.contains("heart") } ||
                (e.w <= 120 && e.h <= 120 && e.x + e.w / 2 > w * 0.72f)
        }.sortedBy { it.y }
        val row = tracker.commentLikesThisReel
        if (hearts.isNotEmpty()) {
            val pick = hearts[row.coerceAtMost(hearts.lastIndex)]
            return ResolveResult(
                StepResponse(action = "like_comment", params = mapOf("target_id" to JsonPrimitive(pick.id))),
            )
        }
        memoryStore.lookup("like_comment")?.let { (x, y) ->
            return ResolveResult(
                StepResponse(action = "like_comment", params = mapOf("x" to JsonPrimitive(x), "y" to JsonPrimitive(y))),
            )
        }
        return visionGround(
            anchor = "comment_heart",
            screen = screen,
            screenState = ScreenState(screenType = "comments_sheet"),
            rowIndex = row,
            screenshotB64 = screenshotB64,
            fallbackAction = "like_comment",
        )
    }

    private suspend fun visionGround(
        anchor: String,
        screen: Screen,
        screenState: ScreenState,
        rowIndex: Int,
        screenshotB64: String?,
        fallbackAction: String,
    ): ResolveResult {
        val shot = screenshotB64?.takeIf { it.isNotBlank() }
            ?: screen.screenshotB64?.takeIf { it.isNotBlank() }
        if (shot == null) {
            return ResolveResult(
                StepResponse(action = "wait", params = mapOf("ms" to JsonPrimitive(300)), reason = "$anchor needs screenshot"),
                needsScreenshot = true,
            )
        }
        val dm = service.resources.displayMetrics
        return runCatching {
            val ground = brain.ground(
                GroundRequest(
                    anchor = anchor,
                    screenshotB64 = shot,
                    screenWidth = dm.widthPixels,
                    screenHeight = dm.heightPixels,
                    screenType = screenState.screenType,
                    elements = screen.elements,
                    rowIndex = rowIndex,
                ),
            )
            if (ground.needsScreenshot || ground.params.isEmpty()) {
                ResolveResult(
                    StepResponse(action = "wait", params = mapOf("ms" to JsonPrimitive(400)), reason = ground.reason),
                    needsScreenshot = true,
                )
            } else {
                ResolveResult(
                    StepResponse(
                        action = ground.action.ifBlank { fallbackAction },
                        params = ground.params,
                        reason = "vision ground: ${ground.reason}",
                    ),
                )
            }
        }.getOrElse {
            ResolveResult(
                StepResponse(action = "wait", params = mapOf("ms" to JsonPrimitive(500)), reason = "ground failed: ${it.message}"),
                needsScreenshot = true,
            )
        }
    }
}
