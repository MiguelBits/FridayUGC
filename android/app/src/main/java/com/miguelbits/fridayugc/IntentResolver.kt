package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.GroundRequest
import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenState
import com.miguelbits.fridayugc.model.SomMark
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
        /** ui_key learned from this bind (nav_reels, comments_icon, comment_heart). */
        val uiKey: String? = null,
    )

    suspend fun resolve(
        intent: StepResponse,
        screen: Screen,
        screenState: ScreenState,
        tracker: SessionTracker,
        screenshotB64: String? = null,
        somMarks: List<SomMark> = emptyList(),
        forceVision: Boolean = false,
    ): ResolveResult {
        val name = (intent.params["name"] as? JsonPrimitive)?.content?.lowercase().orEmpty()
        return when (name) {
            "enter_reels" -> resolveEnterReels(screen, screenState, tracker)
            "watch_reel", "dwell" -> resolveDwell(intent)
            "open_comments" -> resolveOpenComments(screen, screenState, screenshotB64, somMarks, forceVision)
            "engage_comments" -> resolveEngageComments(screen, tracker, screenshotB64, somMarks, forceVision)
            "next_reel" -> ResolveResult(
                StepResponse(action = "swipe", params = mapOf("direction" to JsonPrimitive("up"))),
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
        tracker: SessionTracker,
    ): ResolveResult {
        if (screenState.screenType == "story_viewer") {
            return ResolveResult(
                StepResponse(action = "press", params = mapOf("key" to JsonPrimitive("back"))),
            )
        }
        val hasHomeTabs = screen.elements.any {
            val t = it.text.lowercase()
            t.contains("for you") || t.contains("following")
        }
        val activityLower = screenState.activityClass.lowercase()
        val activityReels = activityLower.contains("clips") ||
            (activityLower.contains("reel") && !activityLower.contains("profile"))
        val reelsNavSelected = screen.elements.any {
            val t = it.text.lowercase()
            t.contains("reels") && t.contains("selected")
        }
        val onReels = tracker.reelsTabOpened && !hasHomeTabs &&
            (activityReels || reelsNavSelected || screenState.screenType == "reels_viewer")
        if (onReels) {
            return ResolveResult(
                StepResponse(
                    action = "wait",
                    params = mapOf("ms" to JsonPrimitive(300)),
                    reason = "already on reels_viewer",
                ),
            )
        }
        // Memory hit for the Reels bottom-nav tab → tap directly. Second run on the
        // same device will land here after the first verified `nav_reels` tap.
        memoryStore.lookup("nav_reels")?.let { (x, y) ->
            return ResolveResult(
                StepResponse(
                    action = "tap",
                    params = mapOf(
                        "x" to JsonPrimitive(x),
                        "y" to JsonPrimitive(y),
                        "ui_key" to JsonPrimitive("nav_reels"),
                    ),
                    reason = "memory bind — nav_reels tap",
                ),
                uiKey = "nav_reels",
            )
        }
        return ResolveResult(
            StepResponse(
                action = "navigate",
                params = mapOf(
                    "tab" to JsonPrimitive("reels"),
                    "ui_key" to JsonPrimitive("nav_reels"),
                ),
                reason = "enter_reels — a11y / deep link (no swipe RIGHT; LEFT only via ReelsEntry)",
            ),
            uiKey = "nav_reels",
        )
    }

    /** Controlled pager LEFT — only ReelsEntry / explicit recovery may call this path. */
    fun resolveEnterReelsPagerSwipe(): ResolveResult = ResolveResult(
        MotorPolicy.pagerSwipeLeft(),
        uiKey = "nav_reels",
    )

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
        forceVision: Boolean = false,
    ): ResolveResult {
        if (screenState.screenType == "comments_sheet") {
            return ResolveResult(
                StepResponse(action = "wait", params = mapOf("ms" to JsonPrimitive(200))),
            )
        }
        val dm = service.resources.displayMetrics
        if (!forceVision) {
            ReelsTargetFinder.findCommentsElement(screen, dm.widthPixels, dm.heightPixels)?.let { e ->
                return ResolveResult(
                    StepResponse(
                        action = "tap",
                        params = mapOf(
                            "target_id" to JsonPrimitive(e.id),
                            "ui_key" to JsonPrimitive("comments_icon"),
                        ),
                        reason = "a11y bind — comments bubble on reels rail",
                    ),
                    uiKey = "comments_icon",
                )
            }
            memoryStore.lookup("comments_icon")?.let { (x, y) ->
                return ResolveResult(
                    StepResponse(
                        action = "tap",
                        params = mapOf(
                            "x" to JsonPrimitive(x),
                            "y" to JsonPrimitive(y),
                            "ui_key" to JsonPrimitive("comments_icon"),
                        ),
                        reason = "memory bind — comments_icon",
                    ),
                    uiKey = "comments_icon",
                )
            }
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
        forceVision: Boolean = false,
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
        val row = tracker.commentLikesThisReel
        if (!forceVision) {
            val hearts = screen.elements.filter { e ->
                if (!e.clickable || e.w <= 0 || e.h <= 0) return@filter false
                val cy = e.y + e.h / 2
                if (cy < sheetMinY) return@filter false
                e.text.lowercase().let { t -> t.contains("like") || t.contains("heart") } ||
                    (e.w <= 120 && e.h <= 120 && e.x + e.w / 2 > w * 0.72f)
            }.sortedBy { it.y }
            if (hearts.isNotEmpty()) {
                val pick = hearts[row.coerceAtMost(hearts.lastIndex)]
                return ResolveResult(
                    StepResponse(
                        action = "like_comment",
                        params = mapOf(
                            "target_id" to JsonPrimitive(pick.id),
                            "ui_key" to JsonPrimitive("comment_heart"),
                        ),
                        reason = "a11y bind — comment heart row $row",
                    ),
                    uiKey = "comment_heart",
                )
            }
            memoryStore.lookup("comment_heart")?.let { (x, y) ->
                return ResolveResult(
                    StepResponse(
                        action = "like_comment",
                        params = mapOf(
                            "x" to JsonPrimitive(x),
                            "y" to JsonPrimitive(y),
                            "ui_key" to JsonPrimitive("comment_heart"),
                        ),
                        reason = "memory bind — comment_heart",
                    ),
                    uiKey = "comment_heart",
                )
            }
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
        somMarks: List<com.miguelbits.fridayugc.model.SomMark> = emptyList(),
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
                    somMarks = somMarks,
                    useSom = somMarks.isNotEmpty(),
                ),
            )
            if (ground.needsScreenshot || ground.params.isEmpty()) {
                ResolveResult(
                    StepResponse(action = "wait", params = mapOf("ms" to JsonPrimitive(400)), reason = ground.reason),
                    needsScreenshot = true,
                    uiKey = anchor,
                )
            } else {
                val paramsWithKey = ground.params + mapOf("ui_key" to JsonPrimitive(anchor))
                ResolveResult(
                    StepResponse(
                        action = ground.action.ifBlank { fallbackAction },
                        params = paramsWithKey,
                        reason = "vision ground: ${ground.reason}",
                    ),
                    uiKey = anchor,
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
