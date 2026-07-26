import httpx
import pytest

from app.plugins.worker import classify_execution_error


def provider_error(status_code: int, body: str = "provider detail") -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://api.example.test/chat/completions")
    response = httpx.Response(status_code, request=request, text=body)
    return httpx.HTTPStatusError("provider request failed", request=request, response=response)


@pytest.mark.parametrize(
    ("exc", "code", "message"),
    [
        (
            provider_error(401),
            "provider_auth_failed",
            "认证或权限失败；检查管理员插件设置中的 API Key、服务地址和权限。",
        ),
        (
            provider_error(402, '{"error":{"message":"Insufficient Balance"}}'),
            "provider_insufficient_balance",
            "AI 服务额度不足；请充值或更换有可用额度的 API Key。",
        ),
        (
            provider_error(429),
            "provider_rate_limited",
            "AI 服务限流或配额已用尽；请稍后重试并检查服务额度。",
        ),
        (
            httpx.TimeoutException("timed out"),
            "provider_timeout",
            "AI 服务响应超时；请稍后重试或检查超时设置。",
        ),
        (
            httpx.RequestError("connection refused"),
            "provider_network_error",
            "无法连接 AI 服务；检查服务地址和网络。",
        ),
    ],
)
def test_classify_execution_error_returns_safe_actionable_diagnostics(
    exc, code, message
):
    diagnostic = classify_execution_error(exc)

    assert diagnostic.code == code
    assert diagnostic.message == message
    assert diagnostic.detail


def test_classify_execution_error_redacts_credentials_from_detail():
    diagnostic = classify_execution_error(
        RuntimeError("Authorization: Bearer sk-test-secret-token api_key=another-secret")
    )

    assert diagnostic.code == "plugin_failed"
    assert "sk-test-secret-token" not in diagnostic.detail
    assert "another-secret" not in diagnostic.detail
    assert "[redacted]" in diagnostic.detail
