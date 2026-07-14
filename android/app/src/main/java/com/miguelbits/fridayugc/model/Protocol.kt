package com.miguelbits.fridayugc.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

/** Mirrors shared/action_protocol.md. Keep in sync with brain/app/agent/actions.py. */

@Serializable
data class ScreenElement(
    val id: Int,
    val role: String = "",
    val text: String = "",
    val scrollable: Boolean = false,
    val editable: Boolean = false,
    val clickable: Boolean = false,
    val x: Int = 0,
    val y: Int = 0,
    val w: Int = 0,
    val h: Int = 0,
)

@Serializable
data class Screen(
    val app: String = "",
    val activity: String = "",
    val elements: List<ScreenElement> = emptyList(),
    @SerialName("screenshot_b64") val screenshotB64: String? = null,
)

/** Structured perception from phone classifier — brain should trust this over raw labels. */
@Serializable
data class ScreenState(
    @SerialName("app_package") val appPackage: String = "",
    @SerialName("activity_class") val activityClass: String = "",
    @SerialName("screen_type") val screenType: String = "unknown",
    @SerialName("selected_tab") val selectedTab: String = "unknown",
    val confidence: Float = 0f,
    @SerialName("element_count") val elementCount: Int = 0,
    val signals: List<String> = emptyList(),
    @SerialName("needs_vision") val needsVision: Boolean = false,
)

@Serializable
data class LastResult(
    val action: String? = null,
    val ok: Boolean = true,
    val error: String? = null,
    val verified: String? = null,
    @SerialName("change_score") val changeScore: Float = 0f,
)

@Serializable
data class StepRequest(
    @SerialName("session_id") val sessionId: String,
    val goal: String,
    val step: Int = 0,
    val screen: Screen,
    @SerialName("last_result") val lastResult: LastResult? = null,
    val history: List<String> = emptyList(),
    val mode: String = "read_only",
    @SerialName("device_id") val deviceId: String = "",
    @SerialName("screen_fingerprint") val screenFingerprint: String = "",
    @SerialName("screen_state") val screenState: ScreenState? = null,
    @SerialName("ig_version") val igVersion: String = "",
    @SerialName("session_context") val sessionContext: Map<String, JsonElement> = emptyMap(),
)

@Serializable
data class CaptionRequest(
    val context: String,
    val cta: Int = 1,
    @SerialName("max_words") val maxWords: Int = 22,
)

@Serializable
data class CaptionResponse(
    val caption: String,
    val warnings: List<String> = emptyList(),
)

@Serializable
data class VoiceRequest(
    @SerialName("user_text") val userText: String,
    val situation: String? = null,
)

@Serializable
data class VoiceResponse(
    val reply: String,
)

@Serializable
data class SpeakRequest(
    val text: String,
    val situation: String? = null,
)

@Serializable
data class CurateRequest(
    @SerialName("days_ahead") val daysAhead: Int = 7,
    @SerialName("max_posts_per_day") val maxPostsPerDay: Int = 2,
    @SerialName("include_bio_update") val includeBioUpdate: Boolean = false,
    val notes: String? = null,
)

@Serializable
data class ScheduledPost(
    @SerialName("asset_ids") val assetIds: List<String>,
    val format: String,
    val lane: String,
    val type: String,
    val cta: Int,
    val code: String,
    @SerialName("on_screen_text") val onScreenText: String = "",
    val caption: String,
    val hashtags: List<String> = emptyList(),
    @SerialName("scheduled_date") val scheduledDate: String,
    @SerialName("approval_required") val approvalRequired: Boolean = true,
    @SerialName("pairing_reason") val pairingReason: String = "",
)

@Serializable
data class CurateResponse(
    @SerialName("posting_queue") val postingQueue: List<ScheduledPost>,
    @SerialName("bio_suggestion") val bioSuggestion: String? = null,
    @SerialName("strategy_notes") val strategyNotes: String = "",
    val warnings: List<String> = emptyList(),
)

@Serializable
data class SessionBudget(
    @SerialName("likes_used") val likesUsed: Int = 0,
    @SerialName("likes_max") val likesMax: Int = 25,
    @SerialName("story_likes_used") val storyLikesUsed: Int = 0,
    @SerialName("story_likes_max") val storyLikesMax: Int = 12,
    @SerialName("reels_scrolled") val reelsScrolled: Int = 0,
    @SerialName("reels_max") val reelsMax: Int = 35,
    @SerialName("comments_used") val commentsUsed: Int = 0,
    @SerialName("comments_max") val commentsMax: Int = 8,
    @SerialName("comment_likes_used") val commentLikesUsed: Int = 0,
    @SerialName("comment_likes_max") val commentLikesMax: Int = 50,
    @SerialName("comment_likes_per_reel") val commentLikesPerReel: Int = 5,
    @SerialName("dms_used") val dmsUsed: Int = 0,
    @SerialName("dms_max") val dmsMax: Int = 10,
    @SerialName("follows_used") val followsUsed: Int = 0,
    @SerialName("follows_max") val followsMax: Int = 3,
    @SerialName("saves_used") val savesUsed: Int = 0,
    @SerialName("saves_max") val savesMax: Int = 5,
    val phase: String = "reels",
)

@Serializable
data class RoutineRequest(
    val routine: String = "full_session",
    @SerialName("duration_minutes") val durationMinutes: Int = 25,
    val mode: String = "full",
    val notes: String? = null,
)

@Serializable
data class RoutineResponse(
    val goal: String,
    @SerialName("session_context") val sessionContext: SessionBudget,
    val checklist: List<String> = emptyList(),
    @SerialName("playbook_excerpt") val playbookExcerpt: String = "",
)

@Serializable
data class StepResponse(
    val action: String,
    val params: Map<String, JsonElement> = emptyMap(),
    val say: String? = null,
    val reason: String = "",
    val done: Boolean = false,
    @SerialName("needs_screenshot") val needsScreenshot: Boolean = false,
    @SerialName("approval_required") val approvalRequired: Boolean = false,
)

@Serializable
data class IncomingMessage(
    @SerialName("message_id") val messageId: String,
    @SerialName("thread_id") val threadId: String = "",
    val author: String,
    val text: String,
    val channel: String = "dm",
    @SerialName("post_id") val postId: String = "",
)

@Serializable
data class MessageDecision(
    @SerialName("message_id") val messageId: String,
    val author: String,
    val action: String,
    val reason: String,
    val draft: String? = null,
    @SerialName("approval_required") val approvalRequired: Boolean = false,
    @SerialName("replies_today_for_user") val repliesTodayForUser: Int = 0,
    @SerialName("cap_per_user_per_day") val capPerUserPerDay: Int = 2,
    val channel: String = "dm",
)

@Serializable
data class EvaluateInboxRequest(
    val messages: List<IncomingMessage>,
    @SerialName("draft_if_reply") val draftIfReply: Boolean = true,
)

@Serializable
data class EvaluateInboxResponse(
    val decisions: List<MessageDecision>,
    @SerialName("policy_summary") val policySummary: String,
    @SerialName("global_replies_today") val globalRepliesToday: Int = 0,
    @SerialName("global_cap_today") val globalCapToday: Int = 40,
)

@Serializable
data class RecordReplyRequest(
    @SerialName("message_id") val messageId: String,
    val author: String,
    val channel: String = "dm",
    @SerialName("text_sent") val textSent: String,
    @SerialName("thread_id") val threadId: String = "",
)

@Serializable
data class RecordReplyResponse(
    val ok: Boolean,
    @SerialName("replies_today_for_user") val repliesTodayForUser: Int = 0,
)

@Serializable
data class OperatorStatus(
    val enabled: Boolean = true,
    @SerialName("kill_reason") val killReason: String? = null,
    @SerialName("fsm_state") val fsmState: String = "IDLE",
    @SerialName("pending_tasks") val pendingTasks: Int = 0,
    @SerialName("active_session_id") val activeSessionId: String? = null,
)

@Serializable
data class TaskRecord(
    @SerialName("task_id") val taskId: String,
    val kind: String,
    val goal: String,
    @SerialName("scheduled_at") val scheduledAt: String,
    val status: String = "pending",
    val mode: String = "full",
    @SerialName("session_context") val sessionContext: Map<String, JsonElement> = emptyMap(),
    @SerialName("max_steps") val maxSteps: Int = 40,
    @SerialName("session_id") val sessionId: String? = null,
)

@Serializable
data class TaskClaimRequest(
    @SerialName("device_id") val deviceId: String,
    val after: String? = null,
)

@Serializable
data class TaskClaimResponse(
    val task: TaskRecord? = null,
    val operator: OperatorStatus,
)

@Serializable
data class TaskCompleteRequest(
    @SerialName("task_id") val taskId: String,
    @SerialName("session_id") val sessionId: String,
    val ok: Boolean,
    val summary: String = "",
    val error: String? = null,
    @SerialName("session_context") val sessionContext: Map<String, JsonElement> = emptyMap(),
    @SerialName("idempotency_key") val idempotencyKey: String? = null,
)

@Serializable
data class TaskCompleteResponse(
    val ok: Boolean,
    val operator: OperatorStatus,
)

@Serializable
data class CheckpointRequest(
    @SerialName("session_id") val sessionId: String,
    @SerialName("task_id") val taskId: String? = null,
    val goal: String,
    val step: Int,
    val history: List<String> = emptyList(),
    @SerialName("session_context") val sessionContext: Map<String, JsonElement> = emptyMap(),
    @SerialName("last_action") val lastAction: String? = null,
    @SerialName("last_ok") val lastOk: Boolean = true,
)

@Serializable
data class CheckpointResponse(
    val ok: Boolean,
    @SerialName("resume_token") val resumeToken: String,
)

@Serializable
data class DayPlanRequest(
    val timezone: String = "America/New_York",
    val mode: String = "full",
    @SerialName("include_post") val includePost: Boolean = true,
    @SerialName("include_stories") val includeStories: Boolean = true,
    @SerialName("comment_likes_target") val commentLikesTarget: Int = 100,
)

@Serializable
data class DayPlanResponse(
    val date: String,
    val tasks: List<TaskRecord> = emptyList(),
    @SerialName("strategy_notes") val strategyNotes: String = "",
)

@Serializable
data class GallerySyncAsset(
    @SerialName("asset_id") val assetId: String,
    val url: String = "",
    val kind: String = "",
    @SerialName("local_path") val localPath: String = "",
)

@Serializable
data class GalleryDueItem(
    @SerialName("item_id") val itemId: String = "",
    @SerialName("asset_ids") val assetIds: List<String> = emptyList(),
    val format: String = "",
    val caption: String = "",
    val assets: List<GallerySyncAsset> = emptyList(),
)

@Serializable
data class GallerySyncResponse(
    @SerialName("due_items") val dueItems: List<GalleryDueItem> = emptyList(),
)

@Serializable
data class KillRequest(
    val reason: String = "manual stop",
)

@Serializable
data class RecordPostRequest(
    @SerialName("asset_ids") val assetIds: List<String>,
    @SerialName("item_id") val itemId: String? = null,
    @SerialName("idempotency_key") val idempotencyKey: String,
    val format: String = "reel",
)

@Serializable
data class RecordPostResponse(
    val ok: Boolean,
    val deduplicated: Boolean = false,
)

@Serializable
data class VerifiedStepRecord(
    @SerialName("session_id") val sessionId: String,
    @SerialName("device_id") val deviceId: String,
    val step: Int,
    val goal: String,
    val action: String,
    @SerialName("executor_ok") val executorOk: Boolean = true,
    val verified: String = "unknown",
    @SerialName("change_score") val changeScore: Float = 0f,
    @SerialName("screen_fp_before") val screenFpBefore: String = "",
    @SerialName("screen_fp_after") val screenFpAfter: String = "",
    @SerialName("foreground_app_before") val foregroundAppBefore: String = "",
    @SerialName("foreground_app_after") val foregroundAppAfter: String = "",
    @SerialName("element_count_before") val elementCountBefore: Int = 0,
    @SerialName("element_count_after") val elementCountAfter: Int = 0,
    val error: String? = null,
    @SerialName("ig_version") val igVersion: String = "",
    val params: Map<String, String> = emptyMap(),
)

@Serializable
data class TrajectoryBatchRequest(
    @SerialName("device_id") val deviceId: String,
    val steps: List<VerifiedStepRecord>,
)

@Serializable
data class TrajectoryBatchResponse(
    val accepted: Int,
    @SerialName("failures_recorded") val failuresRecorded: Int,
)

@Serializable
data class DeviceMemoryEntry(
    @SerialName("device_id") val deviceId: String,
    @SerialName("ui_key") val uiKey: String,
    val x: Int = 0,
    val y: Int = 0,
    @SerialName("resource_hint") val resourceHint: String = "",
    @SerialName("success_count") val successCount: Int = 0,
    @SerialName("fail_count") val failCount: Int = 0,
    @SerialName("last_verified_at") val lastVerifiedAt: String = "",
    @SerialName("ig_version") val igVersion: String = "",
)

@Serializable
data class DeviceMemorySyncRequest(
    @SerialName("device_id") val deviceId: String,
    val entries: List<DeviceMemoryEntry>,
)

@Serializable
data class DeviceMemoryResponse(
    @SerialName("device_id") val deviceId: String,
    val entries: List<DeviceMemoryEntry> = emptyList(),
)

@Serializable
data class LearningMetrics(
    @SerialName("trajectories_total") val trajectoriesTotal: Int = 0,
    @SerialName("verified_steps") val verifiedSteps: Int = 0,
    @SerialName("failed_steps") val failedSteps: Int = 0,
    @SerialName("verification_rate") val verificationRate: Float = 0f,
    @SerialName("memory_entries") val memoryEntries: Int = 0,
    @SerialName("last_eval_at") val lastEvalAt: String? = null,
    @SerialName("last_eval_pass_rate") val lastEvalPassRate: Float? = null,
)

@Serializable
data class EvalReport(
    @SerialName("ran_at") val ranAt: String,
    @SerialName("cases_reviewed") val casesReviewed: Int,
    @SerialName("would_fix") val wouldFix: Int,
    @SerialName("pass_rate") val passRate: Float,
    val notes: String = "",
)
