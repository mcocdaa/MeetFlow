from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.agendas.lifecycle import actual_duration_seconds
from app.agendas.models import AgendaItem
from app.agendas.outcome_tags import parse_outcome_tags
from app.agendas.service import AgendaService
from app.auth.dependencies import current_user
from app.auth.models import User
from app.collaboration.activity import ActivityRecorder
from app.database import get_session
from app.domain.enums import AgendaStatus, AgendaType
from app.errors import AppError
from app.http import utc_response
from app.meetings.policies import LifecyclePolicy
from app.meetings.schemas import (
    AmendmentWrite,
    LifecycleCommand,
    MeetingEdit,
    MeetingSeriesEdit,
    MeetingSeriesWrite,
    MeetingWrite,
    OccurrenceWrite,
)
from app.meetings.projectors import serialize_amendment, serialize_snapshot
from app.meetings.service import MeetingService
from app.projects.access import WorkspaceAccess
from app.time_utils import utcnow
from app.webhooks.adapter import (
    dispatch_webhook,
    format_dingtalk_card,
    format_feishu_card,
    format_generic_card,
    redact_webhook_url,
)

router = APIRouter(tags=["meetings"])


def _capability_payload(capabilities) -> dict[str, bool]:
    return {
        "can_manage": capabilities.can_manage,
        "can_contribute": capabilities.can_contribute,
        "can_comment": capabilities.can_comment,
    }


def _meeting_payload(
    service: MeetingService, meeting, user: User
) -> dict[str, Any]:
    access = WorkspaceAccess(service.session)
    capabilities = access.meeting_capabilities(meeting, user)
    result = service.serialize_meeting(meeting)
    result["capabilities"] = _capability_payload(capabilities)
    return result


def _require_meeting_contribution(
    session: Session, meeting_id: str, user: User
):
    return WorkspaceAccess(session).require_meeting_contribute(meeting_id, user)


@router.get("/api/projects/{project_id}/meeting-series")
def list_series(
    project_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    WorkspaceAccess(session).require_project_view(project_id, user)
    return utc_response(MeetingService(session).list_series(project_id))


@router.post("/api/projects/{project_id}/meeting-series", status_code=201)
def create_series(
    project_id: str,
    payload: MeetingSeriesWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    WorkspaceAccess(session).require_project_contribute(project_id, user)
    return utc_response(
        service.serialize_series(service.create_series(project_id, payload, user)),
        status_code=201,
    )


@router.get("/api/meeting-series/{series_id}")
def get_series(
    series_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    series = service.get_series(series_id)
    WorkspaceAccess(session).require_project_view(series.project_id, user)
    return utc_response(service.series_detail(series_id))


@router.put("/api/meeting-series/{series_id}")
def update_series(
    series_id: str,
    payload: MeetingSeriesEdit,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    series = service.get_series(series_id)
    WorkspaceAccess(session).require_project_contribute(series.project_id, user)
    return utc_response(service.serialize_series(service.update_series(series_id, payload, user)))


@router.post("/api/meeting-series/{series_id}/occurrences", status_code=201)
def create_occurrence(
    series_id: str,
    payload: OccurrenceWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    series = service.get_series(series_id)
    WorkspaceAccess(session).require_project_contribute(series.project_id, user)
    return utc_response(
        service.serialize_meeting(service.create_occurrence(series_id, payload, user)),
        status_code=201,
    )


@router.get("/api/projects/{project_id}/meetings")
def list_meetings(
    project_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    WorkspaceAccess(session).require_project_view(project_id, user)
    return utc_response(MeetingService(session).list_meetings(project_id))


@router.post("/api/projects/{project_id}/meetings", status_code=201)
def create_meeting(
    project_id: str,
    payload: MeetingWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    WorkspaceAccess(session).require_project_contribute(project_id, user)
    meeting = service.create_meeting(project_id, payload, user)
    return utc_response(
        _meeting_payload(service, meeting, user),
        status_code=201,
    )


@router.get("/api/meetings/{meeting_id}")
def get_meeting(
    meeting_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    meeting = WorkspaceAccess(session).require_meeting_view(meeting_id, user)
    result = service.meeting_detail(meeting_id, user)
    capabilities = WorkspaceAccess(session).meeting_capabilities(meeting, user)
    result["capabilities"] = _capability_payload(capabilities)
    return utc_response(result)


@router.put("/api/meetings/{meeting_id}")
def update_meeting(
    meeting_id: str,
    payload: MeetingEdit,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    _require_meeting_contribution(session, meeting_id, user)
    meeting = service.update_meeting(meeting_id, payload, user)
    return utc_response(_meeting_payload(service, meeting, user))


def _lifecycle_result(
    operation: str,
    meeting_id: str,
    payload: LifecycleCommand,
    user: User,
    session: Session,
) -> JSONResponse:
    service = MeetingService(session)
    _require_meeting_contribution(session, meeting_id, user)
    meeting = getattr(service, operation)(meeting_id, payload, user)
    return utc_response(_meeting_payload(service, meeting, user))


@router.post("/api/meetings/{meeting_id}/start")
def start_meeting(
    meeting_id: str,
    payload: LifecycleCommand,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _lifecycle_result("start", meeting_id, payload, user, session)


@router.post("/api/meetings/{meeting_id}/finish")
def finish_meeting(
    meeting_id: str,
    payload: LifecycleCommand,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _lifecycle_result("finish", meeting_id, payload, user, session)


@router.post("/api/meetings/{meeting_id}/reopen")
def reopen_meeting(
    meeting_id: str,
    payload: LifecycleCommand,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _lifecycle_result("reopen", meeting_id, payload, user, session)


@router.post("/api/meetings/{meeting_id}/cancel")
def cancel_meeting(
    meeting_id: str,
    payload: LifecycleCommand,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _lifecycle_result("cancel", meeting_id, payload, user, session)


@router.get("/api/meetings/{meeting_id}/snapshots")
def list_snapshots(
    meeting_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    service = MeetingService(session)
    WorkspaceAccess(session).require_meeting_view(meeting_id, user)
    return utc_response([
        serialize_snapshot(row)
        for row in service.list_snapshots(meeting_id, limit=limit, offset=offset)
    ])


@router.post("/api/meetings/{meeting_id}/amendments", status_code=201)
def add_amendment(
    meeting_id: str,
    payload: AmendmentWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = MeetingService(session)
    _require_meeting_contribution(session, meeting_id, user)
    return utc_response(
        serialize_amendment(service.add_amendment(meeting_id, payload, user)),
        status_code=201,
    )


class MeetingWebhookNotifyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    webhook_url: str
    webhook_type: Literal["feishu", "dingtalk", "generic"] = Field(
        default="feishu",
        validation_alias=AliasChoices("webhook_type", "platform"),
    )
    secret: str | None = None


@router.post("/api/meetings/{meeting_id}/webhook-notify")
async def notify_meeting_webhook(
    meeting_id: str,
    payload: MeetingWebhookNotifyRequest,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    meeting = WorkspaceAccess(session).require_meeting_contribute(meeting_id, user)
    service = MeetingService(session)
    detail = service.meeting_detail(meeting_id, user)
    project_name = meeting.project.name if meeting.project else "未指定项目"
    completed_time_str = (
        meeting.completed_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        if meeting.completed_at
        else utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    )
    summary_text = detail.get("summary_markdown") or detail.get("purpose_markdown") or ""
    all_decisions = detail.get("meeting_decisions", []) + [
        d for item in detail.get("agenda_items", []) for d in item.get("decisions", [])
    ]
    all_actions = detail.get("meeting_actions", []) + [
        a for item in detail.get("agenda_items", []) for a in item.get("actions", [])
    ]
    decisions = [d["title"] for d in all_decisions]
    actions = [a["content"] for a in all_actions]

    if payload.webhook_type == "feishu":
        card = format_feishu_card(
            meeting_title=meeting.title,
            project_name=project_name,
            completed_at_str=completed_time_str,
            summary=summary_text,
            decisions=decisions,
            actions=actions,
        )
    elif payload.webhook_type == "dingtalk":
        card = format_dingtalk_card(
            meeting_title=meeting.title,
            project_name=project_name,
            completed_at_str=completed_time_str,
            summary=summary_text,
            decisions=decisions,
            actions=actions,
        )
    else:
        card = format_generic_card(
            meeting_title=meeting.title,
            project_name=project_name,
            completed_at_str=completed_time_str,
            summary=summary_text,
            decisions=decisions,
            actions=actions,
        )

    res = await dispatch_webhook(
        webhook_url=payload.webhook_url,
        webhook_type=payload.webhook_type,
        payload=card,
        secret=payload.secret,
    )
    ActivityRecorder(session).record(
        project_id=meeting.project_id,
        meeting_id=meeting.id,
        actor_user_id=user.id,
        event_type="meeting.webhook_sent",
        subject_type="meeting",
        subject_id=meeting.id,
        payload={
            "webhook_type": payload.webhook_type,
            "webhook_url": redact_webhook_url(payload.webhook_url),
        },
    )
    session.commit()
    return utc_response({"status": "ok", "response": res, "webhook_type": payload.webhook_type})


class MeetingIngestRequest(BaseModel):
    agenda_title: str | None = Field(default=None, max_length=300)
    agenda_item_id: str | int | None = None
    notes_markdown: str = Field(min_length=1, max_length=200_000)
    auto_complete_agenda: bool = False

    @field_validator("notes_markdown")
    @classmethod
    def require_notes(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("notes_markdown must not be blank")
        return value


@router.post("/api/meetings/{meeting_id}/ingest")
@router.post("/api/v1/meetings/{meeting_id}/ingest")
def ingest_meeting_notes(
    meeting_id: str,
    payload: MeetingIngestRequest,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    meeting = WorkspaceAccess(session).require_meeting_contribute(meeting_id, user)
    LifecyclePolicy.require_mutable_status(meeting.status)
    agenda_service = AgendaService(session)
    tags = parse_outcome_tags(payload.notes_markdown)

    target_id = (
        str(payload.agenda_item_id).strip()
        if payload.agenda_item_id is not None
        else ""
    )
    if target_id:
        item = agenda_service.get(target_id)
        if item.meeting_id != meeting.id:
            raise AppError(404, "agenda_item_not_found", "议题不存在")
        if payload.agenda_title and payload.agenda_title.strip():
            item.title = payload.agenda_title.strip()
        item.notes_markdown = payload.notes_markdown
        item.updated_by = user.id
        item.version += 1
        meeting.updated_by = user.id
        meeting.version += 1
        agenda_service._reconcile_derived_outcomes(item, tags, user)
    else:
        raw_title = (payload.agenda_title or "").strip()
        title = raw_title or "AI 纪要导入"
        items = agenda_service.list(meeting.id)
        existing = next(
            (row for row in items if raw_title and row.title.strip() == raw_title),
            None,
        )
        if existing is not None:
            item = existing
            item.notes_markdown = payload.notes_markdown
            item.updated_by = user.id
            item.version += 1
            meeting.updated_by = user.id
            meeting.version += 1
            agenda_service._reconcile_derived_outcomes(item, tags, user)
        else:
            item = AgendaItem(
                meeting_id=meeting.id,
                title=title,
                agenda_type=AgendaType.discussion,
                estimated_minutes=15,
                notes_markdown=payload.notes_markdown,
                status=AgendaStatus.planned,
                position=len(items),
                version=1,
                created_by=user.id,
                updated_by=user.id,
            )
            session.add(item)
            meeting.version += 1
            meeting.updated_by = user.id
            session.flush()
            agenda_service._reconcile_derived_outcomes(item, tags, user)

    if payload.auto_complete_agenda and item.status in {
        AgendaStatus.planned,
        AgendaStatus.in_progress,
    }:
        now = utcnow()
        if item.started_at is None:
            item.started_at = now
        item.status = AgendaStatus.completed
        item.completed_at = now
        item.actual_duration_seconds = actual_duration_seconds(item, now)

    decisions_count = sum(1 for t in tags if t.kind == "decision")
    actions_count = sum(1 for t in tags if t.kind == "action")
    questions_count = sum(1 for t in tags if t.kind == "question")

    ActivityRecorder(session).record(
        project_id=meeting.project_id,
        meeting_id=meeting.id,
        actor_user_id=user.id,
        event_type="meeting.notes_ingested",
        subject_type="agenda_item",
        subject_id=item.id,
        payload={
            "title": item.title,
            "decisions": decisions_count,
            "actions": actions_count,
            "questions": questions_count,
        },
    )
    session.commit()

    service = MeetingService(session)
    detail = service.meeting_detail(meeting_id, user)
    capabilities = WorkspaceAccess(session).meeting_capabilities(meeting, user)
    detail["capabilities"] = _capability_payload(capabilities)
    return utc_response(
        {
            **detail,
            "meeting": detail,
            "ingested_agenda_item_id": item.id,
            "decisions": decisions_count,
            "actions": actions_count,
            "questions": questions_count,
            "extracted": {
                "decisions": decisions_count,
                "actions": actions_count,
                "questions": questions_count,
            },
        }
    )

