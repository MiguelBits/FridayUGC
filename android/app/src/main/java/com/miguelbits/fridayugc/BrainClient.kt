package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.CheckpointRequest
import com.miguelbits.fridayugc.model.CheckpointResponse
import com.miguelbits.fridayugc.model.DayPlanRequest
import com.miguelbits.fridayugc.model.DayPlanResponse
import com.miguelbits.fridayugc.model.GallerySyncResponse
import com.miguelbits.fridayugc.model.KillRequest
import com.miguelbits.fridayugc.model.OperatorStatus
import com.miguelbits.fridayugc.model.RecordPostRequest
import com.miguelbits.fridayugc.model.RecordPostResponse
import com.miguelbits.fridayugc.model.TaskClaimRequest
import com.miguelbits.fridayugc.model.TaskClaimResponse
import com.miguelbits.fridayugc.model.TaskCompleteRequest
import com.miguelbits.fridayugc.model.TaskCompleteResponse
import com.miguelbits.fridayugc.model.DeviceMemorySyncRequest
import com.miguelbits.fridayugc.model.DeviceMemoryResponse
import com.miguelbits.fridayugc.model.EvalReport
import com.miguelbits.fridayugc.model.LearningMetrics
import com.miguelbits.fridayugc.model.TrajectoryBatchRequest
import com.miguelbits.fridayugc.model.TrajectoryBatchResponse
import com.miguelbits.fridayugc.model.GroundRequest
import com.miguelbits.fridayugc.model.GroundResponse
import com.miguelbits.fridayugc.model.StepRequest
import com.miguelbits.fridayugc.model.StepResponse
import com.miguelbits.fridayugc.model.TickRequest
import com.miguelbits.fridayugc.model.TickResponse
import com.miguelbits.fridayugc.model.CaptionRequest
import com.miguelbits.fridayugc.model.CaptionResponse
import com.miguelbits.fridayugc.model.CurateRequest
import com.miguelbits.fridayugc.model.CurateResponse
import com.miguelbits.fridayugc.model.EvaluateInboxRequest
import com.miguelbits.fridayugc.model.EvaluateInboxResponse
import com.miguelbits.fridayugc.model.RecordReplyRequest
import com.miguelbits.fridayugc.model.RecordReplyResponse
import com.miguelbits.fridayugc.model.SpeakRequest
import com.miguelbits.fridayugc.model.VoiceRequest
import com.miguelbits.fridayugc.model.VoiceResponse
import com.miguelbits.fridayugc.model.RoutineRequest
import com.miguelbits.fridayugc.model.RoutineResponse
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

/** Talks to the Friday brain (Gemma 4 on AWS GPU) over HTTPS. */
class BrainClient(
    private val baseUrl: String = BuildConfig.BRAIN_URL,
    private val apiToken: String = BuildConfig.API_TOKEN,
) {
    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(180, TimeUnit.SECONDS)
        .build()
    private val jsonMedia = "application/json".toMediaType()

    suspend fun step(req: StepRequest): StepResponse = withContext(Dispatchers.IO) {
        val body = json.encodeToString(StepRequest.serializer(), req).toRequestBody(jsonMedia)
        val request = Request.Builder()
            .url("$baseUrl/agent/step")
            .addHeader("Authorization", "Bearer $apiToken")
            .post(body)
            .build()
        http.newCall(request).execute().use { resp ->
            val text = resp.body?.string().orEmpty()
            check(resp.isSuccessful) { "Brain error ${resp.code}: $text" }
            json.decodeFromString(StepResponse.serializer(), text)
        }
    }

    suspend fun tick(req: TickRequest): TickResponse = withContext(Dispatchers.IO) {
        val body = json.encodeToString(TickRequest.serializer(), req).toRequestBody(jsonMedia)
        val request = Request.Builder()
            .url("$baseUrl/agent/tick")
            .addHeader("Authorization", "Bearer $apiToken")
            .post(body)
            .build()
        http.newCall(request).execute().use { resp ->
            val text = resp.body?.string().orEmpty()
            check(resp.isSuccessful) { "Brain tick error ${resp.code}: $text" }
            json.decodeFromString(TickResponse.serializer(), text)
        }
    }

    suspend fun ground(req: GroundRequest): GroundResponse = withContext(Dispatchers.IO) {
        val body = json.encodeToString(GroundRequest.serializer(), req).toRequestBody(jsonMedia)
        val request = Request.Builder()
            .url("$baseUrl/agent/ground")
            .addHeader("Authorization", "Bearer $apiToken")
            .post(body)
            .build()
        http.newCall(request).execute().use { resp ->
            val text = resp.body?.string().orEmpty()
            check(resp.isSuccessful) { "Ground error ${resp.code}: $text" }
            json.decodeFromString(GroundResponse.serializer(), text)
        }
    }

    suspend fun health(): Boolean = withContext(Dispatchers.IO) {
        runCatching {
            val request = Request.Builder().url("$baseUrl/health").get().build()
            http.newCall(request).execute().use { it.isSuccessful }
        }.getOrDefault(false)
    }

    suspend fun operatorStatus(): OperatorStatus = get("/operator/status", OperatorStatus.serializer())

    suspend fun isOperatorEnabled(): Boolean = runCatching { operatorStatus().enabled }.getOrDefault(true)

    suspend fun killOperator(reason: String = "manual stop"): OperatorStatus =
        post("/operator/kill", KillRequest(reason), OperatorStatus.serializer())

    suspend fun resumeOperator(): OperatorStatus = postEmpty("/operator/resume", OperatorStatus.serializer())

    suspend fun dayPlan(req: DayPlanRequest = DayPlanRequest()): DayPlanResponse =
        post("/operator/day-plan", req, DayPlanResponse.serializer())

    suspend fun claimTask(deviceId: String, after: String? = null): TaskClaimResponse =
        post("/operator/tasks/claim", TaskClaimRequest(deviceId, after), TaskClaimResponse.serializer())

    suspend fun completeTask(req: TaskCompleteRequest): TaskCompleteResponse =
        post("/operator/tasks/complete", req, TaskCompleteResponse.serializer())

    suspend fun checkpoint(req: CheckpointRequest): CheckpointResponse =
        post("/operator/checkpoint", req, CheckpointResponse.serializer())

    suspend fun gallerySync(): GallerySyncResponse =
        get("/gallery/sync", GallerySyncResponse.serializer())

    suspend fun recordPost(req: RecordPostRequest): RecordPostResponse =
        post("/gallery/record-post", req, RecordPostResponse.serializer())

    suspend fun recordTrajectory(req: TrajectoryBatchRequest): TrajectoryBatchResponse =
        post("/learning/trajectory", req, TrajectoryBatchResponse.serializer())

    suspend fun syncDeviceMemory(req: DeviceMemorySyncRequest): DeviceMemoryResponse =
        post("/learning/memory", req, DeviceMemoryResponse.serializer())

    /** Pull previously-learned coords from the brain (cold-start bootstrap). */
    suspend fun getDeviceMemory(deviceId: String): DeviceMemoryResponse =
        get("/learning/memory/$deviceId", DeviceMemoryResponse.serializer())

    suspend fun learningMetrics(): LearningMetrics =
        get("/learning/metrics", LearningMetrics.serializer())

    suspend fun runLearningEval(limit: Int = 50): EvalReport =
        postEmpty("/learning/eval?limit=$limit", EvalReport.serializer())

    suspend fun latestLearningEval(): EvalReport? = withContext(Dispatchers.IO) {
        runCatching {
            get("/learning/eval/latest", EvalReport.serializer())
        }.getOrNull()
    }

    suspend fun voiceReply(req: VoiceRequest): VoiceResponse = post("/voice/reply", req, VoiceResponse.serializer())

    suspend fun caption(req: CaptionRequest): CaptionResponse = post("/ugc/caption", req, CaptionResponse.serializer())

    suspend fun curate(req: CurateRequest): CurateResponse = post("/ugc/curate", req, CurateResponse.serializer())

    suspend fun routine(req: RoutineRequest): RoutineResponse =
        post("/ugc/routine", req, RoutineResponse.serializer())

    suspend fun evaluateInbox(req: EvaluateInboxRequest): EvaluateInboxResponse =
        post("/inbox/evaluate", req, EvaluateInboxResponse.serializer())

    suspend fun recordReply(req: RecordReplyRequest) {
        post("/inbox/record", req, RecordReplyResponse.serializer())
    }

    suspend fun speak(text: String, situation: String? = null): ByteArray = withContext(Dispatchers.IO) {
        val body = json.encodeToString(
            SpeakRequest.serializer(),
            SpeakRequest(text = text, situation = situation),
        ).toRequestBody(jsonMedia)
        val request = Request.Builder()
            .url("$baseUrl/voice/speak")
            .addHeader("Authorization", "Bearer $apiToken")
            .post(body)
            .build()
        http.newCall(request).execute().use { resp ->
            check(resp.isSuccessful) { "TTS error ${resp.code}" }
            resp.body?.bytes() ?: ByteArray(0)
        }
    }

    private suspend fun <TResp> get(path: String, deserializer: kotlinx.serialization.KSerializer<TResp>): TResp =
        withContext(Dispatchers.IO) {
            val request = Request.Builder()
                .url("$baseUrl$path")
                .addHeader("Authorization", "Bearer $apiToken")
                .get()
                .build()
            http.newCall(request).execute().use { resp ->
                val text = resp.body?.string().orEmpty()
                check(resp.isSuccessful) { "Brain error ${resp.code}: $text" }
                json.decodeFromString(deserializer, text)
            }
        }

    private suspend inline fun <reified TReq, reified TResp> post(
        path: String,
        req: TReq,
        deserializer: kotlinx.serialization.KSerializer<TResp>,
    ): TResp where TReq : Any = withContext(Dispatchers.IO) {
        val body = json.encodeToString(
            kotlinx.serialization.serializer<TReq>(),
            req,
        ).toRequestBody(jsonMedia)
        val request = Request.Builder()
            .url("$baseUrl$path")
            .addHeader("Authorization", "Bearer $apiToken")
            .post(body)
            .build()
        http.newCall(request).execute().use { resp ->
            val text = resp.body?.string().orEmpty()
            check(resp.isSuccessful) { "Brain error ${resp.code}: $text" }
            json.decodeFromString(deserializer, text)
        }
    }

    private suspend inline fun <reified TResp> postEmpty(
        path: String,
        deserializer: kotlinx.serialization.KSerializer<TResp>,
    ): TResp = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("$baseUrl$path")
            .addHeader("Authorization", "Bearer $apiToken")
            .post("".toRequestBody(jsonMedia))
            .build()
        http.newCall(request).execute().use { resp ->
            val text = resp.body?.string().orEmpty()
            check(resp.isSuccessful) { "Brain error ${resp.code}: $text" }
            json.decodeFromString(deserializer, text)
        }
    }
}
