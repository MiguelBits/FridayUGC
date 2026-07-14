package com.miguelbits.fridayugc

import android.content.Context
import com.miguelbits.fridayugc.model.AgentProgress
import com.miguelbits.fridayugc.model.CheckpointRequest
import com.miguelbits.fridayugc.model.TaskCompleteRequest
import com.miguelbits.fridayugc.model.TaskRecord
import kotlinx.coroutines.CancellationException
import java.util.UUID

/**
 * Durable agent runner hosted in the foreground service.
 * Supports autonomous mode (no per-action dialogs), checkpoints, and kill-switch polling.
 */
class AgentRunner(
    private val context: Context,
    private val brain: BrainClient,
    private val voice: VoiceManager,
    private val store: AgentSessionStore = AgentSessionStore(context),
    private val onSay: (String) -> Unit = {},
    private val onProgress: (AgentProgress) -> Unit = {},
    private val shouldStop: () -> Boolean = { false },
) {
    suspend fun runTask(task: TaskRecord) {
        if (!AgentRunLock.tryAcquire()) {
            onProgress(AgentProgress.Idle("Another session is already running"))
            return
        }
        store.setRunning(true)
        onProgress(
            AgentProgress.TaskQueued(
                taskKind = task.kind,
                goal = task.goal,
                maxSteps = task.maxSteps,
                taskId = task.taskId,
            ),
        )
        try {
            val sessionId = task.sessionId ?: UUID.randomUUID().toString()
            val controller = AgentController(
                brain = brain,
                voice = voice,
                mode = task.mode,
                initialBudget = null,
                onSay = onSay,
                onProgress = onProgress,
                onApproval = { true },
                maxSteps = task.maxSteps,
                autonomous = true,
                sessionId = sessionId,
                taskId = task.taskId,
                taskKind = task.kind,
                onCheckpoint = { cp -> store.save(cp) },
                shouldStop = shouldStop,
            )
            val ok = controller.runGoal(task.goal, resumeContext = task.sessionContext)
            brain.completeTask(
                TaskCompleteRequest(
                    taskId = task.taskId,
                    sessionId = sessionId,
                    ok = ok,
                    summary = if (ok) "completed" else "failed",
                    error = if (ok) null else "session ended early",
                    sessionContext = controller.exportContext(),
                    idempotencyKey = "${task.taskId}:complete",
                ),
            )
            store.clear()
        } catch (e: CancellationException) {
            onProgress(AgentProgress.SessionEnded(ok = false, reason = "Stopped"))
            throw e
        } catch (e: Exception) {
            onProgress(AgentProgress.SessionEnded(ok = false, reason = e.message ?: "Error"))
        } finally {
            store.setRunning(false)
            AgentRunLock.release()
        }
    }

    suspend fun pollAndRun(deviceId: String) {
        val claim = brain.claimTask(deviceId)
        if (!brain.isOperatorEnabled()) {
            onProgress(AgentProgress.Idle("Operator paused"))
            return
        }
        val task = claim.task ?: run {
            onProgress(AgentProgress.Idle("No due tasks"))
            return
        }
        onProgress(
            AgentProgress.TaskQueued(
                taskKind = task.kind,
                goal = task.goal,
                maxSteps = task.maxSteps,
                taskId = task.taskId,
            ),
        )
        runTask(task)
    }
}
