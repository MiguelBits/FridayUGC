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

    fun exportContext(): Map<String, JsonElement> = tracker.toContext()

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

        val wantsCommentLikes = goalWantsCommentLikes(goal)
        if (wantsCommentLikes) tracker.phase = "reels_comment_likes"

        val appCtx = svc.applicationContext
        val deviceId = FridayPreferences.deviceId(appCtx)
        val memoryStore = DeviceMemoryStore(appCtx)
        runCatching { memoryStore.hydrateFromBrain(brain, deviceId) }
            .onFailure { onSay("Memory hydrate skipped: ${it.message}") }
        svc.executor.attachMemory(memoryStore)

        if (wantsCommentLikes && !tracker.reelsTabOpened) {
            onSay("Preflight: entering Reels (nav → deep link → swipe LEFT only)…")
            val entry = ReelsEntry.enter(svc, memoryStore) { onSay(it) }
            tracker.reelsTabOpened = entry.reelsTabOpened
            if (!entry.reelsTabOpened) {
                onSay("Preflight Reels entry not confirmed (${entry.screenType}) — brain will retry.")
            }
        }

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

        val history = ArrayList<String>()
        var last: LastResult? = null
        val wantsIg = goalWantsInstagram(goal)
        val intentResolver = IntentResolver(svc, memoryStore, brain)
        val reporter = VerifiedStepReporter(brain, memoryStore, deviceId, voiceScope)
        var stepEnteredAt = System.currentTimeMillis()
        lastIntentUiKey = null
        lastIntentReground = 0

        for (step in 0 until maxSteps) {
            if (shouldStop()) {
                onSay("Stopped by kill switch.")
                onProgress(AgentProgress.SessionEnded(ok = false, reason = "Kill switch"))
                return false
            }
            if (consecutiveFailures >= 8) {
                onSay("Circuit breaker tripped.")
                onProgress(AgentProgress.SessionEnded(ok = false, reason = "Circuit breaker"))
                return false
            }

            if (consecutiveFailures >= 5 && consecutiveFailures % 5 == 0) {
                onSay("Stuck — recovery (back + wait)…")
                svc.executor.execute(
                    StepResponse(action = "press", params = mapOf("key" to JsonPrimitive("back"))),
                )
                delay(900)
                consecutiveFailures = 0
                continue
            }

            val activity = svc.currentActivityClass()
            var base = svc.readScreen().copy(activity = activity)
            var screenState = ScreenClassifier.classify(base, activity)
            if (wantsCommentLikes && screenState.screenType == "story_viewer") {
                onSay("Stories open — pressing back…")
                svc.executor.execute(
                    StepResponse(action = "press", params = mapOf("key" to JsonPrimitive("back"))),
                )
                delay(900)
                base = svc.readScreen().copy(activity = svc.currentActivityClass())
                screenState = ScreenClassifier.classify(base, svc.currentActivityClass())
                tracker.reelsTabOpened = false
            }
            if (wantsCommentLikes) {
                syncReelsTabState(base, screenState)
            }
            val fingerprint = ScreenValidator.fingerprint(base)
            val stale = ScreenValidator.isStale(lastFingerprint, fingerprint)
            lastFingerprint = fingerprint

            svc.updateDebugOverlay(base, FridayPreferences.debugOverlay(svc.applicationContext))

            val wantScreenshot = wantsIg && (
                screenState.screenType in instagramVisionScreens ||
                screenState.needsVision ||
                wantsCommentLikes ||
                last?.ok == false ||
                last?.verified in setOf("failed", "unverified") ||
                screenState.confidence < 0.55f ||
                base.elements.size < 12
            )
            var screen = if (wantScreenshot) {
                onSay("Sending screenshot to brain…")
                onProgress(AgentProgress.StepThinking(step, withScreenshot = true))
                val cap = ScreenCapture.captureForGrounding(
                    svc,
                    base,
                    useSom = FridayPreferences.somEnabled(svc.applicationContext),
                )
                if (cap != null) base.copy(screenshotB64 = cap.screenshotB64) else base
            } else {
                base
            }

            val dwellMs = (System.currentTimeMillis() - stepEnteredAt).coerceAtMost(60_000)
            stepEnteredAt = System.currentTimeMillis()
            val contextWithDwell = tracker.toContext() + mapOf(
                "dwell_on_screen_ms" to JsonPrimitive(dwellMs),
            )

            val req = StepRequest(
                sessionId = sessionId,
                goal = goal,
                step = step,
                screen = screen,
                lastResult = last,
                history = history.takeLast(12),
                mode = mode,
                deviceId = deviceId,
                screenFingerprint = fingerprint,
                screenState = screenState,
                sessionContext = contextWithDwell,
            )

            onSay("Thinking… step ${step + 1}")
            onProgress(AgentProgress.StepThinking(step))

            val resp: StepResponse = runCatching { brain.step(req) }
                .getOrElse {
                    onSay("Brain unreachable: ${it.message}")
                    onProgress(AgentProgress.SessionEnded(ok = false, reason = "Brain unreachable"))
                    consecutiveFailures++
                    return false
                }

            var finalResp = resp

            if (finalResp.needsScreenshot && screen.screenshotB64.isNullOrBlank()) {
                onSay("Brain requested screenshot — recapturing…")
                val cap = ScreenCapture.captureForGrounding(
                    svc,
                    base,
                    useSom = FridayPreferences.somEnabled(svc.applicationContext),
                )
                if (cap != null) {
                    screen = base.copy(screenshotB64 = cap.screenshotB64)
                    finalResp = runCatching { brain.step(req.copy(screen = screen)) }.getOrElse {
                        onSay("Brain unreachable on retry: ${it.message}")
                        return false
                    }
                }
            }

            val outcome = handleStep(
                svc, goal, step, finalResp, screen, history, last, wantsIg, wantsCommentLikes, stale,
                reporter, fingerprint, intentResolver, memoryStore,
            )
            last = outcome.lastResult
            if (outcome.terminal != null) {
                onProgress(AgentProgress.SessionEnded(ok = outcome.terminal, reason = if (outcome.terminal) "Done" else "Stopped"))
                return outcome.terminal
            }
        }
        onSay("Reached step limit; stopping to stay safe.")
        onProgress(AgentProgress.SessionEnded(ok = false, reason = "Step limit"))
        return false
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
            if (text.isNotBlank()) voiceScope.launch { voice.speakFromBrain(brain, text) }
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
        if (wantsCommentLikes) {
            val screenType = ScreenClassifier.classify(screen, svc.currentActivityClass()).screenType
            MotorPolicy.clampCommentLikes(resp, tracker.reelsTabOpened, screenType)?.let { toExecute = it }
        }
        if (isStuckEnteringReels(history, wantsCommentLikes)) {
            onSay("Stuck on home — full Reels entry recovery…")
            val entry = ReelsEntry.enter(svc, memoryStore) { onSay(it) }
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
        } else if (isStuckOnWait(history, wantsCommentLikes, screen, svc)) {
            onSay("Wait loop on home — forcing Reels entry…")
            tracker.reelsTabOpened = false
            val entry = ReelsEntry.enter(svc, memoryStore) { onSay(it) }
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
            var resolved = intentResolver.resolve(
                resp, screen, ScreenClassifier.classify(screen, svc.currentActivityClass()), tracker, shot,
            )
            // If previous intent tap on the same anchor was unverified, force fresh
            // grounding: dump memory hit, capture new screenshot, re-ground.
            val intentName = (resp.params["name"] as? JsonPrimitive)?.content?.lowercase().orEmpty()
            val prevUnverified = last?.verified in setOf("failed", "unverified") &&
                lastIntentUiKey != null && intentName in setOf("open_comments", "engage_comments")
            if (prevUnverified && lastIntentReground < 2) {
                onSay("Previous intent tap unverified — re-grounding via vision…")
                val cap = ScreenCapture.captureForGrounding(
                    svc,
                    screen,
                    useSom = FridayPreferences.somEnabled(svc.applicationContext),
                )
                if (cap != null) {
                    shot = cap.screenshotB64
                    resolved = intentResolver.resolve(
                        resp,
                        screen.copy(screenshotB64 = cap.screenshotB64),
                        ScreenClassifier.classify(screen, svc.currentActivityClass()),
                        tracker,
                        screenshotB64 = cap.screenshotB64,
                        somMarks = cap.somMarks,
                        forceVision = true,
                    )
                    lastIntentReground += 1
                }
            } else if (resolved.needsScreenshot) {
                onSay("Intent needs vision — grounding with Gemma…")
                val cap = ScreenCapture.captureForGrounding(
                    svc,
                    screen,
                    useSom = FridayPreferences.somEnabled(svc.applicationContext),
                )
                if (cap != null) {
                    shot = cap.screenshotB64
                    resolved = intentResolver.resolve(
                        resp,
                        screen.copy(screenshotB64 = cap.screenshotB64),
                        ScreenClassifier.classify(screen, svc.currentActivityClass()),
                        tracker,
                        screenshotB64 = cap.screenshotB64,
                        somMarks = cap.somMarks,
                    )
                }
            }
            toExecute = resolved.response.copy(
                say = resp.say ?: resolved.response.say,
                reason = resp.reason.ifBlank { resolved.response.reason },
            )
            lastIntentUiKey = resolved.uiKey
            if (resolved.needsScreenshot) {
                onSay("Grounding failed — need clearer screenshot.")
                history.add("intent(ground-failed)")
                return StepOutcome(null, LastResult(action = "intent", ok = false, error = "grounding_failed"))
            }
            onSay("Intent → ${toExecute.action} @${resolved.uiKey ?: "-"}")
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
        if (finalOk) {
            tracker.record(finalAction, toExecute.params)
            consecutiveFailures = 0
            emitBudget()
        } else {
            consecutiveFailures++
            onSay("$finalAction failed: $finalError")
        }

        if (toExecute.action == "open_app") delay(4000)
        delay(humanDelayMs(finalAction))

        val afterScreen = svc.readScreen()
        if (finalOk && wantsCommentLikes) {
            val afterState = ScreenClassifier.classify(afterScreen, svc.currentActivityClass())
            when (finalAction) {
                "tap" -> {
                    if (toExecute.reason.contains("open_comments") || toExecute.reason.contains("vision ground")) {
                        when {
                            afterState.screenType == "comments_sheet" -> tracker.commentsSheetOpen = true
                            ReelsTargetFinder.isAudioBrowser(afterScreen) -> {
                                onSay("Opened audio by mistake — going back.")
                                svc.executor.execute(
                                    StepResponse(action = "press", params = mapOf("key" to JsonPrimitive("back"))),
                                )
                                tracker.commentsSheetOpen = false
                            }
                        }
                    } else if (afterState.screenType == "comments_sheet") {
                        tracker.commentsSheetOpen = true
                    }
                }
                "like_comment" -> {
                    if (afterState.screenType == "comments_sheet") {
                        tracker.commentsSheetOpen = true
                    }
                }
                "press" -> tracker.commentsSheetOpen = false
                "swipe" -> {
                    val dir = (toExecute.params["direction"] as? JsonPrimitive)?.content
                    if (dir == "left" && finalOk) {
                        tracker.reelsTabOpened = ScreenClassifier.likelyReelsSurface(afterState, afterScreen)
                    }
                }
                "navigate" -> {
                    val tab = (toExecute.params["tab"] as? JsonPrimitive)?.content?.lowercase()
                    if (tab == "reels" && finalOk) {
                        tracker.reelsTabOpened = ScreenClassifier.likelyReelsSurface(afterState, afterScreen)
                    }
                }
            }
        }
        val afterFingerprint = ScreenValidator.fingerprint(afterScreen)
        val verification = OutcomeVerifier.verify(
            finalAction, finalOk, beforeScreen, afterScreen, beforeFingerprint, afterFingerprint,
        )
        reporter.report(
            sessionId = sessionId,
            step = step,
            goal = goal,
            action = finalAction,
            params = toExecute.params,
            executorOk = finalOk,
            verification = verification,
            before = beforeScreen,
            after = afterScreen,
            beforeFp = beforeFingerprint,
            afterFp = afterFingerprint,
            error = finalError,
        )
        if (verification.status == "verified") lastIntentReground = 0
        onSay(
            "step=${step + 1} action=$finalAction verify=${verification.status} " +
                "screen=${ScreenClassifier.classify(afterScreen, svc.currentActivityClass()).screenType} " +
                "reels=${if (tracker.reelsTabOpened) 1 else 0} ui_key=${lastIntentUiKey ?: "-"}"
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
        if (ScreenClassifier.hasHomeFeedTabs(screen) || state.screenType == "home_feed") {
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
        val idle = setOf("wait", "navigate", "intent(ground-failed)")
        return tail.count { it in idle || it.startsWith("navigate") || it.startsWith("reels_entry") } >= 3 &&
            !tracker.reelsTabOpened
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
}
