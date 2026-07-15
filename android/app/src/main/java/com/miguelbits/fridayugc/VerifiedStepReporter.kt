package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.TrajectoryBatchRequest
import com.miguelbits.fridayugc.model.VerifiedStepRecord
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive

/** Reports verified step outcomes to brain for learning (screenshot + vision taps). */
class VerifiedStepReporter(
    private val brain: BrainClient,
    private val memoryStore: DeviceMemoryStore,
    private val deviceId: String,
    private val scope: CoroutineScope,
    private val igVersion: String = "",
) {
    fun report(
        sessionId: String,
        step: Int,
        goal: String,
        action: String,
        params: Map<String, JsonElement>,
        executorOk: Boolean,
        verification: OutcomeVerifier.Result,
        before: Screen,
        after: Screen,
        beforeFp: String,
        afterFp: String,
        error: String? = null,
        screenshotB64: String? = null,
    ) {
        val uiKey = (params["ui_key"] as? JsonPrimitive)?.content.orEmpty().trim('"')
        val isVisionReels = uiKey in VisionMotor.REELS_ANCHORS
        val reportParams = params.toMutableMap()
        if (isVisionReels) {
            val hasXY = (params["x"] as? JsonPrimitive)?.content?.toIntOrNull() != null &&
                (params["y"] as? JsonPrimitive)?.content?.toIntOrNull() != null
            if (!hasXY) {
                val tid = (params["target_id"] as? JsonPrimitive)?.content?.toIntOrNull()
                if (tid != null) {
                    val el = before.elements.firstOrNull { it.id == tid }
                    if (el != null && el.w > 0 && el.h > 0) {
                        reportParams["x"] = JsonPrimitive(el.x + el.w / 2)
                        reportParams["y"] = JsonPrimitive(el.y + el.h / 2)
                    }
                }
            }
        }
        if (!isVisionReels) {
            val resolvedXY: Pair<Int, Int>? = run {
                val tid = (params["target_id"] as? JsonPrimitive)?.content?.toIntOrNull() ?: return@run null
                val el = before.elements.firstOrNull { it.id == tid } ?: return@run null
                if (el.w <= 0 || el.h <= 0) return@run null
                (el.x + el.w / 2) to (el.y + el.h / 2)
            }
            memoryStore.bump(
                action, params, verification.status, igVersion, resolvedXY,
                screenW = before.elements.maxOfOrNull { it.x + it.w } ?: 0,
                screenH = before.elements.maxOfOrNull { it.y + it.h } ?: 0,
            )
        }
        val shot = screenshotB64?.takeIf { it.isNotBlank() } ?: before.screenshotB64?.takeIf { it.isNotBlank() }
        val record = VerifiedStepRecord(
            sessionId = sessionId,
            deviceId = deviceId,
            step = step,
            goal = goal,
            action = action,
            executorOk = executorOk,
            verified = verification.status,
            changeScore = verification.changeScore,
            screenFpBefore = beforeFp,
            screenFpAfter = afterFp,
            foregroundAppBefore = before.app,
            foregroundAppAfter = after.app,
            elementCountBefore = before.elements.size,
            elementCountAfter = after.elements.size,
            error = error,
            igVersion = igVersion,
            params = reportParams.mapValues { (_, v) -> paramValue(v) },
            screenshotB64 = shot,
            anchor = uiKey,
        )
        scope.launch {
            runCatching {
                brain.recordTrajectory(TrajectoryBatchRequest(deviceId = deviceId, steps = listOf(record)))
            }
            if (verification.status == "verified" && !isVisionReels) {
                memoryStore.syncToBrain(brain, deviceId)
            }
        }
    }

    private fun paramValue(v: JsonElement): String =
        (v as? JsonPrimitive)?.content ?: v.toString()
}
