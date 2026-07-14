package com.miguelbits.fridayugc

import android.content.Context
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

/** Persist session checkpoints for process-death resume. */
class AgentSessionStore(context: Context) {
    private val prefs = context.getSharedPreferences("friday_agent_session", Context.MODE_PRIVATE)
    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }

    data class Checkpoint(
        val sessionId: String,
        val taskId: String? = null,
        val goal: String,
        val step: Int,
        val history: List<String>,
        val sessionContextJson: String,
        val resumeToken: String? = null,
    )

    fun save(checkpoint: Checkpoint) {
        prefs.edit()
            .putString(KEY_SESSION_ID, checkpoint.sessionId)
            .putString(KEY_TASK_ID, checkpoint.taskId)
            .putString(KEY_GOAL, checkpoint.goal)
            .putInt(KEY_STEP, checkpoint.step)
            .putString(KEY_HISTORY, checkpoint.history.joinToString("|"))
            .putString(KEY_CONTEXT, checkpoint.sessionContextJson)
            .putLong(KEY_SAVED_AT, System.currentTimeMillis())
            .apply()
    }

    fun load(): Checkpoint? {
        val sessionId = prefs.getString(KEY_SESSION_ID, null) ?: return null
        return Checkpoint(
            sessionId = sessionId,
            taskId = prefs.getString(KEY_TASK_ID, null),
            goal = prefs.getString(KEY_GOAL, "") ?: "",
            step = prefs.getInt(KEY_STEP, 0),
            history = prefs.getString(KEY_HISTORY, "")?.split("|")?.filter { it.isNotBlank() } ?: emptyList(),
            sessionContextJson = prefs.getString(KEY_CONTEXT, "{}") ?: "{}",
        )
    }

    fun clear() {
        prefs.edit()
            .remove(KEY_SESSION_ID)
            .remove(KEY_TASK_ID)
            .remove(KEY_GOAL)
            .remove(KEY_STEP)
            .remove(KEY_HISTORY)
            .remove(KEY_CONTEXT)
            .remove(KEY_SAVED_AT)
            .apply()
    }

    fun isRunning(): Boolean = prefs.getBoolean(KEY_RUNNING, false)

    fun setRunning(running: Boolean) {
        prefs.edit().putBoolean(KEY_RUNNING, running).apply()
    }

    companion object {
        private const val KEY_SESSION_ID = "session_id"
        private const val KEY_TASK_ID = "task_id"
        private const val KEY_GOAL = "goal"
        private const val KEY_STEP = "step"
        private const val KEY_HISTORY = "history"
        private const val KEY_CONTEXT = "context"
        private const val KEY_SAVED_AT = "saved_at"
        private const val KEY_RUNNING = "running"
    }
}
