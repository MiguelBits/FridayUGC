package com.miguelbits.fridayugc.tools

import com.miguelbits.fridayugc.ActionExecutor
import com.miguelbits.fridayugc.model.StepResponse

/** Registry of named motor tools (MobClaw-style dispatch). */
class ToolRegistry(private val executor: ActionExecutor) {

    private val tools: Map<String, AgentTool> = mapOf(
        "tap" to AgentTool { executor.runTap(it) },
        "scroll" to AgentTool { executor.runScroll(it) },
        "swipe" to AgentTool { executor.runSwipe(it) },
        "type" to AgentTool { executor.runType(it) },
        "press" to AgentTool { executor.runPress(it) },
        "open_app" to AgentTool { executor.runOpenApp(it) },
        "navigate" to AgentTool { executor.runNavigate(it) },
        "wait" to AgentTool { executor.runWait(it) },
        "comment" to AgentTool { executor.runComment(it) },
        "dm" to AgentTool { executor.runDm(it) },
        "post" to AgentTool { executor.runPost(it) },
        "like" to AgentTool { executor.runTap(it) },
        "like_story" to AgentTool { executor.runTap(it) },
        "like_comment" to AgentTool { executor.runTap(it) },
        "view_story" to AgentTool { executor.runTap(it) },
        "save" to AgentTool { executor.runTap(it) },
        "follow" to AgentTool { executor.runTap(it) },
        "unfollow" to AgentTool { executor.runTap(it) },
        "done" to AgentTool { ActionExecutor.Result(true) },
        "fail" to AgentTool { ActionExecutor.Result(true) },
    )

    val registeredActions: Set<String> get() = tools.keys

    suspend fun dispatch(response: StepResponse): ActionExecutor.Result {
        val tool = tools[response.action]
            ?: return ActionExecutor.Result(false, "unknown action ${response.action}")
        return tool.run(response)
    }
}
