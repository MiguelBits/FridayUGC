package com.miguelbits.fridayugc.tools

import com.miguelbits.fridayugc.ActionExecutor
import com.miguelbits.fridayugc.model.StepResponse

/** MobClaw-inspired tool interface — one capability per agent action. */
fun interface AgentTool {
    suspend fun run(response: StepResponse): ActionExecutor.Result
}
