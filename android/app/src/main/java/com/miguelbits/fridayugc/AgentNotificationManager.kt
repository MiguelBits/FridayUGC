package com.miguelbits.fridayugc

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import com.miguelbits.fridayugc.model.AgentProgress
import java.util.ArrayDeque

/**
 * Rich foreground notification: task name, step progress, budget counters, recent step log.
 */
class AgentNotificationManager(private val context: Context) {

    data class StepLine(
        val step: Int,
        val action: String,
        val ok: Boolean?,
        val detail: String = "",
    )

    private val recentSteps = ArrayDeque<StepLine>(MAX_STEP_LINES)
    private var taskKind: String? = null
    private var goal: String = ""
    private var taskId: String? = null
    private var sessionId: String? = null
    private var currentStep: Int = 0
    private var maxSteps: Int = 40
    private var currentAction: String = "—"
    private var foregroundApp: String = ""
    private var statusLine: String = "Idle"
    private var budgetLine: String = ""
    private var phase: String = ""
    private var sessionActive: Boolean = false

    fun apply(event: AgentProgress) {
        when (event) {
            is AgentProgress.Idle -> {
                sessionActive = false
                statusLine = event.message
                currentAction = "—"
            }
            is AgentProgress.TaskQueued -> {
                taskKind = event.taskKind
                goal = event.goal
                taskId = event.taskId
                maxSteps = event.maxSteps
                currentStep = 0
                sessionActive = false
                statusLine = "Queued"
                recentSteps.clear()
            }
            is AgentProgress.SessionStarted -> {
                goal = event.goal
                taskKind = event.taskKind
                taskId = event.taskId
                sessionId = event.sessionId
                maxSteps = event.maxSteps
                currentStep = 0
                sessionActive = true
                statusLine = "Running"
                currentAction = "start"
                recentSteps.clear()
            }
            is AgentProgress.StepThinking -> {
                currentStep = event.step + 1
                currentAction = if (event.withScreenshot) "thinking+screenshot" else "thinking"
                statusLine = "Brain deciding…"
            }
            is AgentProgress.StepDecided -> {
                currentStep = event.step + 1
                currentAction = event.action
                foregroundApp = event.app.ifBlank { foregroundApp }
                statusLine = event.say?.take(60) ?: statusLine
            }
            is AgentProgress.StepExecuted -> {
                currentStep = event.step + 1
                currentAction = event.action
                pushStep(
                    StepLine(
                        step = event.step + 1,
                        action = event.action,
                        ok = event.ok,
                        detail = event.error.orEmpty(),
                    ),
                )
                statusLine = if (event.ok) "OK" else (event.error ?: "Failed")
            }
            is AgentProgress.BudgetUpdate -> {
                budgetLine = "♥ ${event.likes} · 💬♥ ${event.commentLikes} · 🎬 ${event.reels}"
                phase = event.phase
            }
            is AgentProgress.SessionEnded -> {
                sessionActive = false
                statusLine = if (event.ok) "Complete" else event.reason
                pushStep(
                    StepLine(
                        step = currentStep,
                        action = if (event.ok) "done" else "fail",
                        ok = event.ok,
                        detail = event.reason,
                    ),
                )
            }
        }
        refreshNotification()
    }

    fun build(): Notification {
        ensureChannel()
        val title = buildTitle()
        val content = buildContentLine()
        val bigText = buildBigText()

        val open = PendingIntent.getActivity(
            context,
            0,
            Intent(context, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val stop = PendingIntent.getService(
            context,
            1,
            Intent(context, FridayForegroundService::class.java)
                .setAction(FridayForegroundService.ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )

        val progressMax = maxSteps.coerceAtLeast(1)
        val progressValue = currentStep.coerceIn(0, progressMax)

        return NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .setContentTitle(title)
            .setContentText(content)
            .setSubText(budgetLine.ifBlank { phase.ifBlank { "@itslorenamor" } })
            .setStyle(NotificationCompat.BigTextStyle().bigText(bigText).setSummaryText(content))
            .setContentIntent(open)
            .setOngoing(sessionActive)
            .setOnlyAlertOnce(true)
            .setShowWhen(true)
            .setWhen(System.currentTimeMillis())
            .setProgress(progressMax, progressValue, false)
            .addAction(0, context.getString(R.string.notif_action_stop), stop)
            .addAction(0, context.getString(R.string.notif_action_open), open)
            .build()
    }

    private fun buildTitle(): String {
        val label = taskKind?.replace('_', ' ')?.trim().orEmpty()
        return when {
            label.isNotBlank() -> context.getString(R.string.notif_title_task, label)
            sessionActive -> context.getString(R.string.notif_title_session)
            else -> context.getString(R.string.notif_title_idle)
        }
    }

    private fun buildContentLine(): String {
        if (!sessionActive) return statusLine
        val app = foregroundApp.substringAfterLast('.').ifBlank { "?" }
        return context.getString(
            R.string.notif_step_line,
            currentStep,
            maxSteps,
            currentAction,
            app,
            statusLine,
        )
    }

    private fun buildBigText(): String {
        val header = buildString {
            if (goal.isNotBlank()) append(goal.take(120))
            if (taskId != null) append("\nTask: ").append(taskId!!.take(8))
            if (sessionId != null) append(" · Session: ").append(sessionId!!.take(8))
            if (budgetLine.isNotBlank()) append("\n").append(budgetLine)
            if (phase.isNotBlank()) append(" · phase=").append(phase)
        }
        val lines = recentSteps.map { line ->
            val mark = when (line.ok) {
                true -> "✓"
                false -> "✗"
                null -> "…"
            }
            val detail = if (line.detail.isNotBlank()) " — ${line.detail}" else ""
            "$mark Step ${line.step}: ${line.action}$detail"
        }
        return if (lines.isEmpty()) header else header + "\n\n" + lines.joinToString("\n")
    }

    private fun pushStep(line: StepLine) {
        if (recentSteps.size >= MAX_STEP_LINES) recentSteps.removeFirst()
        recentSteps.addLast(line)
    }

    private fun refreshNotification() {
        context.getSystemService(NotificationManager::class.java)
            .notify(NOTIF_ID, build())
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = context.getSystemService(NotificationManager::class.java)
        if (nm.getNotificationChannel(CHANNEL_ID) != null) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            context.getString(R.string.fgs_channel),
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = context.getString(R.string.notif_channel_desc)
            setShowBadge(false)
        }
        nm.createNotificationChannel(channel)
    }

    companion object {
        const val NOTIF_ID = 1001
        private const val CHANNEL_ID = "friday_agent"
        private const val MAX_STEP_LINES = 8

        fun budgetLineFrom(tracker: SessionTracker): AgentProgress.BudgetUpdate =
            AgentProgress.BudgetUpdate(
                likes = "${tracker.likesUsed}/${tracker.likesMax}",
                commentLikes = "${tracker.commentLikesUsed}/${tracker.commentLikesMax}",
                reels = "${tracker.reelsScrolled}/${tracker.reelsMax}",
                phase = tracker.phase,
            )
    }
}
