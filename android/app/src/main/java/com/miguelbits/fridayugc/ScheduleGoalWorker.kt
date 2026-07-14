package com.miguelbits.fridayugc

import android.content.Context
import android.content.Intent
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters

/**
 * Runs a brain-issued task in the foreground service.
 * Autonomous mode: no approval dialogs; kill-switch polled by AgentController.
 */
class ScheduleGoalWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val goal = inputData.getString(KEY_GOAL)?.ifBlank { null }
            ?: FridayPreferences.lastGoal(applicationContext).ifBlank { DEFAULT_GOAL }
        val taskId = inputData.getString(KEY_TASK_ID)
        val mode = inputData.getString(KEY_MODE) ?: FridayPreferences.modeString(applicationContext)

        if (!FridayAccessibilityService.isConnected) {
            return Result.failure()
        }

        applicationContext.startForegroundService(
            Intent(applicationContext, FridayForegroundService::class.java),
        )

        val brain = BrainClient()
        if (!brain.isOperatorEnabled()) {
            return Result.success()
        }

        val voice = VoiceManager(applicationContext)
        return try {
            if (taskId != null) {
                val claim = brain.claimTask(FridayPreferences.deviceId(applicationContext))
                val task = claim.task
                if (task != null) {
                    AgentRunner(applicationContext, brain, voice).runTask(task)
                } else {
                    FridayForegroundService.runGoal(applicationContext, goal)
                }
                Result.success()
            } else {
                val controller = AgentController(
                    brain = brain,
                    voice = voice,
                    mode = mode,
                    onSay = { FridayForegroundService.updateStatus(applicationContext, it) },
                    onProgress = AgentNotificationHub::apply,
                    onApproval = { FridayPreferences.autonomous(applicationContext) },
                    autonomous = FridayPreferences.autonomous(applicationContext),
                    shouldStop = { FridayForegroundService.stopRequested },
                )
                val ok = controller.runGoal(goal)
                if (ok) Result.success() else Result.retry()
            }
        } catch (_: Exception) {
            Result.retry()
        } finally {
            voice.shutdown()
        }
    }

    companion object {
        const val KEY_GOAL = "goal"
        const val KEY_TASK_ID = "task_id"
        const val KEY_MODE = "mode"
        private const val DEFAULT_GOAL =
            "Open Instagram and scroll the feed for 60 seconds, observe only"
    }
}
