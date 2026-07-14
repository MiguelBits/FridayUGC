package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.StepResponse
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonPrimitive

/** Deterministic posting flows — Gemma handles surprises, state machine handles happy path. */
class PostingController(private val executor: ActionExecutor) {

    enum class Phase { OPEN_CREATE, PICK_MEDIA, EDIT_CAPTION, ADD_LOCATION, CONFIRM_SHARE, VERIFY_SUCCESS }

    suspend fun postReel(mediaUri: String, caption: String, location: String = ""): ActionExecutor.Result {
        var phase = Phase.OPEN_CREATE
        repeat(30) {
            when (phase) {
                Phase.OPEN_CREATE -> {
                    val nav = executor.execute(
                        StepResponse(action = "navigate", params = mapOf("tab" to JsonPrimitive("create"))),
                    )
                    if (!nav.ok) return nav
                    delay(1200)
                    phase = Phase.PICK_MEDIA
                }
                Phase.PICK_MEDIA -> {
                    val pick = executor.execute(
                        StepResponse(
                            action = "open_app",
                            params = mapOf("package" to JsonPrimitive(mediaUri)),
                        ),
                    )
                    if (!pick.ok) {
                        val tap = executor.execute(
                            StepResponse(action = "tap", params = mapOf("target_id" to JsonPrimitive(0))),
                        )
                        if (!tap.ok) return ActionExecutor.Result(false, "media pick failed")
                    }
                    delay(1500)
                    phase = Phase.EDIT_CAPTION
                }
                Phase.EDIT_CAPTION -> {
                    if (caption.isNotBlank()) {
                        val type = executor.execute(
                            StepResponse(
                                action = "post",
                                params = mapOf("caption" to JsonPrimitive(caption)),
                            ),
                        )
                        if (!type.ok) return type
                    }
                    phase = if (location.isNotBlank()) Phase.ADD_LOCATION else Phase.CONFIRM_SHARE
                }
                Phase.ADD_LOCATION -> {
                    executor.execute(
                        StepResponse(action = "type", params = mapOf("text" to JsonPrimitive(location))),
                    )
                    delay(800)
                    phase = Phase.CONFIRM_SHARE
                }
                Phase.CONFIRM_SHARE -> {
                    val share = executor.execute(StepResponse(action = "post", params = emptyMap()))
                    if (!share.ok) return share
                    delay(2500)
                    phase = Phase.VERIFY_SUCCESS
                }
                Phase.VERIFY_SUCCESS -> return ActionExecutor.Result(true)
            }
        }
        return ActionExecutor.Result(false, "posting state machine exceeded steps")
    }

    suspend fun postStory(mediaUri: String): ActionExecutor.Result {
        val nav = executor.execute(
            StepResponse(action = "navigate", params = mapOf("tab" to JsonPrimitive("profile"))),
        )
        if (!nav.ok) return nav
        delay(1000)
        return postReel(mediaUri, caption = "", location = "")
    }
}
