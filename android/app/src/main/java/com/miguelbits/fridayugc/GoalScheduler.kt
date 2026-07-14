package com.miguelbits.fridayugc

import android.content.Context
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.workDataOf
import com.miguelbits.fridayugc.model.DayPlanRequest
import kotlinx.coroutines.runBlocking
import java.util.concurrent.TimeUnit

/** Sync brain day plan and schedule one-time WorkManager jobs for each due task. */
object GoalScheduler {
    private const val WORK_PREFIX = "friday_task_"
    private const val SYNC_WORK = "friday_sync_plan"

    fun scheduleAutonomous(context: Context) {
        FridayPreferences.setScheduled(context, true)
        FridayPreferences.setAutonomous(context, true)
        enqueuePlanSync(context)
        FridayForegroundService.startAutonomous(context)
        WorkManager.getInstance(context).enqueueUniqueWork(
            GallerySyncWorker.WORK_NAME,
            ExistingWorkPolicy.REPLACE,
            OneTimeWorkRequestBuilder<GallerySyncWorker>()
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build(),
        )
    }

    fun cancel(context: Context) {
        WorkManager.getInstance(context).cancelAllWorkByTag(WORK_PREFIX)
        WorkManager.getInstance(context).cancelUniqueWork(SYNC_WORK)
        WorkManager.getInstance(context).cancelUniqueWork(GallerySyncWorker.WORK_NAME)
        FridayForegroundService.stop(context)
        FridayPreferences.setScheduled(context, false)
    }

    fun enqueuePlanSync(context: Context) {
        val request = OneTimeWorkRequestBuilder<PlanSyncWorker>()
            .addTag(SYNC_WORK)
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build(),
            )
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            SYNC_WORK,
            ExistingWorkPolicy.REPLACE,
            request,
        )
    }

    fun scheduleTask(context: Context, taskId: String, goal: String, delayMs: Long, mode: String) {
        val request = OneTimeWorkRequestBuilder<ScheduleGoalWorker>()
            .addTag(WORK_PREFIX)
            .setInitialDelay(delayMs.coerceAtLeast(0), TimeUnit.MILLISECONDS)
            .setInputData(
                workDataOf(
                    ScheduleGoalWorker.KEY_GOAL to goal,
                    ScheduleGoalWorker.KEY_TASK_ID to taskId,
                    ScheduleGoalWorker.KEY_MODE to mode,
                ),
            )
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build(),
            )
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            "$WORK_PREFIX$taskId",
            ExistingWorkPolicy.REPLACE,
            request,
        )
    }

    /** Legacy daily read-only schedule (kept for manual testing). */
    fun scheduleDaily(context: Context, goal: String) {
        val request = OneTimeWorkRequestBuilder<ScheduleGoalWorker>()
            .setInitialDelay(computeInitialDelayMs(), TimeUnit.MILLISECONDS)
            .setInputData(workDataOf(ScheduleGoalWorker.KEY_GOAL to goal))
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            "friday_daily_goal",
            ExistingWorkPolicy.REPLACE,
            request,
        )
        FridayPreferences.setScheduled(context, true)
    }

    private fun computeInitialDelayMs(): Long {
        val now = java.util.Calendar.getInstance()
        val target = java.util.Calendar.getInstance().apply {
            set(java.util.Calendar.HOUR_OF_DAY, 9)
            set(java.util.Calendar.MINUTE, 0)
            set(java.util.Calendar.SECOND, 0)
            set(java.util.Calendar.MILLISECOND, 0)
            if (before(now)) add(java.util.Calendar.DAY_OF_YEAR, 1)
        }
        return target.timeInMillis - now.timeInMillis
    }
}

/** Pulls day plan from brain and schedules each task. */
class PlanSyncWorker(
    context: Context,
    params: androidx.work.WorkerParameters,
) : androidx.work.CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val brain = BrainClient()
        return try {
            val plan = brain.dayPlan(DayPlanRequest(mode = FridayPreferences.modeString(applicationContext)))
            val now = System.currentTimeMillis()
            for (task in plan.tasks) {
                val at = runCatching {
                    java.time.Instant.parse(task.scheduledAt).toEpochMilli()
                }.getOrDefault(now)
                GoalScheduler.scheduleTask(
                    applicationContext,
                    task.taskId,
                    task.goal,
                    (at - now).coerceAtLeast(0),
                    task.mode,
                )
            }
            Result.success()
        } catch (_: Exception) {
            Result.retry()
        }
    }
}
