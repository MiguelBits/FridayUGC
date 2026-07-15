package com.miguelbits.fridayugc

import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.IBinder
import android.os.PowerManager
import com.miguelbits.fridayugc.model.AgentProgress
import com.miguelbits.fridayugc.model.SessionBudget
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/** Durable foreground host for autonomous agent sessions with rich step/task notifications. */
class FridayForegroundService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var agentJob: Job? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private lateinit var brain: BrainClient
    private lateinit var voice: VoiceManager
    private lateinit var runner: AgentRunner
    private lateinit var notifications: AgentNotificationManager

    override fun onCreate() {
        super.onCreate()
        brain = BrainClient()
        voice = VoiceManager(this)
        notifications = AgentNotificationManager(this)
        AgentNotificationHub.attach(this)
        runner = AgentRunner(
            context = this,
            brain = brain,
            voice = voice,
            onProgress = AgentNotificationHub::apply,
            shouldStop = { stopRequested },
        )
        startForeground(AgentNotificationManager.NOTIF_ID, notifications.build())
        acquireWakeLock()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopRequested = true
                agentJob?.cancel()
                AgentNotificationHub.apply(AgentProgress.SessionEnded(ok = false, reason = "Stopped"))
                AgentNotificationHub.apply(AgentProgress.Idle("Stopped"))
                stopSelf()
                return START_NOT_STICKY
            }
            ACTION_RUN_COMMENT_LIKES -> startCommentLikesRoutine()
            ACTION_RUN_TASK -> {
                val goal = intent.getStringExtra(EXTRA_GOAL).orEmpty()
                if (goal.isNotBlank()) startManualGoal(goal)
            }
            ACTION_POLL_TASKS -> startAutonomousPolling()
            ACTION_PROGRESS -> applyProgressIntent(intent)
            else -> {
                val status = intent?.getStringExtra(EXTRA_STATUS)
                if (!status.isNullOrBlank()) AgentNotificationHub.apply(AgentProgress.Idle(status))
            }
        }
        return START_STICKY
    }

    private fun applyProgressIntent(intent: Intent) {
        when (intent.getStringExtra(EXTRA_PROGRESS_TYPE).orEmpty()) {
            "idle" -> AgentNotificationHub.apply(
                AgentProgress.Idle(intent.getStringExtra(EXTRA_STATUS).orEmpty()),
            )
            "task" -> AgentNotificationHub.apply(
                AgentProgress.TaskQueued(
                    taskKind = intent.getStringExtra(EXTRA_TASK_KIND).orEmpty(),
                    goal = intent.getStringExtra(EXTRA_GOAL).orEmpty(),
                    maxSteps = intent.getIntExtra(EXTRA_MAX_STEPS, 40),
                    taskId = intent.getStringExtra(EXTRA_TASK_ID),
                ),
            )
        }
    }

    private fun startCommentLikesRoutine() {
        val pending = consumePendingCommentLikes() ?: return
        if (agentJob?.isActive == true) {
            AgentNotificationHub.apply(AgentProgress.Idle("Session already running"))
            return
        }
        stopRequested = false
        agentJob = scope.launch {
            if (!AgentRunLock.tryAcquire()) {
                AgentNotificationHub.apply(AgentProgress.Idle("Session already running"))
                return@launch
            }
            try {
                AgentNotificationHub.apply(
                    AgentProgress.TaskQueued(
                        taskKind = pending.taskKind,
                        goal = pending.goal,
                        maxSteps = pending.maxSteps,
                    ),
                )
                val controller = AgentController(
                    brain = brain,
                    voice = voice,
                    mode = "full",
                    initialBudget = pending.budget,
                    maxSteps = pending.maxSteps,
                    taskKind = pending.taskKind,
                    onSay = { AgentNotificationHub.apply(AgentProgress.Idle(it)) },
                    onProgress = AgentNotificationHub::apply,
                    onApproval = { resp -> confirmCommentLikes(resp) },
                    shouldStop = { stopRequested },
                )
                controller.runGoal(pending.goal)
            } finally {
                AgentRunLock.release()
            }
        }
    }

    private suspend fun confirmCommentLikes(resp: com.miguelbits.fridayugc.model.StepResponse): Boolean {
        if (FridayPreferences.autonomous(this)) return true
        if (!resp.approvalRequired) return true
        return false
    }

    private fun startManualGoal(goal: String) {
        if (agentJob?.isActive == true) return
        stopRequested = false
        agentJob = scope.launch {
            if (!AgentRunLock.tryAcquire()) {
                AgentNotificationHub.apply(AgentProgress.Idle("Session already running"))
                return@launch
            }
            try {
                val controller = AgentController(
                    brain = brain,
                    voice = voice,
                    mode = FridayPreferences.modeString(this@FridayForegroundService),
                    onProgress = AgentNotificationHub::apply,
                    onApproval = {
                        FridayPreferences.autonomous(this@FridayForegroundService) || !it.approvalRequired
                    },
                    autonomous = FridayPreferences.autonomous(this@FridayForegroundService),
                    shouldStop = { stopRequested },
                )
                controller.runGoal(goal)
            } finally {
                AgentRunLock.release()
            }
        }
    }

    private fun startAutonomousPolling() {
        if (agentJob?.isActive == true) return
        stopRequested = false
        AgentNotificationHub.apply(AgentProgress.Idle("Autonomous — waiting for tasks"))
        agentJob = scope.launch {
            while (isActive && !stopRequested) {
                if (!brain.isOperatorEnabled()) {
                    AgentNotificationHub.apply(AgentProgress.Idle("Operator paused — waiting"))
                    delay(30_000)
                    continue
                }
                runner.pollAndRun(FridayPreferences.deviceId(this@FridayForegroundService))
                AgentNotificationHub.apply(AgentProgress.Idle("Waiting for next task"))
                delay(60_000)
            }
        }
    }

    override fun onDestroy() {
        agentJob?.cancel()
        scope.cancel()
        releaseWakeLock()
        voice.shutdown()
        AgentNotificationHub.detach()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun acquireWakeLock() {
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "FridayUGC:Agent").apply {
            setReferenceCounted(false)
            acquire(60 * 60 * 1000L)
        }
    }

    private fun releaseWakeLock() {
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
    }

    companion object {
        private const val EXTRA_STATUS = "status"
        private const val EXTRA_GOAL = "goal"
        private const val EXTRA_PROGRESS_TYPE = "progress_type"
        private const val EXTRA_TASK_KIND = "task_kind"
        private const val EXTRA_TASK_ID = "task_id"
        private const val EXTRA_MAX_STEPS = "max_steps"
        const val ACTION_STOP = "com.miguelbits.fridayugc.STOP"
        const val ACTION_RUN_COMMENT_LIKES = "com.miguelbits.fridayugc.RUN_COMMENT_LIKES"
        const val ACTION_RUN_TASK = "com.miguelbits.fridayugc.RUN_TASK"
        const val ACTION_POLL_TASKS = "com.miguelbits.fridayugc.POLL_TASKS"
        const val ACTION_PROGRESS = "com.miguelbits.fridayugc.PROGRESS"
        @Volatile
        var stopRequested = false

        private data class PendingCommentLikes(
            val goal: String,
            val budget: SessionBudget,
            val taskKind: String,
            val maxSteps: Int,
        )

        @Volatile
        private var pendingCommentLikes: PendingCommentLikes? = null

        private fun consumePendingCommentLikes(): PendingCommentLikes? {
            val p = pendingCommentLikes
            pendingCommentLikes = null
            return p
        }

        fun runCommentLikesRoutine(context: Context, goal: String, budget: SessionBudget) {
            pendingCommentLikes = PendingCommentLikes(
                goal = goal,
                budget = budget,
                taskKind = "reels_comment_likes",
                maxSteps = 120,
            )
            context.startForegroundService(
                Intent(context, FridayForegroundService::class.java)
                    .setAction(ACTION_RUN_COMMENT_LIKES),
            )
        }

        fun updateStatus(context: Context, status: String) {
            AgentNotificationHub.apply(AgentProgress.Idle(status))
            context.startForegroundService(
                Intent(context, FridayForegroundService::class.java).putExtra(EXTRA_STATUS, status),
            )
        }

        fun updateProgress(context: Context, event: AgentProgress) {
            AgentNotificationHub.apply(event)
            val intent = Intent(context, FridayForegroundService::class.java).setAction(ACTION_PROGRESS)
            when (event) {
                is AgentProgress.Idle -> {
                    intent.putExtra(EXTRA_PROGRESS_TYPE, "idle")
                    intent.putExtra(EXTRA_STATUS, event.message)
                }
                is AgentProgress.TaskQueued -> {
                    intent.putExtra(EXTRA_PROGRESS_TYPE, "task")
                    intent.putExtra(EXTRA_TASK_KIND, event.taskKind)
                    intent.putExtra(EXTRA_GOAL, event.goal)
                    intent.putExtra(EXTRA_TASK_ID, event.taskId)
                    intent.putExtra(EXTRA_MAX_STEPS, event.maxSteps)
                }
                else -> return
            }
            context.startForegroundService(intent)
        }

        fun runGoal(context: Context, goal: String) {
            context.startForegroundService(
                Intent(context, FridayForegroundService::class.java)
                    .setAction(ACTION_RUN_TASK)
                    .putExtra(EXTRA_GOAL, goal),
            )
        }

        fun startAutonomous(context: Context) {
            context.startForegroundService(
                Intent(context, FridayForegroundService::class.java).setAction(ACTION_POLL_TASKS),
            )
        }

        fun stop(context: Context) {
            context.startService(
                Intent(context, FridayForegroundService::class.java).setAction(ACTION_STOP),
            )
        }
    }
}
