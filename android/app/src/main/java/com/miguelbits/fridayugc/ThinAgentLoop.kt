package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.AgentProgress
import com.miguelbits.fridayugc.model.ObserveBundle
import com.miguelbits.fridayugc.model.StepResponse
import com.miguelbits.fridayugc.model.TickLastResult
import com.miguelbits.fridayugc.model.TickRequest
import com.miguelbits.fridayugc.model.TickResponse
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonPrimitive

/**
 * Thin-client agent loop: observe → POST /agent/tick → execute atomic action.
 * Brain owns verify, plan, ground, and session_context.
 */
class ThinAgentLoop(
    private val svc: FridayAccessibilityService,
    private val brain: BrainClient,
    private val voice: VoiceManager,
    private val tracker: SessionTracker,
    private val mode: String,
    private val sessionId: String,
    private val goal: String,
    private val maxSteps: Int,
    private val autonomous: Boolean,
    private val taskId: String?,
    private val onSay: (String) -> Unit,
    private val onProgress: (AgentProgress) -> Unit,
    private val onCheckpoint: (AgentSessionStore.Checkpoint) -> Unit,
    private val onApproval: suspend (StepResponse) -> Boolean,
    private val shouldStop: () -> Boolean,
) {
    private val readOnlyBlocked = setOf(
        "post", "comment", "dm", "follow", "unfollow", "like", "like_story", "like_comment", "save", "type",
    )
    private val voiceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var consecutiveFailures = 0

    suspend fun run(): Boolean {
        val appCtx = svc.applicationContext
        val deviceId = FridayPreferences.deviceId(appCtx)
        val memoryStore = DeviceMemoryStore(appCtx)
        runCatching { memoryStore.hydrateFromBrain(brain, deviceId) }
            .onFailure { onSay("Memory hydrate skipped: ${it.message}") }
        svc.executor.attachMemory(memoryStore)
        val reporter = VerifiedStepReporter(brain, memoryStore, deviceId, voiceScope)

        var pendingLast: TickLastResult? = null
        var forceScreenshot = false

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
                svc.executor.execute(StepResponse(action = "press", params = mapOf("key" to JsonPrimitive("back"))))
                delay(900)
                consecutiveFailures = 0
                continue
            }

            val onIg = svc.currentPackage().contains("instagram", ignoreCase = true)
            val observe = captureObserve(onIg || forceScreenshot)
            forceScreenshot = false
            svc.updateDebugOverlay(observe.screen, FridayPreferences.debugOverlay(appCtx))

            onSay("Thinking… step ${step + 1}")
            onProgress(AgentProgress.StepThinking(step, withScreenshot = observe.screen.screenshotB64 != null))

            val tickResp = runCatching {
                brain.tick(
                    TickRequest(
                        sessionId = sessionId,
                        deviceId = deviceId,
                        goal = goal,
                        step = step,
                        observe = observe,
                        lastResult = pendingLast,
                        mode = mode,
                        sessionContext = tracker.toContext(),
                    ),
                )
            }.getOrElse {
                onSay("Brain unreachable: ${it.message}")
                onProgress(AgentProgress.SessionEnded(ok = false, reason = "Brain unreachable"))
                consecutiveFailures++
                return false
            }

            tracker.applyContext(tickResp.sessionContext)
            emitBudget()
            speak(tickResp.say)
            checkpoint(step, tickResp)

            onProgress(
                AgentProgress.StepDecided(
                    step = step,
                    action = tickResp.action,
                    app = observe.screen.app,
                    say = tickResp.say,
                ),
            )
            onSay("→ ${tickResp.action}: ${tickResp.reason.ifBlank { tickResp.say ?: "" }}")

            if (tickResp.done || tickResp.action == "done") {
                onSay("Task complete.")
                onProgress(AgentProgress.SessionEnded(ok = true, reason = "Done"))
                return true
            }
            if (tickResp.action == "fail") {
                onSay("Stopped: ${tickResp.reason}")
                onProgress(AgentProgress.SessionEnded(ok = false, reason = tickResp.reason))
                return false
            }

            if (tickResp.needsScreenshot && observe.screen.screenshotB64.isNullOrBlank()) {
                forceScreenshot = true
                continue
            }

            val stepResp = tickResp.toStepResponse()
            if (mode == "read_only" && stepResp.action in readOnlyBlocked) {
                onSay("Read-only mode — skipping ${stepResp.action}.")
                pendingLast = TickLastResult(
                    action = stepResp.action,
                    executorOk = false,
                    error = "read_only blocked",
                    beforeObserve = observe,
                    afterObserve = observe,
                )
                continue
            }

            if (stepResp.approvalRequired && !autonomous) {
                if (!onApproval(stepResp)) {
                    pendingLast = TickLastResult(
                        action = stepResp.action,
                        executorOk = false,
                        error = "user declined",
                        beforeObserve = observe,
                        afterObserve = observe,
                    )
                    continue
                }
            }

            if (stepResp.action == "wait") {
                val ms = (stepResp.params["ms"] as? JsonPrimitive)?.content?.toLongOrNull() ?: 500L
                if (stepResp.reason.isNotBlank()) onSay(stepResp.reason)
                delay(ms)
                val afterObserve = captureObserve(onIg)
                pendingLast = TickLastResult(
                    action = "wait",
                    executorOk = true,
                    beforeObserve = observe,
                    afterObserve = afterObserve,
                )
                onProgress(AgentProgress.StepExecuted(step, "wait", ok = true))
                continue
            }

            val x = (stepResp.params["x"] as? JsonPrimitive)?.content?.toIntOrNull()
            val y = (stepResp.params["y"] as? JsonPrimitive)?.content?.toIntOrNull()
            if (x != null && y != null) {
                val tapErr = ScreenValidator.validateTap(observe.screen, x, y)
                if (tapErr != null) {
                    onSay("Invalid tap: $tapErr")
                    consecutiveFailures++
                    pendingLast = TickLastResult(
                        action = stepResp.action,
                        executorOk = false,
                        error = tapErr,
                        uiKey = uiKeyOf(stepResp),
                        params = stepResp.params,
                        beforeObserve = observe,
                        afterObserve = observe,
                    )
                    continue
                }
            }

            val exec = svc.executor.execute(stepResp)
            delay(actionSettleMs(stepResp.action))
            val afterObserve = captureObserve(onIg)
            val beforeFp = ScreenValidator.fingerprint(observe.screen)
            val afterFp = ScreenValidator.fingerprint(afterObserve.screen)
            val verification = OutcomeVerifier.verify(
                stepResp.action,
                exec.ok,
                observe.screen,
                afterObserve.screen,
                beforeFp,
                afterFp,
                params = stepResp.params,
                afterActivity = svc.currentActivityClass(),
            )

            reporter.report(
                sessionId = sessionId,
                step = step,
                goal = goal,
                action = stepResp.action,
                params = stepResp.params,
                executorOk = exec.ok,
                verification = verification,
                before = observe.screen,
                after = afterObserve.screen,
                beforeFp = beforeFp,
                afterFp = afterFp,
                error = exec.error,
                screenshotB64 = observe.screen.screenshotB64,
            )

            pendingLast = TickLastResult(
                action = stepResp.action,
                executorOk = exec.ok,
                error = exec.error,
                uiKey = uiKeyOf(stepResp),
                params = stepResp.params,
                beforeObserve = observe,
                afterObserve = afterObserve,
                verified = verification.status,
                changeScore = verification.changeScore,
            )

            if (exec.ok) consecutiveFailures = 0 else consecutiveFailures++
            onProgress(AgentProgress.StepExecuted(step, stepResp.action, ok = exec.ok, error = exec.error))
        }

        onSay("Reached step limit; stopping to stay safe.")
        onProgress(AgentProgress.SessionEnded(ok = false, reason = "Step limit"))
        return false
    }

    private suspend fun captureObserve(wantScreenshot: Boolean): ObserveBundle {
        val activity = svc.currentActivityClass()
        var screen = svc.readScreen().copy(activity = activity)
        val pkg = svc.currentPackage()
        if (screen.app.isBlank() && pkg.contains("instagram", ignoreCase = true)) {
            screen = screen.copy(app = pkg)
        }
        val dm = svc.resources.displayMetrics
        var marks = emptyList<com.miguelbits.fridayugc.model.SomMark>()
        if (wantScreenshot) {
            val cap = ScreenCapture.captureForGrounding(svc, screen, useSom = true)
            if (cap != null) {
                screen = screen.copy(screenshotB64 = cap.screenshotB64)
                marks = cap.somMarks
            }
        }
        return ObserveBundle(
            screen = screen,
            somMarks = marks,
            screenWidth = dm.widthPixels,
            screenHeight = dm.heightPixels,
        )
    }

    private fun uiKeyOf(resp: StepResponse): String =
        (resp.params["ui_key"] as? JsonPrimitive)?.content.orEmpty().trim('"')

    private fun actionSettleMs(action: String): Long = when (action) {
        "open_app" -> 4500L
        "navigate", "open_reels" -> 2800L
        "swipe", "scroll" -> 900L
        "press" -> 700L
        "like_comment", "tap" -> 650L
        else -> 500L
    }

    private fun speak(text: String?) {
        if (!text.isNullOrBlank() && voice.speakEnabled) {
            voiceScope.launch { voice.speakFromBrain(brain, text) }
        }
    }

    private fun emitBudget() {
        onProgress(AgentNotificationManager.budgetLineFrom(tracker))
    }

    private fun checkpoint(step: Int, resp: TickResponse) {
        onCheckpoint(
            AgentSessionStore.Checkpoint(
                sessionId = sessionId,
                taskId = taskId,
                goal = goal,
                step = step,
                history = listOf("${resp.action}:${resp.reason}"),
                sessionContextJson = tracker.toContext().toString(),
            ),
        )
    }

    private fun TickResponse.toStepResponse(): StepResponse = StepResponse(
        action = action,
        params = params,
        say = say,
        reason = reason,
        done = done,
        needsScreenshot = needsScreenshot,
        approvalRequired = approvalRequired,
    )
}
