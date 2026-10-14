from datetime import date, datetime, timedelta, timezone
import httpx
import pytest
from sqlalchemy import select
from unittest.mock import AsyncMock, patch

from app.agendas.schemas import AgendaEdit, AgendaWrite
from app.agendas.service import AgendaService
from app.auth.models import User
from app.calendar.router import generate_ics_feed
from app.collaboration.models import ActivityEvent
from app.domain.enums import ActionStatus
from app.meetings.models import Meeting
from app.outcomes.models import ActionItem, Decision


def test_calendar_feed_url_and_ics_export(authenticated_client, meeting_id):
    # 1. Get user's private feed url
    res = authenticated_client.get("/api/calendar/feed-url")
    assert res.status_code == 200
    data = res.json()
    token = data["token"]
    feed_url = data["feed_url"]
    assert feed_url.endswith(".ics")

    # 2. Add an action with due_date and special characters in content
    tz_plus_8 = timezone(timedelta(hours=8))
    with authenticated_client.app.state.database.session() as session:
        meeting = session.get(Meeting, meeting_id)
        user = session.get(User, meeting.created_by)
        meeting.title = "评审, 复盘; 阶段\\总结\n第二行"
        meeting.purpose_markdown = "第一行;\n第二行, 含反斜杠\\结束"
        action = ActionItem(
            project_id=meeting.project_id,
            meeting_id=meeting.id,
            content="准备季度财务总结; 核对, 归档",
            due_date=date(2026, 10, 20),
            status=ActionStatus.open,
            owner_user_id=meeting.created_by,
            created_by=meeting.created_by,
        )
        session.add(action)
        session.commit()

        # Verify timezone-aware non-UTC datetime conversion in generate_ics_feed
        meeting.scheduled_start = datetime(2026, 10, 20, 18, 0, tzinfo=tz_plus_8)
        meeting.scheduled_end = datetime(2026, 10, 20, 19, 0, tzinfo=tz_plus_8)
        direct_ics = generate_ics_feed(user, [action], [meeting])
        assert "DTSTART:20261020T100000Z" in direct_ics
        assert "DTEND:20261020T110000Z" in direct_ics

    # 3. Access the feed without cookies (external calendar client)
    ics_res = authenticated_client.get(f"/api/calendar/{token}.ics", cookies={})
    assert ics_res.status_code == 200
    assert "text/calendar" in ics_res.headers["content-type"]
    text = ics_res.text
    assert "BEGIN:VCALENDAR" in text
    assert "BEGIN:VEVENT" in text
    assert "SUMMARY:[待办] 准备季度财务总结\\; 核对\\, 归档" in text
    assert "DTSTART;VALUE=DATE:20261020" in text
    assert "DTEND;VALUE=DATE:20261021" in text
    assert "SUMMARY:[会议] 评审\\, 复盘\\; 阶段\\\\总结\\n第二行" in text
    assert "DESCRIPTION:会议议题与目的:\\n第一行\\;\\n第二行\\, 含反斜杠\\\\结束" in text
    assert "END:VCALENDAR" in text

    # 4. Invalid token test
    bad_res = authenticated_client.get("/api/calendar/invalid-token-123.ics", cookies={})
    assert bad_res.status_code == 404


@pytest.mark.anyio
async def test_meeting_webhook_notification_feishu_and_dingtalk(authenticated_client, meeting_id):
    with authenticated_client.app.state.database.session() as session:
        meeting = session.get(Meeting, meeting_id)
        admin = session.get(User, meeting.created_by)
        agenda_service = AgendaService(session)
        item = agenda_service.create(
            meeting.id,
            AgendaWrite(title="Webhook 统计议题", agenda_type="decision"),
            admin,
            expected_meeting_version=meeting.version,
        )
        agenda_service.update(
            item.id,
            AgendaEdit(
                expected_version=item.version,
                notes_markdown="@决策: 议题级决议\n@行动: 议题级行动",
            ),
            admin,
        )
        session.add(
            Decision(
                project_id=meeting.project_id,
                meeting_id=meeting.id,
                title="会议级决议",
                decision_markdown="会议级决议内容",
                created_by=admin.id,
            )
        )
        session.commit()

    mock_post = AsyncMock()
    mock_post.return_value = httpx.Response(200, json={"StatusCode": 0, "StatusMessage": "success"})

    with patch("httpx.AsyncClient.post", mock_post):
        # Test Feishu webhook notify using `platform` alias (sent by frontend modal)
        res = authenticated_client.post(
            f"/api/meetings/{meeting_id}/webhook-notify",
            json={
                "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/secret-hook-token-123",
                "platform": "feishu",
            },
        )
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        assert res.json()["webhook_type"] == "feishu"
        assert mock_post.called
        call_args, call_kwargs = mock_post.call_args
        assert call_args[0] == "https://open.feishu.cn/open-apis/bot/v2/hook/secret-hook-token-123"
        card_json = call_kwargs["json"]
        assert card_json["msg_type"] == "interactive"
        card_str = str(card_json)
        # Should include both meeting-level (1) and agenda-level (1) decisions = 2, and agenda-level action = 1
        assert "决议清单 (2)" in card_str
        assert "会议级决议" in card_str
        assert "议题级决议" in card_str
        assert "待办事项 (1)" in card_str
        assert "议题级行动" in card_str

    # Verify ActivityEvent redacts the secret webhook token
    with authenticated_client.app.state.database.session() as session:
        event = session.scalar(
            select(ActivityEvent)
            .where(
                ActivityEvent.meeting_id == meeting_id,
                ActivityEvent.event_type == "meeting.webhook_sent",
            )
            .order_by(ActivityEvent.id.desc())
        )
        assert event is not None
        assert "secret-hook-token-123" not in event.payload_json["webhook_url"]
        assert "***" in event.payload_json["webhook_url"]

    # Test DingTalk webhook notify
    mock_post.reset_mock()
    mock_post.return_value = httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})
    with patch("httpx.AsyncClient.post", mock_post):
        res2 = authenticated_client.post(
            f"/api/meetings/{meeting_id}/webhook-notify",
            json={
                "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=mock",
                "webhook_type": "dingtalk",
                "secret": "SECmock123",
            },
        )
        assert res2.status_code == 200
        assert res2.json()["status"] == "ok"
        assert res2.json()["webhook_type"] == "dingtalk"
        assert mock_post.called
        call_args2, call_kwargs2 = mock_post.call_args
        assert "timestamp=" in call_args2[0]
        assert "sign=" in call_args2[0]
        assert call_kwargs2["json"]["msgtype"] == "markdown"


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "http://127.0.0.1:8000/hook",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/internal",
        "http://192.168.1.1/hook",
        "http://localhost:8080/hook",
        "ftp://open.feishu.cn/hook",
    ],
)
def test_meeting_webhook_ssrf_protection_blocks_private_and_invalid_urls(
    authenticated_client, meeting_id, unsafe_url
):
    res = authenticated_client.post(
        f"/api/meetings/{meeting_id}/webhook-notify",
        json={
            "webhook_url": unsafe_url,
            "platform": "generic",
        },
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "invalid_webhook_url"
