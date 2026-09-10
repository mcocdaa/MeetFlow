from app.errors import AppError
from app.plugins.manager import (
    PluginConfigurationError,
    PluginInputError,
    PluginOutputError,
    PluginStreamingError,
)


def map_plugin_error(
    exc: Exception,
    *,
    output_message: str,
    input_message: str | None = "插件输入无效",
    streaming_message: str | None = None,
) -> AppError | None:
    """Translate a plugin exception to an AppError, or None when unexpected.

    Callers handle the None case as a generic plugin failure they log.
    """
    if input_message is not None and isinstance(exc, PluginInputError):
        return AppError(422, "invalid_action_payload", input_message)
    if streaming_message is not None and isinstance(exc, PluginStreamingError):
        return AppError(422, "plugin_stream_unsupported", streaming_message)
    if isinstance(exc, PluginConfigurationError):
        return AppError(409, "plugin_not_configured", "插件配置不完整")
    if isinstance(exc, PluginOutputError):
        return AppError(502, "plugin_invalid_output", output_message)
    if isinstance(exc, TimeoutError):
        return AppError(504, "plugin_timeout", "插件执行超时")
    return None
