from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.agendas.lifecycle import complete_item, start_planned_item
from app.agendas.schemas import AgendaWrite
from app.agendas.service import AgendaService
from app.meetings.models import utcnow
from app.meetings.models import Meeting
from app.auth.models import User
from app.plugins.jobs import PluginJobService
from app.plugins.models import PluginJob, PluginJobStatus
from app.plugins.worker import PluginJobWorker


def test_user_work_brief_replaces_the_current_users_saved_brief_without_creating_a_plugin_job(
    ai_plugin_client, ai_plugin_meeting_id
):
    manager = ai_plugin_client.app.state.plugin_manager
    database = ai_plugin_client.app.state.database
    actor_id = ai_plugin_client.get("/api/auth/me").json()["id"]
    action = next(
        (
            item
            for item in manager.loaded_actions()
            if item.action_id == "ai-work-assistant.user_work_brief"
        ),
        None,
    )

    assert action is not None

    captured: dict = {}

    responses = iter(["第一次跨项目工作摘要", "第二次跨项目工作摘要"])

    async def stream(context, _payload, _config):
        captured.update(context)
        yield next(responses)

    action.stream_handler = stream
    with database.session() as session:
        manager.update_config(
            "ai-work-assistant",
            {
                "base_url": "https://example.test/v1",
                "api_key": "test-key",
                "model": "test-model",
                "timeout_seconds": 10,
            },
            actor_id,
            session,
        )

    first_response = ai_plugin_client.post(
        "/api/plugins/stream",
        json={"action_id": "ai-work-assistant.user_work_brief", "input": {}},
    )

    assert first_response.status_code == 200
    assert "event: delta" in first_response.text
    assert "第一次跨项目工作摘要" in first_response.text
    first_saved = ai_plugin_client.get("/api/work-brief")
    assert first_saved.status_code == 200
    assert first_saved.json()["content_markdown"] == "第一次跨项目工作摘要"
    assert first_saved.json()["generated_at"] is not None

    second_response = ai_plugin_client.post(
        "/api/plugins/stream",
        json={"action_id": "ai-work-assistant.user_work_brief", "input": {}},
    )

    assert second_response.status_code == 200
    assert "第二次跨项目工作摘要" in second_response.text
    second_saved = ai_plugin_client.get("/api/work-brief")
    assert second_saved.status_code == 200
    assert second_saved.json()["content_markdown"] == "第二次跨项目工作摘要"
    assert [project["name"] for project in captured["projects"]] == [
        "Plugin project"
    ]
    assert "attention" in captured
    with database.session() as session:
        assert session.scalar(select(func.count(PluginJob.id))) == 0


def test_meeting_context_exposes_attachment_metadata_but_never_content(
    plugin_client, plugin_meeting_id
):
    from app.plugins.context import PluginContextBuilder

    uploaded = plugin_client.post(
        f"/api/attachments/meeting/{plugin_meeting_id}",
        files={"file": ("architecture.png", b"private attachment bytes", "image/png")},
    )
    assert uploaded.status_code == 201
    actor_id = plugin_client.get("/api/auth/me").json()["id"]

    with plugin_client.app.state.database.session() as session:
        context = PluginContextBuilder(session).meeting(
            plugin_meeting_id, session.get(User, actor_id)
        )

    assert context["attachments"][0]["original_name"] == "architecture.png"
    assert "content" not in context["attachments"][0]
    assert "stored_name" not in context["attachments"][0]


def test_meeting_plugin_context_contains_tag_rules_and_agenda_timing(
    ai_plugin_client, ai_plugin_meeting_id
):
    database = ai_plugin_client.app.state.database
    actor_id = ai_plugin_client.get("/api/auth/me").json()["id"]
    with database.session() as session:
        actor = session.get(User, actor_id)
        meeting = session.get(Meeting, ai_plugin_meeting_id)
        agenda = AgendaService(session).create(
            meeting.id,
            AgendaWrite(
                title="Tagged agenda",
                agenda_type="decision",
                notes_markdown="@决策: 采用方案 A",
            ),
            actor,
            expected_meeting_version=meeting.version,
        )
        finished_at = datetime(2026, 7, 17, 13, 35, tzinfo=timezone.utc)
        start_planned_item(
            agenda,
            actor_id=actor.id,
            at=finished_at - timedelta(minutes=5),
        )
        complete_item(agenda, actor_id=actor.id, at=finished_at)
        session.commit()

        from app.plugins.context import PluginContextBuilder

        context = PluginContextBuilder(session).meeting(meeting.id, actor)

    agenda_context = next(item for item in context["agenda_items"] if item["id"] == agenda.id)
    assert context["agenda_outcome_tags"] == ["@决策:", "@行动:", "@开放问题:"]
    assert agenda_context["actual_duration_seconds"] == 300
    assert agenda_context["decisions"][0]["is_derived"] is True


def test_same_active_action_returns_existing_job(
    plugin_client, plugin_meeting_id
):
    manager = plugin_client.app.state.plugin_manager
    database = plugin_client.app.state.database
    actor = plugin_client.get("/api/auth/me").json()

    with database.session() as session:
        service = PluginJobService(session, manager)
        first, created = service.submit(
            "test-ai.summarize", "meeting", plugin_meeting_id, {}, actor["id"]
        )
        second, duplicate = service.submit(
            "test-ai.summarize", "meeting", plugin_meeting_id, {}, actor["id"]
        )

    assert created is True
    assert duplicate is False
    assert second.id == first.id


def test_worker_marks_interrupted_request_as_non_replayable(
    plugin_client, plugin_meeting_id
):
    manager = plugin_client.app.state.plugin_manager
    database = plugin_client.app.state.database
    actor = plugin_client.get("/api/auth/me").json()
    with database.session() as session:
        job, _ = PluginJobService(session, manager).submit(
            "test-ai.summarize", "meeting", plugin_meeting_id, {}, actor["id"]
        )
        job.status = PluginJobStatus.requesting
        session.commit()
        job_id = job.id

    PluginJobWorker(database, manager).recover()

    with database.session() as session:
        assert session.get(type(job), job_id).status == PluginJobStatus.interrupted


def test_submit_endpoint_returns_active_duplicate_job(
    plugin_client, plugin_meeting_id
):
    first = plugin_client.post(
        "/api/plugin-jobs",
        json={
            "action_id": "test-ai.summarize",
            "target_type": "meeting",
            "target_id": plugin_meeting_id,
            "input": {},
        },
    )
    second = plugin_client.post(
        "/api/plugin-jobs",
        json={
            "action_id": "test-ai.summarize",
            "target_type": "meeting",
            "target_id": plugin_meeting_id,
            "input": {},
        },
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["status"] == "queued"


def test_creator_can_cancel_queued_job_and_rerun_terminal_job(
    plugin_client, plugin_meeting_id
):
    created = plugin_client.post(
        "/api/plugin-jobs",
        json={"action_id": "test-ai.summarize", "target_type": "meeting", "target_id": plugin_meeting_id, "input": {}},
    ).json()

    canceled = plugin_client.post(f"/api/plugin-jobs/{created['id']}/cancel")
    rerun = plugin_client.post(f"/api/plugin-jobs/{created['id']}/rerun")

    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"
    assert rerun.status_code == 201
    assert rerun.json()["id"] != created["id"]


def test_plugin_registered_apply_handler_marks_any_succeeded_action_applied(
    plugin_client, plugin_meeting_id
):
    database = plugin_client.app.state.database
    actor_id = plugin_client.get("/api/auth/me").json()["id"]
    action = plugin_client.app.state.plugin_manager.loaded_actions()[0]

    def apply_handler(job, payload, actor, session):
        assert job.action_id == "test-ai.summarize"
        assert actor.id == actor_id
        assert payload == {"value": "confirmed"}
        return {"value": payload["value"]}

    action.apply_handler = apply_handler
    with database.session() as session:
        job = PluginJob(
            plugin_id="test-ai",
            action_id="test-ai.summarize",
            target_type="meeting",
            target_id=plugin_meeting_id,
            dedupe_key=f"apply:meeting:{plugin_meeting_id}",
            status=PluginJobStatus.succeeded,
            input_json={},
            context_snapshot={},
            result_json={"markdown": "# Draft"},
            created_by=actor_id,
            finished_at=utcnow(),
        )
        session.add(job)
        session.commit()
        job_id = job.id

    response = plugin_client.post(
        f"/api/plugin-jobs/{job_id}/apply", json={"value": "confirmed"}
    )

    assert response.status_code == 200
    assert response.json() == {"value": "confirmed"}
    with database.session() as session:
        applied = session.get(PluginJob, job_id)
        assert applied.applied_by == actor_id
        assert applied.applied_at is not None


def test_meeting_summary_result_cannot_bypass_the_editor_by_using_the_apply_api(
    ai_plugin_client, ai_plugin_meeting_id
):
    database = ai_plugin_client.app.state.database
    actor_id = ai_plugin_client.get("/api/auth/me").json()["id"]
    with database.session() as session:
        job = PluginJob(
            plugin_id="ai-work-assistant",
            action_id="ai-work-assistant.meeting_summary",
            target_type="meeting",
            target_id=ai_plugin_meeting_id,
            dedupe_key=f"summary:meeting:{ai_plugin_meeting_id}",
            status=PluginJobStatus.succeeded,
            input_json={},
            context_snapshot={},
            result_json={"markdown": "# AI 草稿", "model": "test-model"},
            created_by=actor_id,
            finished_at=utcnow(),
        )
        session.add(job)
        session.commit()
        job_id = job.id

    before = ai_plugin_client.get(f"/api/meetings/{ai_plugin_meeting_id}").json()
    assert before["summary_markdown"] == ""
    response = ai_plugin_client.post(
        f"/api/plugin-jobs/{job_id}/apply",
        json={"edited_markdown": "# 已确认纪要", "expected_version": before["version"]},
    )

    assert response.status_code == 409
    assert ai_plugin_client.get(f"/api/meetings/{ai_plugin_meeting_id}").json()[
        "summary_markdown"
    ] == ""


def test_project_progress_result_cannot_create_an_update_through_the_apply_api(
    ai_plugin_client, ai_plugin_meeting_id
):
    database = ai_plugin_client.app.state.database
    actor_id = ai_plugin_client.get("/api/auth/me").json()["id"]
    project_id = ai_plugin_client.get(f"/api/meetings/{ai_plugin_meeting_id}").json()["project"]["id"]
    with database.session() as session:
        job = PluginJob(
            plugin_id="ai-work-assistant",
            action_id="ai-work-assistant.project_progress",
            target_type="project",
            target_id=project_id,
            dedupe_key=f"progress:project:{project_id}",
            status=PluginJobStatus.succeeded,
            input_json={},
            context_snapshot={},
            result_json={"markdown": "# AI 项目进展", "model": "test-model"},
            created_by=actor_id,
            finished_at=utcnow(),
        )
        session.add(job)
        session.commit()
        job_id = job.id

    response = ai_plugin_client.post(
        f"/api/plugin-jobs/{job_id}/apply",
        json={"edited_markdown": "# 已确认项目进展"},
    )

    assert response.status_code == 409
    project = ai_plugin_client.get(f"/api/projects/{project_id}").json()
    assert project["updates"] == []


def test_list_jobs_can_be_scoped_to_one_meeting(plugin_client, plugin_meeting_id):
    created = plugin_client.post(
        "/api/plugin-jobs",
        json={
            "action_id": "test-ai.summarize",
            "target_type": "meeting",
            "target_id": plugin_meeting_id,
            "input": {},
        },
    )

    response = plugin_client.get(
        f"/api/plugin-jobs?target_type=meeting&target_id={plugin_meeting_id}"
    )

    assert created.status_code == 201
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [
        created.json()["id"]
    ]


def test_dismissed_and_applied_jobs_are_history_not_pending_drafts(
    plugin_client, plugin_meeting_id
):
    database = plugin_client.app.state.database
    actor_id = plugin_client.get("/api/auth/me").json()["id"]
    with database.session() as session:
        dismissed = PluginJob(
            plugin_id="ai-work-assistant",
            action_id="ai-work-assistant.meeting_summary",
            target_type="meeting",
            target_id=plugin_meeting_id,
            dedupe_key=f"dismiss:meeting:{plugin_meeting_id}",
            status=PluginJobStatus.succeeded,
            input_json={},
            context_snapshot={},
            result_json={"markdown": "# 草稿"},
            created_by=actor_id,
            finished_at=utcnow(),
        )
        applied = PluginJob(
            plugin_id="ai-work-assistant",
            action_id="ai-work-assistant.meeting_summary",
            target_type="meeting",
            target_id=plugin_meeting_id,
            dedupe_key=f"applied:meeting:{plugin_meeting_id}",
            status=PluginJobStatus.succeeded,
            input_json={},
            context_snapshot={},
            result_json={"markdown": "# 已应用"},
            created_by=actor_id,
            applied_by=actor_id,
            applied_at=utcnow(),
            finished_at=utcnow(),
        )
        session.add_all([dismissed, applied])
        session.commit()
        dismissed_id = dismissed.id
        applied_id = applied.id

    response = plugin_client.post(f"/api/plugin-jobs/{dismissed_id}/dismiss")
    pending = plugin_client.get(
        f"/api/plugin-jobs?target_type=meeting&target_id={plugin_meeting_id}"
    )
    history = plugin_client.get(
        f"/api/plugin-jobs?target_type=meeting&target_id={plugin_meeting_id}&include_history=true"
    )

    assert response.status_code == 200
    assert response.json()["dismissed_by"] == actor_id
    assert response.json()["dismissed_at"]
    assert pending.json()["items"] == []
    assert {item["id"] for item in history.json()["items"]} == {
        dismissed_id,
        applied_id,
    }


@pytest.mark.parametrize(
    "status",
    [
        PluginJobStatus.succeeded,
        PluginJobStatus.failed,
        PluginJobStatus.interrupted,
        PluginJobStatus.canceled,
    ],
)
def test_unapplied_terminal_job_can_be_dismissed(
    plugin_client, plugin_meeting_id, status
):
    database = plugin_client.app.state.database
    actor_id = plugin_client.get("/api/auth/me").json()["id"]
    with database.session() as session:
        job = PluginJob(
            plugin_id="test-ai",
            action_id="test-ai.summarize",
            target_type="meeting",
            target_id=plugin_meeting_id,
            dedupe_key=f"dismiss-{status.value}:{plugin_meeting_id}",
            status=status,
            input_json={},
            context_snapshot={},
            created_by=actor_id,
            finished_at=utcnow(),
        )
        session.add(job)
        session.commit()
        job_id = job.id

    response = plugin_client.post(f"/api/plugin-jobs/{job_id}/dismiss")

    assert response.status_code == 200
    assert response.json()["dismissed_by"] == actor_id


def test_queued_job_cannot_be_dismissed(plugin_client, plugin_meeting_id):
    created = plugin_client.post(
        "/api/plugin-jobs",
        json={
            "action_id": "test-ai.summarize",
            "target_type": "meeting",
            "target_id": plugin_meeting_id,
            "input": {},
        },
    ).json()

    response = plugin_client.post(f"/api/plugin-jobs/{created['id']}/dismiss")

    assert response.status_code == 409
