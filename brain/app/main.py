from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import Response

from .agent.actions import GroundRequest, GroundResponse, StepRequest, StepResponse
from .agent.grounding import ground_target
from .agent.router import decide
from .config import get_settings
from .gallery.curator import curate, reply_to_comment
from .gallery.schemas import (
    AnalyzeGalleryRequest,
    AnalyzeGalleryResponse,
    CurateRequest,
    CurateResponse,
    GalleryListResponse,
    GallerySyncAsset,
    GalleryDueItem,
    GallerySyncResponse,
    RecordPostRequest,
    RecordPostResponse,
    ReplyRequest,
    ReplyResponse,
    SpeakRequest,
    QueueSyncRequest,
)
from .gallery.store import GalleryStore
from .gallery.queue import GalleryQueueStore
from .gallery.vision import analyze_gallery
from .retrieval.captions import sync_caption_index
from .retrieval.gallery import sync_gallery_index
from .retrieval.vector_store import CaptionVectorStore, GalleryVectorStore
from .inbox.composer import evaluate_inbox
from .inbox.schemas import (
    EvaluateInboxRequest,
    EvaluateInboxResponse,
    InboxPolicyResponse,
    RecordReplyRequest,
    RecordReplyResponse,
)
from .inbox.store import InboxStore
from .llm.health import check_model_ready
from .runs import RunStore
from .runs.schemas import RunMetrics, SessionRun
from .ugc import director
from .ugc.archetypes import load_archetypes
from .ugc.schemas import (
    CaptionRequest,
    CaptionResponse,
    GenPromptRequest,
    GenPromptResponse,
    PlanRequest,
    PlanResponse,
    VoiceRequest,
    VoiceResponse,
)
from .ugc.operator import RoutineRequest, RoutineResponse, build_routine
from .operator import OperatorService
from .operator.schemas import (
    CheckpointRequest,
    CheckpointResponse,
    DayPlanRequest,
    DayPlanResponse,
    KillRequest,
    OperatorStatus,
    ResumeRequest,
    ResumeResponse,
    TaskClaimRequest,
    TaskClaimResponse,
    TaskCompleteRequest,
    TaskCompleteResponse,
    TaskRecord,
)
from .operator.circuit import get_circuit_breaker
from .learning import LearningService
from .learning.schemas import (
    DeviceMemoryResponse,
    DeviceMemorySyncRequest,
    EvalReport,
    LearningMetrics,
    NovelPlanRecord,
    TrajectoryBatchRequest,
    TrajectoryBatchResponse,
)
from .voice.friday import reply as voice_reply
from .voice.tts import get_tts

app = FastAPI(title="Friday UGC Brain", version="0.2.0")


async def require_token(authorization: str | None = Header(default=None)) -> None:
    """Simple bearer-token gate. The Android agent sends Authorization: Bearer <token>."""
    settings = get_settings()
    expected = f"Bearer {settings.api_token}"
    if authorization != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API token.",
        )


@app.get("/health")
async def health() -> dict:
    s = get_settings()
    model = await check_model_ready()
    gallery_index = GalleryVectorStore()
    caption_index = CaptionVectorStore()
    return {
        "status": "ok",
        "provider": s.llm_provider,
        "agent_engine": s.agent_engine,
        "maf_backend": s.maf_backend if s.agent_engine.lower() == "maf" else None,
        "model_ready": model.get("ready", False),
        "model_detail": model.get("detail", ""),
        "tts": s.tts_provider,
        "voice_enabled": s.voice_enabled,
        "gallery": s.gallery_backend,
        "vision": s.vision_enabled,
        "vision_model": s.vision_model,
        "persona": s.persona,
        "rag_enabled": s.rag_enabled,
        "embedding_provider": s.embedding_provider,
        "rag_gallery_indexed": gallery_index.count(),
        "rag_caption_indexed": caption_index.count(),
    }


# --- Run traces (observability) ---


@app.get("/runs/metrics", response_model=RunMetrics, dependencies=[Depends(require_token)])
async def runs_metrics() -> RunMetrics:
    return RunStore().metrics()


@app.get("/runs", response_model=list[SessionRun], dependencies=[Depends(require_token)])
async def runs_list(limit: int = 20) -> list[SessionRun]:
    return RunStore().list_recent(limit=min(limit, 100))


@app.get("/runs/{session_id}", response_model=SessionRun, dependencies=[Depends(require_token)])
async def runs_get(session_id: str) -> SessionRun:
    run = RunStore().load(session_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    return run


# --- Agent loop ---


@app.post("/agent/step", response_model=StepResponse, dependencies=[Depends(require_token)])
async def agent_step(req: StepRequest) -> StepResponse:
    try:
        return await decide(req, persona_key=get_settings().persona)
    except Exception as exc:
        name = type(exc).__name__
        if name in {"ChatClientException", "SettingNotFoundError"} or "agent_framework" in type(exc).__module__:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LLM agent failed: {exc}",
            ) from exc
        raise


@app.post("/agent/ground", response_model=GroundResponse, dependencies=[Depends(require_token)])
async def agent_ground(req: GroundRequest) -> GroundResponse:
    """Gemma 3 vision grounding — find tap target on screenshot (no OpenAI)."""
    try:
        return await ground_target(req)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Grounding failed: {exc}",
        ) from exc


# --- UGC creation ---


@app.post("/ugc/plan", response_model=PlanResponse, dependencies=[Depends(require_token)])
async def ugc_plan(req: PlanRequest) -> PlanResponse:
    return await director.make_plan(req, persona_key=get_settings().persona)


@app.post("/ugc/caption", response_model=CaptionResponse, dependencies=[Depends(require_token)])
async def ugc_caption(req: CaptionRequest) -> CaptionResponse:
    return await director.make_caption(req, persona_key=get_settings().persona)


@app.post("/ugc/prompt", response_model=GenPromptResponse, dependencies=[Depends(require_token)])
async def ugc_prompt(req: GenPromptRequest) -> GenPromptResponse:
    return await director.make_gen_prompt(req, persona_key=get_settings().persona)


@app.post("/ugc/routine", response_model=RoutineResponse, dependencies=[Depends(require_token)])
async def ugc_routine(req: RoutineRequest) -> RoutineResponse:
    """Full UGC operator session plan: reels, stories, likes, DMs, comments, post."""
    return build_routine(req)


@app.post("/ugc/curate", response_model=CurateResponse, dependencies=[Depends(require_token)])
async def ugc_curate(req: CurateRequest) -> CurateResponse:
    """Plan a week of posts from the cloud gallery — captions, groupings, hashtags, bio."""
    return await curate(req, persona_key=get_settings().persona)


@app.post("/ugc/reply", response_model=ReplyResponse, dependencies=[Depends(require_token)])
async def ugc_reply(req: ReplyRequest) -> ReplyResponse:
    """Draft a Lorena-voice reply to one Instagram comment."""
    return await reply_to_comment(req, persona_key=get_settings().persona)


# --- Gallery ---


@app.get("/gallery", response_model=GalleryListResponse, dependencies=[Depends(require_token)])
async def gallery_list() -> GalleryListResponse:
    manifest = GalleryStore().load()
    unposted = sum(1 for a in manifest.assets if not a.posted)
    return GalleryListResponse(
        account=manifest.account,
        total=len(manifest.assets),
        unposted=unposted,
        assets=manifest.assets,
    )


@app.post("/gallery/analyze", response_model=AnalyzeGalleryResponse, dependencies=[Depends(require_token)])
async def gallery_analyze(req: AnalyzeGalleryRequest) -> AnalyzeGalleryResponse:
    """Vision model sees gallery images/frames and writes vibe + pairing hints to manifest."""
    return await analyze_gallery(req, persona_key=get_settings().persona)


@app.post("/gallery/index", dependencies=[Depends(require_token)])
async def gallery_reindex() -> dict:
    """Rebuild the local RAG embedding index from the current gallery manifest."""
    manifest = GalleryStore().load()
    unposted = [a for a in manifest.assets if not a.posted]
    updated, warnings = await sync_gallery_index(unposted)
    return {
        "indexed": updated,
        "total_unposted": len(unposted),
        "warnings": warnings,
    }


@app.post("/gallery/index-captions", dependencies=[Depends(require_token)])
async def gallery_reindex_captions() -> dict:
    """Rebuild the caption RAG index from posted queue items."""
    updated, warnings = await sync_caption_index()
    return {
        "indexed": updated,
        "total_posted_captions": CaptionVectorStore().count(),
        "warnings": warnings,
    }


@app.post("/gallery/scan", dependencies=[Depends(require_token)])
async def gallery_scan() -> dict:
    """Scan local gallery folder, validate files, refresh inventory."""
    items = GalleryQueueStore().scan_local_folder()
    return {"scanned": len(items), "assets": items}


@app.get("/gallery/queue", dependencies=[Depends(require_token)])
async def gallery_queue_list() -> dict:
    return {"items": GalleryQueueStore().list_all()}


@app.get("/gallery/sync", response_model=GallerySyncResponse, dependencies=[Depends(require_token)])
async def gallery_sync_due() -> GallerySyncResponse:
    """Return due queue items and download URLs for the phone."""
    store = GalleryStore()
    queue = GalleryQueueStore()
    items = []
    for row in queue.list_due():
        assets = []
        for aid in row["asset_ids"]:
            manifest = store.load()
            asset = next((a for a in manifest.assets if a.id == aid), None)
            if asset:
                assets.append(
                    GallerySyncAsset(
                        asset_id=aid,
                        url=store.asset_urls(asset),
                        kind=asset.kind,
                        local_path=asset.local_path,
                    )
                )
        items.append(
            GalleryDueItem(
                item_id=row["item_id"],
                asset_ids=row["asset_ids"],
                format=row["format"],
                caption=row["caption"],
                assets=assets,
            )
        )
    return GallerySyncResponse(due_items=items)


@app.post("/gallery/queue", dependencies=[Depends(require_token)])
async def gallery_queue_enqueue(req: QueueSyncRequest) -> dict:
    store = GalleryStore()
    manifest = store.load()
    assets = [a for a in manifest.assets if a.id in req.asset_ids]
    if len(assets) != len(req.asset_ids):
        raise HTTPException(status_code=400, detail="Unknown asset ids")
    item = GalleryQueueStore().enqueue_from_assets(
        assets,
        format=req.format,
        caption=req.caption,
        hashtags=req.hashtags,
        location=req.location,
        scheduled_at=req.scheduled_at,
        timezone=req.timezone,
    )
    return item


@app.post("/gallery/record-post", response_model=RecordPostResponse, dependencies=[Depends(require_token)])
async def gallery_record_post(req: RecordPostRequest) -> RecordPostResponse:
    """Mark assets posted after verified Instagram success — idempotent."""
    result = GalleryQueueStore().mark_posted(
        item_id=req.item_id,
        asset_ids=req.asset_ids,
        idempotency_key=req.idempotency_key,
    )
    if not result.get("deduplicated"):
        await sync_caption_index()
    return RecordPostResponse(ok=result.get("ok", True), deduplicated=bool(result.get("deduplicated")))


# --- Autonomous operator ---


@app.get("/operator/status", response_model=OperatorStatus, dependencies=[Depends(require_token)])
async def operator_status() -> OperatorStatus:
    return OperatorService().status()


@app.post("/operator/kill", response_model=OperatorStatus, dependencies=[Depends(require_token)])
async def operator_kill(req: KillRequest) -> OperatorStatus:
    return OperatorService().kill(req)


@app.post("/operator/resume", response_model=OperatorStatus, dependencies=[Depends(require_token)])
async def operator_resume() -> OperatorStatus:
    return OperatorService().resume()


@app.post("/operator/day-plan", response_model=DayPlanResponse, dependencies=[Depends(require_token)])
async def operator_day_plan(req: DayPlanRequest) -> DayPlanResponse:
    return OperatorService().day_plan(req)


@app.get("/operator/tasks", response_model=list[TaskRecord], dependencies=[Depends(require_token)])
async def operator_tasks(day: str | None = None) -> list[TaskRecord]:
    return OperatorService().list_tasks(day)


@app.post("/operator/tasks/claim", response_model=TaskClaimResponse, dependencies=[Depends(require_token)])
async def operator_claim(req: TaskClaimRequest) -> TaskClaimResponse:
    return OperatorService().claim(req)


@app.post("/operator/tasks/complete", response_model=TaskCompleteResponse, dependencies=[Depends(require_token)])
async def operator_complete(req: TaskCompleteRequest) -> TaskCompleteResponse:
    return OperatorService().complete(req)


@app.post("/operator/checkpoint", response_model=CheckpointResponse, dependencies=[Depends(require_token)])
async def operator_checkpoint(req: CheckpointRequest) -> CheckpointResponse:
    return OperatorService().checkpoint(req)


@app.post("/operator/resume-session", response_model=ResumeResponse, dependencies=[Depends(require_token)])
async def operator_resume_session(req: ResumeRequest) -> ResumeResponse:
    return OperatorService().resume_session(req)


@app.get("/operator/circuit", dependencies=[Depends(require_token)])
async def operator_circuit() -> dict:
    return get_circuit_breaker().status()


# --- Learning (verified trajectories + device memory) ---


@app.post("/learning/trajectory", response_model=TrajectoryBatchResponse, dependencies=[Depends(require_token)])
async def learning_record_trajectory(req: TrajectoryBatchRequest) -> TrajectoryBatchResponse:
    """Phone reports verified step outcomes after execute — feeds memory + eval."""
    return LearningService().record_trajectory(req)


@app.get("/learning/memory/{device_id}", response_model=DeviceMemoryResponse, dependencies=[Depends(require_token)])
async def learning_get_memory(device_id: str) -> DeviceMemoryResponse:
    return LearningService().get_memory(device_id)


@app.post("/learning/memory", response_model=DeviceMemoryResponse, dependencies=[Depends(require_token)])
async def learning_sync_memory(req: DeviceMemorySyncRequest) -> DeviceMemoryResponse:
    return LearningService().sync_memory(req)


@app.get("/learning/metrics", response_model=LearningMetrics, dependencies=[Depends(require_token)])
async def learning_metrics() -> LearningMetrics:
    return LearningService().metrics()


@app.post("/learning/eval", response_model=EvalReport, dependencies=[Depends(require_token)])
async def learning_run_eval(limit: int = 50) -> EvalReport:
    """Replay recent failures and estimate recoverability (run nightly)."""
    return LearningService().run_eval(limit=min(limit, 200))


@app.get("/learning/eval/latest", response_model=EvalReport | None, dependencies=[Depends(require_token)])
async def learning_latest_eval() -> EvalReport | None:
    return LearningService().latest_eval()


@app.get("/learning/novel-plans", response_model=list[NovelPlanRecord], dependencies=[Depends(require_token)])
async def learning_novel_plans(device_id: str | None = None, limit: int = 20) -> list[NovelPlanRecord]:
    return LearningService().list_novel_plans(device_id=device_id, limit=min(limit, 100))


@app.get("/learning/export-grounding", dependencies=[Depends(require_token)])
async def learning_export_grounding(anchor: str | None = None, limit: int = 1000) -> dict:
    """Export verified (screenshot, anchor, point) rows for offline fine-tune (Layer C)."""
    rows = LearningService().export_grounding_dataset(anchor=anchor, limit=min(limit, 5000))
    return {"count": len(rows), "rows": rows}


@app.get("/content/archetypes", dependencies=[Depends(require_token)])
async def content_archetypes() -> dict:
    items = load_archetypes()
    return {"count": len(items), "archetypes": items}


# --- Inbox (DMs + comments — selective, capped replies) ---


@app.get("/inbox/policy", response_model=InboxPolicyResponse, dependencies=[Depends(require_token)])
async def inbox_policy() -> InboxPolicyResponse:
    s = get_settings()
    return InboxPolicyResponse(
        max_replies_per_user_per_day=s.inbox_max_replies_per_user_per_day,
        max_replies_global_per_day=s.inbox_max_replies_global_per_day,
        min_hours_between_same_user=s.inbox_min_hours_between_same_user,
        skip_low_effort=s.inbox_skip_low_effort,
        low_effort_reply_probability=s.inbox_low_effort_reply_probability,
        comment_max_per_user_per_day=s.inbox_comment_max_per_user_per_day,
    )


@app.post("/inbox/evaluate", response_model=EvaluateInboxResponse, dependencies=[Depends(require_token)])
async def inbox_evaluate(req: EvaluateInboxRequest) -> EvaluateInboxResponse:
    """Decide which messages get a reply today (max ~2/user/day, not every ping)."""
    decisions, summary, global_today, global_cap = await evaluate_inbox(
        req.messages,
        draft_if_reply=req.draft_if_reply,
        persona_key=get_settings().persona,
    )
    return EvaluateInboxResponse(
        decisions=decisions,
        policy_summary=summary,
        global_replies_today=global_today,
        global_cap_today=global_cap,
    )


@app.post("/inbox/record", response_model=RecordReplyResponse, dependencies=[Depends(require_token)])
async def inbox_record(req: RecordReplyRequest) -> RecordReplyResponse:
    """Call after the phone actually sent a reply — updates the daily ledger."""
    count = InboxStore().record_reply(
        user=req.author,
        channel=req.channel,
        message_id=req.message_id,
        thread_id=req.thread_id,
        text_sent=req.text_sent,
    )
    return RecordReplyResponse(ok=True, replies_today_for_user=count)


# --- Voice (Friday assistant — NOT Lorena's content voice) ---


@app.post("/voice/reply", response_model=VoiceResponse, dependencies=[Depends(require_token)])
async def voice(req: VoiceRequest) -> VoiceResponse:
    return await voice_reply(req)


@app.post("/voice/speak", dependencies=[Depends(require_token)])
async def voice_speak(req: SpeakRequest) -> Response:
    """High-quality TTS via OmniVoice (WAV). Pass raw text or let Gemma draft via situation."""
    if not get_settings().voice_enabled:
        return Response(status_code=204)
    if req.situation:
        vr = await voice_reply(VoiceRequest(user_text=req.text, situation=req.situation))
        spoken = vr.reply
    else:
        spoken = req.text
    wav = await get_tts().synthesize(spoken)
    return Response(content=wav, media_type="audio/wav")
