from datetime import date, datetime, timezone
import pytest
from unittest.mock import AsyncMock, patch

from app.domain.enums import ActionStatus
from app.meetings.models import Meeting
from app.outcomes.models import ActionItem


def test_calendar_feed_url_and_ics_export(authenticated_client, meeting_id):
    # 1. Get user's private feed url
    res = authenticated_client.get("/api/calendar/feed-url")
    assert res.status_code == 200
    data = res.json()
    token = data["token"]
    feed_url = data["feed_url"]
    assert feed_url.endswith(".ics")

    # 2. Add an action with due_date
    with authenticated_client.app.state.database.session() as session:
        meeting = session.get(Meeting, meeting_id)
        action = ActionItem(
            project_id=meeting.project_id,
            meeting_id=meeting.id,
            content="准备季度财务总结",
            due_date=date(2026, 10, 20),
            status=ActionStatus.open,
            owner_user_id=meeting.created_by,
            created_by=meeting.created_by,
        )
        session.add(action)
        session.commit()

    # 3. Access the feed without cookies (external calendar client)
    ics_res = authenticated_client.get(f"/api/calendar/{token}.ics", cookies={})
    assert ics_res.status_code == 200
    assert "text/calendar" in ics_res.headers["content-type"]
    text = ics_res.text
    assert "BEGIN:VCALENDAR" in text
    assert "BEGIN:VEVENT" in text
    assert "[待办] 准备季度财务总结" in text
    assert "VALUE=DATE:20261020" in text
    assert "END:VCALENDAR" in text

    # 4. Invalid token test
    bad_res = authenticated_client.get("/api/calendar/invalid-token-123.ics", cookies={})
    assert bad_res.status_code == 404


import httpx

@pytest.mark.anyio
async def test_meeting_webhook_notification_feishu_and_dingtalk(authenticated_client, meeting_id):
    mock_post = AsyncMock()
    mock_post.return_value = httpx.Response(200, json={"StatusCode": 0, "StatusMessage": "success"})

    # Test Feishu webhook notify
    with patch("httpx.AsyncClient.post", mock_post):
        res = authenticated_client.post(
            f"/api/meetings/{meeting_id}/webhook-notify",
            json={
                "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/mock",
                "webhook_type": "feishu",
            },
        )
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        assert res.json()["webhook_type"] == "feishu"
        assert mock_post.called
        call_args, call_kwargs = mock_post.call_args
        assert call_args[0] == "https://open.feishu.cn/open-apis/bot/v2/hook/mock"
        assert call_kwargs["json"]["msg_type"] == "interactive"

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
