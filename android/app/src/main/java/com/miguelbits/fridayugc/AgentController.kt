package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.AgentProgress
import com.miguelbits.fridayugc.model.LastResult
import com.miguelbits.fridayugc.model.SessionBudget
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

    private suspend fun ensureReelsOpen(svc: FridayAccessibilityService, forceNavigate: Boolean = false) {
        val screen = svc.readScreen()
        val state = ScreenClassifier.classify(screen, svc.currentActivityClass())
        if (!forceNavigate && state.screenType == "reels_viewer" && state.confidence >= 0.55f) return
        onSay("Opening Reels tab…")
        repeat(2) { attempt ->
            val nav = svc.executor.execute(
                StepResponse(
                    action = "navigate",
                    params = mapOf("tab" to JsonPrimitive("reels")),
                ),
            )
            if (nav.ok) return@repeat
            if (attempt == 0) onSay("Reels tab: ${nav.error} — retrying…")
            delay(2000)
        }
        delay(3500)
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

        val wantsReels = goal.lowercase().let { g ->
            g.contains("reel") || g.contains("comment like") || g.contains("comment likes")
        }
        val wantsCommentLikes = goalWantsCommentLikes(goal)
        if (wantsReels) ensureReelsOpen(svc, forceNavigate = wantsCommentLikes)

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
        val appCtx = svc.applicationContext
        val deviceId = FridayPreferences.deviceId(appCtx)
        val memoryStore = DeviceMemoryStore(appCtx)
        val reporter = VerifiedStepReporter(brain, memoryStore, deviceId, voiceScope)

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

            val activity = svc.currentActivityClass()
            val base = svc.readScreen().copy(activity = activity)
            val screenState = ScreenClassifier.classify(base, activity)
            val fingerprint = ScreenValidator.fingerprint(base)
            val stale = ScreenValidator.isStale(lastFingerprint, fingerprint)
            lastFingerprint = fingerprint

            val wantScreenshot = screenState.needsVision ||
                wantsCommentLikes ||
                last?.ok == false ||
                last?.verified in setOf("failed", "unverified") ||
                screenState.confidence < 0.55f ||
                screenState.screenType == "unknown" ||
                base.elements.size < 12
            var screen = if (wantScreenshot) {
                onSay("Sending screenshot to brain…")
                onProgress(AgentProgress.StepThinking(step, withScreenshot = true))
                val b64 = ScreenCapture.captureBase64(svc)
                if (b64 != null) base.copy(screenshotB64 = b64) else base
            } else {
                base
            }

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
                sessionContext = tracker.toContext(),
            )

            onSay("Thinking… step ${step + 1}")
            onProgress(AgentProgress.StepThinking(step))

            var resp: StepResponse = runCatching { brain.step(req) }
                .getOrElse {
                    onSay("Brain unreachable: ${it.message}")
                    onProgress(AgentProgress.SessionEnded(ok = false, reason = "Brain unreachable"))
                    consecutiveFailures++
                    return false
                }

            if (resp.needsScreenshot && screen.screenshotB64.isNullOrBlank()) {
                onSay("Brain requested screenshot — recapturing…")
                val b64 = ScreenCapture.captureBase64(svc)
                if (b64 != null) {
                    screen = base.copy(screenshotB64 = b64)
                    resp = runCatching { brain.step(req.copy(screen = screen)) }.getOrElse {
                        onSay("Brain unreachable on retry: ${it.message}")
                        return false
                    }
                }
            }

            val outcome = handleStep(
                svc, goal, step, resp, screen, history, last, wantsIg, wantsCommentLikes, stale,
                reporter, fingerprint,
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

        if (mode == "read_only" && resp.action in readOnlyBlocked) {
            onSay("Read-only: skipped ${resp.action}.")
            history.add("${resp.action}(blocked)")
            return StepOutcome(null, LastResult(action = resp.action, ok = false, error = "read_only blocked"))
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

        val beforeScreen = screen
        val result = svc.executor.execute(resp)
        var finalAction = resp.action
        var finalOk = result.ok
        var finalError = result.error

        if (!finalOk && resp.action == "navigate" &&
            (resp.params["tab"] as? JsonPrimitive)?.content?.lowercase() == "reels"
        ) {
            onSay("Navigate reels failed — retrying…")
            val retry = svc.executor.execute(
                StepResponse(action = "navigate", params = mapOf("tab" to JsonPrimitive("reels"))),
            )
            finalAction = "navigate"
            finalOk = retry.ok
            finalError = retry.error
        }

        if (!finalOk && resp.action == "tap" && goalWantsInstagram(goal)) {
            onSay("Tap failed — swiping instead…")
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
            tracker.record(finalAction, resp.params)
            consecutiveFailures = 0
            emitBudget()
        } else {
            consecutiveFailures++
            onSay("$finalAction failed: $finalError")
        }

        if (resp.action == "open_app") delay(4000)
        delay(humanDelayMs(finalAction))

        val afterScreen = svc.readScreen()
        val afterFingerprint = ScreenValidator.fingerprint(afterScreen)
        val verification = OutcomeVerifier.verify(
            finalAction, finalOk, beforeScreen, afterScreen, beforeFingerprint, afterFingerprint,
        )
        reporter.report(
            sessionId = sessionId,
            step = step,
            goal = goal,
            action = finalAction,
            params = resp.params,
            executorOk = finalOk,
            verification = verification,
            before = beforeScreen,
            after = afterScreen,
            beforeFp = beforeFingerprint,
            afterFp = afterFingerprint,
            error = finalError,
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

    private fun humanDelayMs(action: String): Long = when (action) {
        "like", "like_story", "like_comment", "comment", "post", "follow", "dm", "save" -> Random.nextLong(2500, 6500)
        "scroll", "swipe", "view_story" -> Random.nextLong(1200, 3500)
        "navigate" -> Random.nextLong(800, 2000)
        else -> Random.nextLong(500, 1800)
    }
}
