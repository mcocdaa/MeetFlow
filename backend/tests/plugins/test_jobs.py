from app.meetings.models import utcnow
from app.auth.models import User
from app.plugins.jobs import PluginJobService
from app.plugins.models import PluginJob, PluginJobStatus
from app.plugins.worker import PluginJobWorker


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


def test_meeting_summary_is_applied_only_after_explicit_confirmation(
    plugin_client, plugin_meeting_id
):
    database = plugin_client.app.state.database
    actor_id = plugin_client.get("/api/auth/me").json()["id"]
    with database.session() as session:
        job = PluginJob(
            plugin_id="ai-work-assistant",
            action_id="ai-work-assistant.meeting_summary",
            target_type="meeting",
            target_id=plugin_meeting_id,
            dedupe_key=f"summary:meeting:{plugin_meeting_id}",
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

    before = plugin_client.get(f"/api/meetings/{plugin_meeting_id}").json()
    assert before["summary_markdown"] == ""
    response = plugin_client.post(
        f"/api/plugin-jobs/{job_id}/apply",
        json={"edited_markdown": "# 已确认纪要", "expected_version": before["version"]},
    )

    assert response.status_code == 200
    assert response.json()["summary_markdown"] == "# 已确认纪要"
