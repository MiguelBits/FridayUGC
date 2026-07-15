package com.miguelbits.fridayugc

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.EditText
import android.widget.Switch
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.miguelbits.fridayugc.model.CaptionRequest
import com.miguelbits.fridayugc.model.CurateRequest
import com.miguelbits.fridayugc.model.VoiceRequest
import com.miguelbits.fridayugc.model.RoutineRequest
import com.miguelbits.fridayugc.model.RoutineResponse
import com.miguelbits.fridayugc.model.SessionBudget
import com.miguelbits.fridayugc.model.IncomingMessage
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.coroutines.resume
import kotlin.coroutines.suspendCoroutine

/**
 * Control panel: read-only mode (default), voice goals, scheduling, caption drafts.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var voice: VoiceManager
    private lateinit var brain: BrainClient
    private lateinit var status: TextView
    private lateinit var goalInput: EditText
    private lateinit var readOnlySwitch: Switch

    private val micPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (granted) listenForGoal() else status.text = "Microphone permission required for voice."
    }

    private val notifPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { /* notifications optional but help during background sessions */ }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        voice = VoiceManager(this)
        brain = BrainClient()

        val root = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(48, 96, 48, 48)
        }
        status = TextView(this).apply { text = "Friday UGC — not connected" }
        goalInput = EditText(this).apply {
            hint = "Goal, e.g. Scroll the feed and observe gym posts"
            setText(FridayPreferences.lastGoal(this@MainActivity))
        }
        readOnlySwitch = Switch(this).apply {
            text = "Read-only mode (safe default)"
            isChecked = FridayPreferences.readOnly(this@MainActivity)
        }
        val debugOverlaySwitch = Switch(this).apply {
            text = "Debug overlay (indexed bounds)"
            isChecked = FridayPreferences.debugOverlay(this@MainActivity)
        }
        val somSwitch = Switch(this).apply {
            text = "Set-of-Marks on screenshots"
            isChecked = FridayPreferences.somEnabled(this@MainActivity)
        }
        val imeBtn = Button(this).apply { text = "Enable Friday IME" }
        val a11yBtn = Button(this).apply { text = "Enable Accessibility" }
        val healthBtn = Button(this).apply { text = "Check brain" }
        val speakBtn = Button(this).apply { text = "Speak goal" }
        val runBtn = Button(this).apply { text = "Run goal" }
        val draftBtn = Button(this).apply { text = "Draft caption" }
        val curateBtn = Button(this).apply { text = "Plan week from gallery" }
        val inboxBtn = Button(this).apply { text = "Evaluate inbox (demo)" }
        val fullUgcBtn = Button(this).apply { text = "Run full UGC session" }
        val reelsCommentLikesBtn = Button(this).apply { text = "Like comments on 10 reels" }
        val scheduleBtn = Button(this).apply {
            text = if (FridayPreferences.isScheduled(this@MainActivity)) "Cancel autonomous schedule"
            else "Start autonomous operator"
        }
        val stopBtn = Button(this).apply { text = "Emergency stop" }

        root.addView(status)
        root.addView(goalInput)
        root.addView(readOnlySwitch)
        root.addView(debugOverlaySwitch)
        root.addView(somSwitch)
        root.addView(imeBtn)
        root.addView(a11yBtn)
        root.addView(healthBtn)
        root.addView(speakBtn)
        root.addView(runBtn)
        root.addView(draftBtn)
        root.addView(curateBtn)
        root.addView(inboxBtn)
        root.addView(fullUgcBtn)
        root.addView(reelsCommentLikesBtn)
        root.addView(scheduleBtn)
        root.addView(stopBtn)
        setContentView(root)
        requestNotificationPermissionIfNeeded()

        readOnlySwitch.setOnCheckedChangeListener { _, checked ->
            FridayPreferences.setReadOnly(this, checked)
            status.text = if (checked) "Read-only: scroll/observe only." else "Full mode: engagement needs approval."
        }
        debugOverlaySwitch.setOnCheckedChangeListener { _, checked ->
            FridayPreferences.setDebugOverlay(this, checked)
            if (!checked) FridayAccessibilityService.instance?.updateDebugOverlay(
                com.miguelbits.fridayugc.model.Screen("", "", emptyList()),
                false,
            )
        }
        somSwitch.setOnCheckedChangeListener { _, checked ->
            FridayPreferences.setSomEnabled(this, checked)
        }
        imeBtn.setOnClickListener {
            ImeHelper.openImeSettings(this)
            status.text = "Enable Friday Agent IME in keyboard settings."
        }

        a11yBtn.setOnClickListener {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }
        healthBtn.setOnClickListener {
            lifecycleScope.launch {
                status.text = if (brain.health()) {
                    "Brain: OK (${BuildConfig.BRAIN_URL})"
                } else {
                    "Brain: unreachable at ${BuildConfig.BRAIN_URL}"
                }
            }
        }
        speakBtn.setOnClickListener { requestMicAndListen() }
        runBtn.setOnClickListener { startGoalFromInput() }
        draftBtn.setOnClickListener { draftCaption() }
        curateBtn.setOnClickListener { planWeekFromGallery() }
        inboxBtn.setOnClickListener { demoInboxPass() }
        fullUgcBtn.setOnClickListener { runFullUgcSession() }
        reelsCommentLikesBtn.setOnClickListener { runReelsCommentLikesSession() }
        scheduleBtn.setOnClickListener {
            if (FridayPreferences.isScheduled(this)) {
                GoalScheduler.cancel(this)
                scheduleBtn.text = "Start autonomous operator"
                status.text = "Autonomous schedule cancelled."
            } else {
                FridayPreferences.setReadOnly(this, false)
                readOnlySwitch.isChecked = false
                GoalScheduler.scheduleAutonomous(this)
                scheduleBtn.text = "Cancel autonomous schedule"
                status.text = "Autonomous operator active — brain day plan synced."
            }
        }
        stopBtn.setOnClickListener {
            lifecycleScope.launch {
                runCatching { brain.killOperator("emergency stop from phone") }
                FridayForegroundService.stop(this@MainActivity)
                status.text = "Emergency stop sent to brain."
            }
        }
    }

    private fun requestMicAndListen() {
        when {
            ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) ==
                PackageManager.PERMISSION_GRANTED -> listenForGoal()
            else -> micPermission.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    private fun listenForGoal() {
        status.text = "Listening…"
        voice.listen(
            onResult = { text ->
                runOnUiThread {
                    goalInput.setText(text)
                    status.text = "Heard: $text"
                }
                lifecycleScope.launch {
                    runCatching {
                        val reply = brain.voiceReply(VoiceRequest(userText = text, situation = "voice command"))
                        runOnUiThread { status.text = reply.reply }
                        voice.speakFromBrain(brain, reply.reply)
                    }.onFailure {
                        runOnUiThread { status.text = "Voice reply failed: ${it.message}" }
                    }
                }
            },
            onError = { err -> runOnUiThread { status.text = err } },
        )
    }

    private fun startGoalFromInput() {
        val goal = goalInput.text.toString().ifBlank {
            "Open Instagram and scroll the feed for 30 seconds"
        }
        FridayPreferences.saveGoal(this, goal)
        FridayForegroundService.runGoal(this, goal)
    }

    private fun draftCaption() {
        val context = goalInput.text.toString().ifBlank { "dressing room black ribbed dress" }
        lifecycleScope.launch {
            status.text = "Drafting caption…"
            runCatching {
                val cap = brain.caption(CaptionRequest(context = context, cta = 1))
                status.text = "Caption:\n${cap.caption}"
                // Lorena caption — text only (not Friday's assistant voice).
            }.onFailure {
                status.text = "Caption failed: ${it.message}"
            }
        }
    }

    private fun demoInboxPass() {
        val samples = listOf(
            IncomingMessage("m1", author = "gym_bro", text = "Where did you get that set?", channel = "dm"),
            IncomingMessage("m2", author = "gym_bro", text = "hey", channel = "dm"),
            IncomingMessage("m3", author = "random_fan", text = "hi", channel = "dm"),
            IncomingMessage("c1", author = "foodie", text = "recipe??", channel = "comment", postId = "p99"),
        )
        val controller = InboxController(
            brain = brain,
            voice = voice,
            onSay = { msg ->
                runOnUiThread { status.text = msg }
                FridayForegroundService.updateStatus(this@MainActivity, msg)
            },
            onApproval = { author, _, draft ->
                confirm("dm to $author", draft)
            },
        )
        lifecycleScope.launch { controller.processInbox(samples) }
    }

    private fun planWeekFromGallery() {
        lifecycleScope.launch {
            status.text = "Curating week from gallery…"
            runCatching {
                val plan = brain.curate(
                    CurateRequest(daysAhead = 7, maxPostsPerDay = 2, includeBioUpdate = true),
                )
                val summary = buildString {
                    append(plan.strategyNotes)
                    append("\n\n")
                    plan.postingQueue.forEach { p ->
                        append("${p.scheduledDate} · ${p.format} · ${p.caption}\n")
                        append("  ${p.hashtags.joinToString(" ")}\n")
                        append("  assets: ${p.assetIds.joinToString()}\n\n")
                    }
                    plan.bioSuggestion?.let { append("Bio: $it\n") }
                }
                status.text = summary.trim()
                voice.speakFromBrain(brain, "I planned ${plan.postingQueue.size} posts from your gallery.")
            }.onFailure {
                status.text = "Curate failed: ${it.message}"
            }
        }
    }

    private fun localReelsCommentLikesRoutine(): RoutineResponse = RoutineResponse(
        goal = (
            "Open Instagram Reels tab. Process exactly 10 reels. " +
                "For EACH reel: (1) tap the comments icon to open the comments sheet, " +
                "(2) like exactly 3 comments using like_comment on comment heart buttons — " +
                "do NOT post new comments, (3) press back to return to the reel, " +
                "(4) swipe up to the next reel. " +
                "Repeat until 10 reels done (30 comment likes total). Then done with summary."
            ),
        sessionContext = SessionBudget(
            reelsMax = 10,
            commentLikesMax = 30,
            commentLikesPerReel = 3,
            commentsMax = 0,
            likesMax = 0,
            phase = "reels_comment_likes",
        ),
    )

    private fun runReelsCommentLikesSession() {
        if (FridayPreferences.readOnly(this)) {
            status.text = "Turn off read-only — this routine likes comments on reels."
            return
        }
        lifecycleScope.launch {
            status.text = "Building reels comment-likes routine…"
            runCatching {
                val routine = runCatching {
                    brain.routine(
                        RoutineRequest(routine = "reels_comment_likes", durationMinutes = 30, mode = "full"),
                    )
                }.getOrElse { err ->
                    status.text = "Brain routine stale (${err.message}) — using local plan."
                    localReelsCommentLikesRoutine()
                }
                FridayPreferences.saveGoal(this@MainActivity, routine.goal)
                runOnUiThread { goalInput.setText(routine.goal) }
                FridayForegroundService.runCommentLikesRoutine(
                    this@MainActivity,
                    routine.goal,
                    routine.sessionContext,
                )
                status.text = "Session running — watch notification (Ollama grounding ~30s per tap)."
                moveTaskToBack(true)
            }.onFailure {
                runOnUiThread { status.text = "Routine failed: ${it.message}" }
            }
        }
    }

    private fun runFullUgcSession() {
        val mode = FridayPreferences.modeString(this)
        if (mode == "read_only") {
            status.text = "Turn off read-only for likes, DMs, and comments."
        }
        startForegroundService(Intent(this, FridayForegroundService::class.java))
        lifecycleScope.launch {
            status.text = "Building full UGC routine…"
            moveTaskToBack(true)
            delay(600)
            runCatching {
                val routine = brain.routine(
                    RoutineRequest(routine = "full_session", durationMinutes = 25, mode = mode),
                )
                FridayPreferences.saveGoal(this@MainActivity, routine.goal)
                runOnUiThread { goalInput.setText(routine.goal) }
                voice.speakFromBrain(brain, "Starting full UGC session. Reels, stories, inbox — all in budget.")
                val controller = AgentController(
                    brain = brain,
                    voice = voice,
                    mode = mode,
                    initialBudget = routine.sessionContext,
                    taskKind = "full_session",
                    onSay = { msg ->
                        runOnUiThread { status.text = msg }
                    },
                    onProgress = AgentNotificationHub::apply,
                    onApproval = { resp -> confirm(resp.action, resp.reason) },
                )
                controller.runGoal(routine.goal)
            }.onFailure {
                runOnUiThread { status.text = "Routine failed: ${it.message}" }
            }
        }
    }

    private fun runGoal(goal: String) {
        val mode = FridayPreferences.modeString(this)
        val controller = AgentController(
            brain = brain,
            voice = voice,
            mode = mode,
            onSay = { msg -> runOnUiThread { status.text = msg } },
            onProgress = AgentNotificationHub::apply,
            onApproval = { resp -> confirm(resp.action, resp.reason) },
        )
        startForegroundService(Intent(this, FridayForegroundService::class.java))
        lifecycleScope.launch {
            // Leave Friday UI so accessibility reads Instagram/launcher, not our own screen.
            moveTaskToBack(true)
            delay(600)
            controller.runGoal(goal)
        }
    }

    private suspend fun confirm(action: String, reason: String): Boolean = suspendCoroutine { cont ->
        runOnUiThread {
            AlertDialog.Builder(this)
                .setTitle("Approve $action?")
                .setMessage(reason)
                .setPositiveButton("Allow") { _, _ -> cont.resume(true) }
                .setNegativeButton("Skip") { _, _ -> cont.resume(false) }
                .setCancelable(false)
                .show()
        }
    }

    override fun onDestroy() {
        voice.shutdown()
        super.onDestroy()
    }
}
