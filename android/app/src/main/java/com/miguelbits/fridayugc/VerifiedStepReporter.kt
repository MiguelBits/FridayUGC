package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.TrajectoryBatchRequest
import com.miguelbits.fridayugc.model.VerifiedStepRecord
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement

/** Reports verified step outcomes to brain and updates local device memory. */
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
    ) {
        memoryStore.bump(action, params, verification.status, igVersion)
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
            params = params.mapValues { (_, v) -> v.toString() },
        )
        scope.launch {
            runCatching {
                brain.recordTrajectory(TrajectoryBatchRequest(deviceId = deviceId, steps = listOf(record)))
            }
            if (verification.status == "verified") {
                memoryStore.syncToBrain(brain, deviceId)
            }
        }
    }
}
