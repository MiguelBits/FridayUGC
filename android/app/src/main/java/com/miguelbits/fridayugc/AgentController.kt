package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.AgentProgress
import com.miguelbits.fridayugc.model.LastResult
import com.miguelbits.fridayugc.model.SessionBudget
import com.miguelbits.fridayugc.model.ScreenState
import com.miguelbits.fridayugc.model.StepRequest
import com.miguelbits.fridayugc.model.StepResponse
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive
import java.util.UUID
import kotlin.random.Random

/**
 * Observe → decide → act loop for full UGC operator sessions.
 */
class AgentController(
    private val brain: BrainClient,
    private val voice: VoiceManager,
    private val mode: String = "read_only",
    initialBudget: SessionBudget? = null,
    private val onSay: (String) -> Unit = {},
    private val onProgress: (AgentProgress) -> Unit = {},
    private val onApproval: suspend (StepResponse) -> Boolean = { false },
    private val maxSteps: Int = if (mode == "full") 150 else 40,
    private val autonomous: Boolean = false,
    private val sessionId: String = UUID.randomUUID().toString(),
    private val taskId: String? = null,
    private val taskKind: String? = null,
    private val onCheckpoint: (AgentSessionStore.Checkpoint) -> Unit = {},
    private val shouldStop: () -> Boolean = { false },
) {
    private val readOnlyBlocked = setOf(
        "post", "comment", "dm", "follow", "unfollow", "like", "like_story", "like_comment", "save", "type",
    )
    private val tracker = SessionTracker().apply { initialBudget?.let { applyFromBudget(it) } }
    private val voiceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var lastFingerprint: String? = null
    private var consecutiveFailures = 0
    private var lastIntentUiKey: String? = null
    private var lastIntentReground = 0
    private var forceVisionRetry = false
    private val anchorVerifyFails = mutableMapOf<String, Int>()

    fun exportContext(): Map<String, JsonElement> = tracker.toContext()

    private suspend fun fetchBrainStep(req: StepRequest): StepResponse? =
        runCatching { brain.step(req) }
            .getOrElse {
                onSay("Brain unreachable: ${it.message}")
                onProgress(AgentProgress.SessionEnded(ok = false, reason = "Brain unreachable"))
                consecutiveFailures++
                null
            }

    private fun emitBudget() {
        onProgress(AgentNotificationManager.budgetLineFrom(tracker))
    }

    private fun goalWantsInstagram(goal: String): Boolean {
        val g = goal.lowercase()
        return g.contains("instagram") || g.contains("insta") || g.contains(" ig") ||
            g.contains("scroll") || g.contains("reel") || g.contains("feed") ||
            g.contains("like") || g.contains("story") || g.contains("inbox") ||
            g.contains("post")
    }

    private fun goalWantsCommentLikes(goal: String): Boolean {
        val g = goal.lowercase()
        return (g.contains("like") && g.contains("comment") && (g.contains("reel") || g.contains("reels"))) ||
            g.contains("reels_comment_likes")
    }

    private fun goalWantsPosting(goal: String): Boolean {
        val g = goal.lowercase()
        return g.contains("post") && (g.contains("reel") || g.contains("story") || g.contains("carousel"))
    }

    private suspend fun ensureInstagramOpen(svc: FridayAccessibilityService) {
        if (svc.currentPackage().contains("instagram", ignoreCase = true)) return
        onSay("Opening Instagram…")
        val open = svc.executor.execute(
            StepResponse(
                action = "open_app",
                params = mapOf("package" to JsonPrimitive("com.instagram.android")),
            ),
        )
        if (!open.ok) onSay("Instagram open failed: ${open.error}")
        delay(5000)
    }

    suspend fun runGoal(
        goal: String,
        resumeContext: Map<String, JsonElement> = emptyMap(),
    ): Boolean {
        val svc = FridayAccessibilityService.instance
            ?: run { onSay("Accessibility service is not enabled."); return false }

        if (resumeContext.isNotEmpty()) tracker.applyContext(resumeContext)

        onSay("Starting session…")
        onProgress(
            AgentProgress.SessionStarted(
                goal = goal,
                maxSteps = maxSteps,
                taskKind = taskKind,
                taskId = taskId,
                sessionId = sessionId,
            ),
        )
        emitBudget()
        svc.executor.execute(
            StepResponse(action = "press", params = mapOf("key" to JsonPrimitive("home"))),
        )
        delay(800)

        if (goalWantsInstagram(goal)) ensureInstagramOpen(svc)

        if (goalWantsCommentLikes(goal)) tracker.phase = "reels_comment_likes"

        if (goalWantsPosting(goal)) {
            val prefs = svc.applicationContext.getSharedPreferences("friday_gallery", android.content.Context.MODE_PRIVATE)
            val mediaUri = prefs.all.entries.firstOrNull { it.key.startsWith("asset:") }?.value?.toString()
            if (mediaUri != null) {
                val posting = PostingController(svc.executor)
                val caption = tracker.toContext()["caption"]?.let { (it as? JsonPrimitive)?.content } ?: ""
                val result = if (goal.contains("story", ignoreCase = true)) {
                    posting.postStory(mediaUri)
                } else {
                    posting.postReel(mediaUri, caption)
                }
                if (result.ok) {
                    onSay("Post succeeded.")
                    onProgress(AgentProgress.SessionEnded(ok = true, reason = "Posted"))
                    return true
                }
                onSay("Posting helper failed: ${result.error}")
                onProgress(AgentProgress.SessionEnded(ok = false, reason = result.error ?: "post failed"))
            }
        }

        return ThinAgentLoop(
            svc = svc,
            brain = brain,
            voice = voice,
            tracker = tracker,
            mode = mode,
            sessionId = sessionId,
            goal = goal,
            maxSteps = maxSteps,
            autonomous = autonomous,
            taskId = taskId,
            onSay = onSay,
            onProgress = onProgress,
            onCheckpoint = onCheckpoint,
            onApproval = onApproval,
            shouldStop = shouldStop,
        ).run()
    }

    private data class StepOutcome(val terminal: Boolean?, val lastResult: LastResult?)

    private suspend fun handleStep(
        svc: FridayAccessibilityService,
        goal: String,
        step: Int,
        resp: StepResponse,
        screen: com.miguelbits.fridayugc.model.Screen,
        history: ArrayList<String>,
        last: LastResult?,
        wantsIg: Boolean,
        wantsCommentLikes: Boolean,
        stale: Boolean,
        reporter: VerifiedStepReporter,
        beforeFingerprint: String,
        intentResolver: IntentResolver,
        memoryStore: DeviceMemoryStore,
        deviceId: String,
    ): StepOutcome {
        onSay("Step ${step + 1}: ${resp.action} (${screen.app.ifBlank { "unknown" }})")
        onProgress(
            AgentProgress.StepDecided(
                step = step,
                action = resp.action,
                app = screen.app,
                say = resp.say,
            ),
        )

        resp.say?.let { text ->
            if (text.isNotBlank() && voice.speakEnabled) {
                voiceScope.launch { voice.speakFromBrain(brain, text) }
            }
        }

        onCheckpoint(
            AgentSessionStore.Checkpoint(
                sessionId = sessionId,
                taskId = taskId,
                goal = goal,
                step = step,
                history = history.toList(),
                sessionContextJson = tracker.toContext().toString(),
            ),
        )

        if (resp.done || resp.action == "done") {
            val onIg = screen.app.contains("instagram", ignoreCase = true)
            if (step < 5 && wantsIg && !onIg) {
                onSay("Still starting — opening Instagram…")
                history.add("done(ignored)")
                val open = svc.executor.execute(
                    StepResponse(
                        action = "open_app",
                        params = mapOf("package" to JsonPrimitive("com.instagram.android")),
                    ),
                )
                history.add("open_app")
                delay(4000)
                val after = svc.readScreen()
                val afterFp = ScreenValidator.fingerprint(after)
                val verification = OutcomeVerifier.verify(
                    "open_app", open.ok, screen, after, beforeFingerprint, afterFp,
                )
                reporter.report(
                    sessionId, step, goal, "open_app",
                    mapOf("package" to JsonPrimitive("com.instagram.android")),
                    open.ok, verification, screen, after, beforeFingerprint, afterFp, open.error,
                )
                return StepOutcome(
                    null,
                    LastResult(action = "open_app", ok = open.ok, error = open.error, verified = verification.status, changeScore = verification.changeScore),
                )
            }
            onSay("Task complete.")
            consecutiveFailures = 0
            onProgress(AgentProgress.StepExecuted(step, "done", ok = true))
            emitBudget()
            return StepOutcome(true, LastResult(action = "done", ok = true, verified = "verified"))
        }
        if (resp.action == "fail") {
            onSay("Stopped: ${resp.reason}")
            onProgress(AgentProgress.StepExecuted(step, "fail", ok = false, error = resp.reason))
            return StepOutcome(false, LastResult(action = "fail", ok = false, error = resp.reason))
        }

        if (resp.approvalRequired && !autonomous) {
            val approved = onApproval(resp)
            if (!approved) {
                history.add("${resp.action}(declined)")
                return StepOutcome(null, LastResult(action = resp.action, ok = false, error = "user declined"))
            }
        }

        if (ScreenValidator.needsReobserve(resp.action) || stale) {
            delay(400)
            val fresh = svc.readScreen()
            if (ScreenValidator.isStale(ScreenValidator.fingerprint(screen), ScreenValidator.fingerprint(fresh))) {
                onSay("Stale screen — re-observing before ${resp.action}")
                delay(600)
            }
        }

        val x = (resp.params["x"] as? JsonPrimitive)?.content?.toIntOrNull()
        val y = (resp.params["y"] as? JsonPrimitive)?.content?.toIntOrNull()
        if (x != null && y != null && wantsCommentLikes) {
            val dm = svc.resources.displayMetrics
            if (CommentLikesRoutine.isReelLikeZone(x, y, dm.widthPixels, dm.heightPixels) &&
                tracker.commentLikesPhase != CommentLikesRoutine.PHASE_ON_REELS
            ) {
                onSay("Blocked reel-like zone tap during comments.")
                history.add("tap(reel-like-blocked)")
                return StepOutcome(null, LastResult(action = "tap", ok = false, error = "reel like zone"))
            }
        }

        if (x != null && y != null) {
            ScreenValidator.validateTap(screen, x, y)?.let { err ->
                onSay("Invalid tap: $err")
                history.add("tap(invalid)")
                consecutiveFailures++
                return StepOutcome(null, LastResult(action = "tap", ok = false, error = err))
            }
        }

        if (resp.action == "wait") {
            val ms = (resp.params["ms"] as? JsonPrimitive)?.content?.toLongOrNull() ?: 500L
            delay(ms)
            history.add("wait")
            return StepOutcome(null, LastResult(action = "wait", ok = true, verified = "unknown"))
        }

        var toExecute = resp
        var groundingScreenshotB64: String? = null
        if (wantsCommentLikes) {
            val screenType = ScreenClassifier.classify(screen, svc.currentActivityClass()).screenType
            MotorPolicy.clampCommentLikes(resp, tracker.reelsTabOpened, screenType)?.let { toExecute = it }
        }
        if (isStuckEnteringReels(history, wantsCommentLikes)) {
            onSay("Stuck on home — full Reels entry recovery…")
            val entry = ReelsEntry.enter(svc, brain) { onSay(it) }
            tracker.reelsTabOpened = entry.reelsTabOpened
            history.add("reels_entry(recovery)")
            return StepOutcome(
                null,
                LastResult(
                    action = "navigate",
                    ok = entry.ok,
                    error = if (entry.ok) null else "reels entry recovery incomplete",
                    verified = if (entry.reelsTabOpened) "verified" else "unverified",
                ),
            )
        } else if (isStuckOnOpenReels(history, wantsCommentLikes, screen, svc)) {
            onSay("open_reels loop — full Reels entry recovery…")
            val entry = ReelsEntry.enter(svc, brain) { onSay(it) }
            tracker.reelsTabOpened = entry.reelsTabOpened
            history.add("reels_entry(open-reels-loop)")
            return StepOutcome(
                null,
                LastResult(
                    action = "navigate",
                    ok = entry.ok,
                    verified = if (entry.reelsTabOpened) "verified" else "unverified",
                    error = if (entry.ok) null else "open_reels loop recovery incomplete",
                ),
            )
        } else if (isStuckOnWait(history, wantsCommentLikes, screen, svc)) {
            onSay("Wait loop on home — forcing Reels entry…")
            tracker.reelsTabOpened = false
            val entry = ReelsEntry.enter(svc, brain) { onSay(it) }
            tracker.reelsTabOpened = entry.reelsTabOpened
            history.add("reels_entry(wait-break)")
            return StepOutcome(
                null,
                LastResult(
                    action = "navigate",
                    ok = entry.ok,
                    verified = if (entry.reelsTabOpened) "verified" else "unverified",
                ),
            )
        } else if (resp.action == "intent") {
            var shot = screen.screenshotB64
            var shotW = 0
            var shotH = 0
            val intentName = (resp.params["name"] as? JsonPrimitive)?.content?.lowercase().orEmpty()
            if (wantsCommentLikes && intentName == "open_comments" &&
                (anchorVerifyFails["comments_icon"] ?: 0) >= 4 &&
                tracker.commentLikesPhase == CommentLikesRoutine.PHASE_ON_REELS
            ) {
                onSay("Comments icon stuck — skipping to next reel…")
                anchorVerifyFails["comments_icon"] = 0
                tracker.commentsSheetOpen = false
                tracker.commentLikesPhase = CommentLikesRoutine.PHASE_ON_REELS
                tracker.readyForNextReel = false
                toExecute = StepResponse(
                    action = "swipe",
                    params = mapOf(
                        "direction" to JsonPrimitive("up"),
                        "zone" to JsonPrimitive("reels_rail"),
                    ),
                    reason = "vision stuck recovery — next reel",
                )
                lastIntentUiKey = "comments_icon"
            } else {
                val prevUnverified = last?.verified in setOf("failed", "unverified") &&
                    lastIntentUiKey in VisionMotor.REELS_ANCHORS
                val regroundCap = 2
                val needReground = (forceVisionRetry || prevUnverified) && lastIntentReground < regroundCap
                var resolved = intentResolver.resolve(
                    resp,
                    screen,
                    ScreenClassifier.classify(screen, svc.currentActivityClass()),
                    tracker,
                    shot,
                    deviceId = deviceId,
                    imageWidth = shotW,
                    imageHeight = shotH,
                )
                if (resolved.needsScreenshot || needReground) {
                    onSay("Vision grounding for $intentName (Ollama may take ~30s)…")
                    val cap = ScreenCapture.captureForGrounding(svc, screen, useSom = false)
                    if (cap != null) {
                        shot = cap.screenshotB64
                        shotW = cap.imageWidth
                        shotH = cap.imageHeight
                        groundingScreenshotB64 = shot
                        resolved = intentResolver.resolve(
                            resp,
                            screen.copy(screenshotB64 = cap.screenshotB64),
                            ScreenClassifier.classify(screen, svc.currentActivityClass()),
                            tracker,
                            screenshotB64 = cap.screenshotB64,
                            deviceId = deviceId,
                            imageWidth = shotW,
                            imageHeight = shotH,
                        )
                        if (needReground) lastIntentReground += 1
                    }
                }
                toExecute = resolved.response.copy(
                    say = resp.say ?: resolved.response.say,
                    reason = resp.reason.ifBlank { resolved.response.reason },
                )
                lastIntentUiKey = resolved.uiKey
                val failStreak = resolved.uiKey?.let { anchorVerifyFails[it] ?: 0 } ?: 0
                if (failStreak >= 2 && toExecute.action in setOf("tap", "like_comment")) {
                    toExecute = jitterVisionTap(toExecute, failStreak)
                    onSay("Retry with offset (fail streak $failStreak)…")
                }
                if (resolved.needsScreenshot) {
                    onSay("Grounding failed — need clearer screenshot.")
                    history.add("intent(ground-failed)")
                    return StepOutcome(null, LastResult(action = "intent", ok = false, error = "grounding_failed"))
                }
                val gx = (toExecute.params["x"] as? JsonPrimitive)?.content
                val gy = (toExecute.params["y"] as? JsonPrimitive)?.content
                onSay("Intent → ${toExecute.action} @${resolved.uiKey ?: "-"} ($gx,$gy)")
            }
        } else {
            lastIntentUiKey = null
        }

        if (mode == "read_only" && toExecute.action in readOnlyBlocked) {
            if (!(wantsCommentLikes && toExecute.action == "like_comment")) {
                onSay("Read-only: skipped ${toExecute.action}.")
                history.add("${toExecute.action}(blocked)")
                return StepOutcome(null, LastResult(action = toExecute.action, ok = false, error = "read_only blocked"))
            }
        }

        val beforeScreen = screen
        val result = svc.executor.execute(toExecute)
        var finalAction = toExecute.action
        var finalOk = result.ok
        var finalError = result.error

        // NO pager swipe fallback on navigate=reels failure — pager swipes cause the
        // RIGHT-swipe bug and violate the "no phone-side choreography" rule. On failure
        // let the main loop request a screenshot and route through IntentResolver +
        // vision grounding on the next step.

        if (!finalOk && toExecute.action == "tap" && goalWantsInstagram(goal) && !wantsCommentLikes) {
            onSay("Tap failed — trying next reel…")
            val swipe = svc.executor.execute(
                StepResponse(action = "swipe", params = mapOf("direction" to JsonPrimitive("up"))),
            )
            finalAction = "swipe"
            finalOk = swipe.ok
            finalError = swipe.error
        }

        history.add(finalAction)
        onProgress(AgentProgress.StepExecuted(step, finalAction, ok = finalOk, error = finalError))

        if (toExecute.action == "open_app") delay(4000)
        delay(humanDelayMs(finalAction))

        val afterScreen = svc.readScreen()
        val afterFingerprint = ScreenValidator.fingerprint(afterScreen)
        val afterState = ScreenClassifier.classify(afterScreen, svc.currentActivityClass())
        val verification = OutcomeVerifier.verify(
            finalAction,
            finalOk,
            beforeScreen,
            afterScreen,
            beforeFingerprint,
            afterFingerprint,
            toExecute.params,
            svc.currentActivityClass(),
        )

        val onCommentsSheet = ScreenClassifier.isFullCommentsSheet(afterScreen, svc.currentActivityClass())
        val countsForBudget = !wantsCommentLikes ||
            verification.status == "verified" ||
            finalAction !in setOf("tap", "like_comment") ||
            (finalOk && onCommentsSheet && finalAction in setOf("tap", "like_comment"))
        if (finalOk && countsForBudget) {
            tracker.record(finalAction, toExecute.params)
            consecutiveFailures = 0
            emitBudget()
        } else if (finalOk) {
            onSay("$finalAction sent but screen did not confirm — not counting progress.")
            consecutiveFailures++
        } else {
            consecutiveFailures++
            onSay("$finalAction failed: $finalError")
        }

        if (finalOk && wantsCommentLikes) {
            when (finalAction) {
                "tap" -> {
                    when {
                        ReelsTargetFinder.isAudioBrowser(afterScreen) -> {
                            onSay("Opened audio by mistake — clearing memory and going back.")
                            memoryStore.invalidate("comments_icon")
                            forceVisionRetry = true
                            tracker.commentsSheetOpen = false
                            tracker.commentLikesPhase = CommentLikesRoutine.PHASE_ON_REELS
                            svc.executor.execute(
                                StepResponse(action = "press", params = mapOf("key" to JsonPrimitive("back"))),
                            )
                        }
                        onCommentsSheet -> {
                            tracker.commentsSheetOpen = true
                            CommentLikesRoutine.onActionCompleted(tracker, "tap", ok = true)
                            forceVisionRetry = false
                            lastIntentReground = 0
                        }
                    }
                }
                "like_comment" -> {
                    if (onCommentsSheet) {
                        tracker.commentsSheetOpen = true
                        tracker.commentLikesPhase = CommentLikesRoutine.PHASE_IN_COMMENTS
                    }
                }
                "scroll" -> {
                    val zone = (toExecute.params["zone"] as? JsonPrimitive)?.content?.lowercase()
                    if (zone == "comments_sheet") {
                        tracker.commentsSheetOpen = true
                        tracker.commentLikesPhase = CommentLikesRoutine.PHASE_IN_COMMENTS
                    }
                }
                "press" -> {
                    val key = (toExecute.params["key"] as? JsonPrimitive)?.content?.lowercase()
                    if (key == "back") tracker.commentsSheetOpen = false
                }
                "swipe" -> {
                    val dir = (toExecute.params["direction"] as? JsonPrimitive)?.content
                    if (dir == "left" && finalOk) {
                        tracker.reelsTabOpened = ScreenClassifier.likelyReelsSurface(afterState, afterScreen)
                    }
                }
                "navigate", "open_reels" -> {
                    val tab = (toExecute.params["tab"] as? JsonPrimitive)?.content?.lowercase()
                    if ((tab == "reels" || finalAction == "open_reels") && finalOk) {
                        tracker.reelsTabOpened = ScreenClassifier.likelyReelsSurface(afterState, afterScreen)
                    }
                }
            }
        }

        if (wantsCommentLikes && lastIntentUiKey != null && finalAction in setOf("tap", "like_comment")) {
            if (verification.status == "verified") {
                anchorVerifyFails[lastIntentUiKey!!] = 0
                forceVisionRetry = false
            } else if (finalOk && (onCommentsSheet || lastIntentUiKey == "nav_reels")) {
                anchorVerifyFails[lastIntentUiKey!!] = 0
                forceVisionRetry = false
            } else {
                anchorVerifyFails[lastIntentUiKey!!] = (anchorVerifyFails[lastIntentUiKey] ?: 0) + 1
                forceVisionRetry = true
            }
        }

        val enrichedParams = toExecute.params + mapOf(
            "screen_width" to JsonPrimitive(svc.resources.displayMetrics.widthPixels),
            "screen_height" to JsonPrimitive(svc.resources.displayMetrics.heightPixels),
        )
        reporter.report(
            sessionId = sessionId,
            step = step,
            goal = goal,
            action = finalAction,
            params = enrichedParams,
            executorOk = finalOk,
            verification = verification,
            before = beforeScreen,
            after = afterScreen,
            beforeFp = beforeFingerprint,
            afterFp = afterFingerprint,
            error = finalError,
            screenshotB64 = groundingScreenshotB64 ?: beforeScreen.screenshotB64,
        )
        if (verification.status == "verified") lastIntentReground = 0
        onSay(
            "step=${step + 1} action=$finalAction verify=${verification.status} " +
                "screen=${afterState.screenType} " +
                "reels=${if (tracker.reelsTabOpened) 1 else 0} phase=${tracker.commentLikesPhase} " +
                "ui_key=${lastIntentUiKey ?: "-"}"
        )

        return StepOutcome(
            null,
            LastResult(
                action = finalAction,
                ok = finalOk,
                error = finalError,
                verified = verification.status,
                changeScore = verification.changeScore,
            ),
        )
    }

    private fun syncReelsTabState(screen: com.miguelbits.fridayugc.model.Screen, state: ScreenState) {
        if (ScreenClassifier.hasHomeFeedTabs(screen) ||
            (state.screenType == "home_feed" && state.confidence >= 0.8f)
        ) {
            tracker.reelsTabOpened = false
            return
        }
        if (ScreenClassifier.likelyReelsSurface(state, screen)) {
            tracker.reelsTabOpened = true
        }
    }

    private fun isStuckEnteringReels(history: List<String>, wantsCommentLikes: Boolean): Boolean {
        if (!wantsCommentLikes || history.size < 4) return false
        val tail = history.takeLast(4)
        val idle = setOf("wait", "navigate", "intent(ground-failed)", "open_reels")
        return tail.count { it in idle || it.startsWith("navigate") || it.startsWith("reels_entry") } >= 3 &&
            !tracker.reelsTabOpened
    }

    private fun isStuckOnOpenReels(
        history: List<String>,
        wantsCommentLikes: Boolean,
        screen: com.miguelbits.fridayugc.model.Screen,
        svc: FridayAccessibilityService,
    ): Boolean {
        if (!wantsCommentLikes || history.size < 3) return false
        val tail = history.takeLast(5)
        if (tail.count { it == "open_reels" } < 3) return false
        val state = ScreenClassifier.classify(screen, svc.currentActivityClass())
        return !ScreenClassifier.likelyReelsSurface(state, screen)
    }

    private fun isStuckOnWait(
        history: List<String>,
        wantsCommentLikes: Boolean,
        screen: com.miguelbits.fridayugc.model.Screen,
        svc: FridayAccessibilityService,
    ): Boolean {
        if (!wantsCommentLikes || history.size < 3) return false
        val tail = history.takeLast(3)
        if (!tail.all { it == "wait" }) return false
        val state = ScreenClassifier.classify(screen, svc.currentActivityClass())
        return ScreenClassifier.hasHomeFeedTabs(screen) ||
            state.screenType == "home_feed" ||
            !ScreenClassifier.likelyReelsSurface(state, screen)
    }

    private val instagramVisionScreens = setOf(
        "reels_viewer", "comments_sheet", "home_feed", "unknown", "story_viewer",
    )

    private fun humanDelayMs(action: String): Long = when (action) {
        "like", "like_story", "like_comment", "comment", "post", "follow", "dm", "save" -> Random.nextLong(2500, 6500)
        "scroll", "swipe", "view_story" -> Random.nextLong(1200, 3500)
        "navigate" -> Random.nextLong(800, 2000)
        else -> Random.nextLong(500, 1800)
    }

    private fun jitterVisionTap(step: StepResponse, failStreak: Int): StepResponse {
        val x = (step.params["x"] as? JsonPrimitive)?.content?.toIntOrNull() ?: return step
        val y = (step.params["y"] as? JsonPrimitive)?.content?.toIntOrNull() ?: return step
        val spread = 18 * failStreak.coerceAtMost(4)
        val nx = (x + Random.nextInt(-spread, spread + 1)).coerceAtLeast(0)
        val ny = (y + Random.nextInt(-spread, spread + 1)).coerceAtLeast(0)
        return step.copy(
            params = step.params + mapOf(
                "x" to JsonPrimitive(nx),
                "y" to JsonPrimitive(ny),
            ),
            reason = "${step.reason} (jitter retry)",
        )
    }
}
