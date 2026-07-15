package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenState
import com.miguelbits.fridayugc.model.SomMark
import com.miguelbits.fridayugc.model.StepResponse
import kotlinx.serialization.json.JsonPrimitive
import kotlin.random.Random

/**
 * Translates brain intents into motor actions at execution time.
 * Reels tap targets: pure vision (screenshot → brain.ground → x,y).
 */
class IntentResolver(
    private val service: FridayAccessibilityService,
    private val brain: BrainClient,
) {
    data class ResolveResult(
        val response: StepResponse,
        val needsScreenshot: Boolean = false,
        val uiKey: String? = null,
    )

    suspend fun resolve(
        intent: StepResponse,
        screen: Screen,
        screenState: ScreenState,
        tracker: SessionTracker,
        screenshotB64: String? = null,
        somMarks: List<SomMark> = emptyList(),
        deviceId: String = "",
        imageWidth: Int = 0,
        imageHeight: Int = 0,
    ): ResolveResult {
        val name = (intent.params["name"] as? JsonPrimitive)?.content?.lowercase().orEmpty()
        return when (name) {
            "enter_reels" -> resolveEnterReels(screen, screenState, screenshotB64, deviceId, imageWidth, imageHeight)
            "watch_reel", "dwell" -> resolveDwell(intent)
            "open_comments" -> resolveOpenComments(screen, screenState, screenshotB64, deviceId, imageWidth, imageHeight)
            "engage_comments" -> resolveEngageComments(screen, tracker, screenshotB64, deviceId, imageWidth, imageHeight)
            "next_reel" -> ResolveResult(
                StepResponse(
                    action = "swipe",
                    params = mapOf(
                        "direction" to JsonPrimitive("up"),
                        "zone" to JsonPrimitive("reels_rail"),
                    ),
                    reason = "intent next_reel",
                ),
            )
            "browse_feed" -> {
                val dir = (intent.params["direction"] as? JsonPrimitive)?.content?.lowercase() ?: "up"
                if (dir == "right") {
                    return ResolveResult(
                        MotorPolicy.navigateReels("blocked browse_feed RIGHT"),
                        uiKey = "nav_reels",
                    )
                }
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

    private suspend fun resolveEnterReels(
        screen: Screen,
        screenState: ScreenState,
        screenshotB64: String?,
        deviceId: String,
        imageWidth: Int = 0,
        imageHeight: Int = 0,
    ): ResolveResult {
        if (screenState.screenType == "story_viewer") {
            return ResolveResult(
                StepResponse(action = "press", params = mapOf("key" to JsonPrimitive("back"))),
            )
        }
        if (ScreenClassifier.likelyReelsSurface(screenState, screen)) {
            return ResolveResult(
                StepResponse(
                    action = "wait",
                    params = mapOf("ms" to JsonPrimitive(300)),
                    reason = "already on reels_viewer",
                ),
            )
        }
        val shot = screenshotB64?.takeIf { it.isNotBlank() } ?: screen.screenshotB64?.takeIf { it.isNotBlank() }
        if (shot != null) {
            return VisionMotor.groundToStep(
                service, brain, "nav_reels", screen, screenState, shot,
                deviceId = deviceId, imageWidth = imageWidth, imageHeight = imageHeight,
            )
        }
        return ResolveResult(
            StepResponse(
                action = "open_reels",
                params = mapOf("ui_key" to JsonPrimitive("nav_reels")),
                reason = "enter_reels — deep link first",
            ),
            uiKey = "nav_reels",
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
        deviceId: String,
        imageWidth: Int = 0,
        imageHeight: Int = 0,
    ): ResolveResult {
        if (screenState.screenType == "comments_sheet") {
            return ResolveResult(
                StepResponse(action = "wait", params = mapOf("ms" to JsonPrimitive(200))),
            )
        }
        return VisionMotor.groundToStep(
            service, brain, "comments_icon", screen, screenState, screenshotB64,
            deviceId = deviceId, imageWidth = imageWidth, imageHeight = imageHeight,
        )
    }

    private suspend fun resolveEngageComments(
        screen: Screen,
        tracker: SessionTracker,
        screenshotB64: String?,
        deviceId: String,
        imageWidth: Int = 0,
        imageHeight: Int = 0,
    ): ResolveResult {
        if (tracker.commentLikesThisReel >= tracker.commentLikesPerReel) {
            return ResolveResult(
                StepResponse(action = "press", params = mapOf("key" to JsonPrimitive("back"))),
            )
        }
        val row = tracker.commentLikesThisReel
        return VisionMotor.groundToStep(
            service,
            brain,
            "comment_heart",
            screen,
            ScreenState(screenType = "comments_sheet"),
            screenshotB64,
            rowIndex = row,
            fallbackAction = "like_comment",
            deviceId = deviceId,
            imageWidth = imageWidth,
            imageHeight = imageHeight,
        )
    }
}
