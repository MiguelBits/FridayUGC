package com.miguelbits.fridayugc.model

/** Structured progress events for the foreground notification. */
sealed class AgentProgress {
    data class Idle(val message: String) : AgentProgress()

    data class TaskQueued(
        val taskKind: String,
        val goal: String,
        val maxSteps: Int,
        val taskId: String? = null,
    ) : AgentProgress()

    data class SessionStarted(
        val goal: String,
        val maxSteps: Int,
        val taskKind: String? = null,
        val taskId: String? = null,
        val sessionId: String? = null,
    ) : AgentProgress()

    data class StepThinking(val step: Int, val withScreenshot: Boolean = false) : AgentProgress()

    data class StepDecided(
        val step: Int,
        val action: String,
        val app: String,
        val say: String? = null,
    ) : AgentProgress()

    data class StepExecuted(
        val step: Int,
        val action: String,
        val ok: Boolean,
        val error: String? = null,
    ) : AgentProgress()

    data class BudgetUpdate(
        val likes: String,
        val commentLikes: String,
        val reels: String,
        val phase: String,
    ) : AgentProgress()

    data class SessionEnded(val ok: Boolean, val reason: String) : AgentProgress()
}
