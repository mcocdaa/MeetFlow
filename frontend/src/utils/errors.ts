import { locale } from '../i18n'

const CJK_RE = /[\u4e00-\u9fff]/

export const EN_ERROR_MAP: Record<string, string> = {
  // Auth & users
  '用户名或密码错误': 'Incorrect username or password',
  '请先登录': 'Please sign in first',
  '需要管理员权限': 'Administrator privileges required',
  '无权访问': 'Permission denied',
  '账号尚未启用': 'Account is not active yet',
  '账号已被归档，请联系管理员恢复': 'Account is archived; please contact an administrator to restore it',
  '账号正在等待管理员批准': 'Account is awaiting administrator approval',
  '账号申请未获批准': 'Account registration was not approved',
  '当前不开放注册': 'Registration is currently closed',
  '当前密码错误': 'Current password is incorrect',
  '用户不存在': 'User not found',
  '用户不存在或已被禁用': 'User not found or disabled',
  '用户名已存在': 'Username is already taken',
  '不能禁用当前管理员': 'Cannot disable the current administrator',
  '不能恢复管理员账号': 'Cannot restore an administrator account',
  '不能拒绝管理员账号': 'Cannot reject an administrator account',
  '只能恢复已归档成员': 'Only archived members can be restored',
  '只能批准待审批成员': 'Only pending members can be approved',
  '只能拒绝待审批成员': 'Only pending members can be rejected',

  // Generic HTTP & validation
  '请求参数无效': 'Invalid request parameters',
  '接口不存在': 'Resource not found',
  '请求方法不受支持': 'HTTP method not allowed',
  '请求无法处理': 'Unable to process request',
  '请求来源不受信任': 'Untrusted request origin',
  '请求失败，请稍后重试': 'Request failed, please try again later',
  '记录已被其他操作更新，请刷新后重试': 'Record was updated by another operation; please refresh and try again',
  '内容已更新': 'Content was updated on the server',

  // Projects
  '项目不存在': 'Project not found',
  '项目进展不存在': 'Project update not found',
  '项目标识已存在': 'Project slug is already taken',
  '项目成员不存在': 'Project member not found',
  '无权查看此项目': 'You do not have permission to view this project',
  '无权修改此项目内容': 'You do not have permission to modify this project',
  '无权管理此项目': 'You do not have permission to manage this project',
  '只能修改自己发布的项目进展': 'You can only edit project updates you posted',
  '只有管理员或项目负责人可以删除项目': 'Only an administrator or project lead can delete the project',
  '项目下已有会议，不能删除': 'Cannot delete a project that already has meetings',
  '项目已有附件，不能删除': 'Cannot delete a project that already has attachments',
  '项目已被其他操作更新，请刷新后重试': 'Project was updated by another operation; please refresh and try again',
  '项目进展已被其他操作更新，请刷新后重试': 'Project update was modified by another operation; please refresh and try again',

  // Meetings & agendas
  '会议不存在': 'Meeting not found',
  '会议系列不存在': 'Meeting series not found',
  '会议参与人不存在': 'Meeting participant not found',
  '记录创建者不存在': 'Creator not found',
  '未指定项目': 'Project is not specified',
  '无权查看此会议': 'You do not have permission to view this meeting',
  '无权评论此会议': 'You do not have permission to comment on this meeting',
  '会议已锁定': 'Meeting is locked',
  '已结束的会议不可直接修改': 'Meeting is locked',
  '已完成的会议不可修改': 'Completed meeting cannot be modified',
  '当前会议状态不可修改议程': 'Agenda cannot be modified in the current meeting status',
  '目标会议不可修改': 'Target meeting cannot be modified',
  '会议状态不可执行此操作': 'Operation is not allowed in the current meeting status',
  '会议尚未开始': 'Meeting has not started yet',
  '会议结束时间必须晚于开始时间': 'Meeting end time must be later than start time',
  '只有已完成会议可添加更正': 'Amendments can only be added to completed meetings',
  '会议已更新，请刷新后重试': 'Meeting was updated; please refresh and try again',
  '会议系列已更新，请刷新后重试': 'Meeting series was updated; please refresh and try again',
  '会议议程已更新，请刷新后重试': 'Meeting agenda was updated; please refresh and try again',
  '议题或会议已更新，请刷新后重试': 'Agenda item or meeting was updated; please refresh and try again',
  '议题或会议已更新': 'Agenda item or meeting was updated',
  '议题不存在': 'Agenda item not found',
  '议题关联用户不存在': 'Agenda user not found',
  '只有待处理议题可以开始': 'Only planned agenda items can be started',
  '已结束的议题不能移动': 'Completed agenda items cannot be moved',
  '议题状态不可再次结束': 'Agenda item is already finished',
  '排序必须包含当前会议的全部且唯一议题': 'Order must include all unique agenda items of the meeting',
  '议题只能移动到同一项目的会议': 'Agenda items can only be moved to meetings in the same project',
  '目标会议必须与原会议不同': 'Target meeting must be different from the source meeting',
  '目标会议已有该议题副本': 'Target meeting already has a copy of this agenda item',
  '议题已有产出，不能直接删除': 'Cannot delete an agenda item that already has outcomes',
  '议题已有评论，不能直接删除': 'Cannot delete an agenda item that already has comments',
  '议题已有附件，不能直接删除': 'Cannot delete an agenda item that already has attachments',
  '议题成果标签必须每行填写一项非空内容': 'Each outcome tag must be on its own line with non-empty content',

  // Outcomes (decisions, actions, open questions)
  '决策不存在': 'Decision not found',
  '行动项不存在': 'Action item not found',
  '开放问题不存在': 'Open question not found',
  '议题备注生成的成果不可直接编辑': 'Outcomes derived from agenda notes cannot be edited directly',
  '仅提议中的决策可编辑': 'Only proposed decisions can be edited',
  '仅提议中的决策可定稿': 'Only proposed decisions can be finalized',
  '仅提议中的决策可撤回': 'Only proposed decisions can be withdrawn',
  '决策已不再接受评审': 'Decision is no longer open for review',
  '只有指定评审人可提交评审': 'Only assigned reviewers can submit a review',
  '仅同项目的最终决策可建立替代关系': 'Supersession is only allowed for finalized decisions in the same project',
  '新决策已建立替代关系': 'New decision already supersedes another decision',
  '只能关联同项目的最终决策': 'Can only link to a finalized decision in the same project',
  '开放问题已排入会议': 'Open question is already scheduled into a meeting',
  '开放问题当前不可排期': 'Open question cannot be scheduled in its current state',
  '开放问题只能排入之后的会议': 'Open questions can only be scheduled into future meetings',
  '开放问题已关闭': 'Open question is already closed',
  '议题已转为开放问题': 'Agenda item has already been converted to an open question',
  '只有跳过的议题可转为开放问题': 'Only skipped agenda items can be converted to open questions',
  '议题已复制到目标会议': 'Agenda item has already been copied to the target meeting',
  '只有跳过的议题可复制': 'Only skipped agenda items can be copied',
  '议题只能复制到之后的会议': 'Agenda items can only be copied to future meetings',
  '源议题没有可迁移产物': 'Source agenda item has no outcomes to migrate',
  '源议题不存在': 'Source agenda item not found',
  '源议题或目标议题不存在': 'Source or target agenda item not found',
  '源议题或目标会议不存在': 'Source agenda item or target meeting not found',
  '源议题与目标议题不能相同': 'Source and target agenda items must be different',
  '议题不属于同一项目': 'Agenda items do not belong to the same project',
  '目标会议不存在': 'Target meeting not found',
  '目标会议不属于同一项目': 'Target meeting does not belong to the same project',
  '目标会议与开放问题不属于同一项目': 'Target meeting and open question do not belong to the same project',
  '来源开放问题不存在': 'Source open question not found',
  '来源开放问题与当前排期不一致': 'Source open question does not match the current schedule',
  '会议来源不存在': 'Source meeting not found',
  '项目或会议来源不存在': 'Source project or meeting not found',
  '会议来源与项目不匹配': 'Source meeting does not match the project',
  '议题来源与会议不匹配': 'Source agenda item does not match the meeting',
  '行动项项目与路径项目不匹配': 'Action item project does not match the URL project',
  '关联用户不存在或未启用': 'Referenced user does not exist or is not active',
  '会议成果来源链不完整': 'Meeting outcome provenance chain is incomplete',
  '复制议题违反数据完整性约束': 'Copying agenda item violated data integrity constraints',
  '开放问题写入违反数据完整性约束': 'Saving open question violated data integrity constraints',

  // Comments & inbox
  '评论不存在': 'Comment not found',
  '评论目标不存在': 'Comment target not found',
  '不支持此评论目标': 'Unsupported comment target',
  '评论游标无效': 'Invalid comment cursor',
  '只能分页读取根评论的回复': 'Replies can only be paginated for root comments',
  '回复必须属于同一评论目标': 'Reply must belong to the same comment target',
  '评论只能提及会议参与者': 'Comments can only mention meeting participants',
  '评论提及用户不存在或未启用': 'Mentioned user does not exist or is not active',
  '只能编辑自己的评论': 'You can only edit your own comments',
  '只能删除自己的评论': 'You can only delete your own comments',
  '只能解决自己的评论': 'You can only resolve your own comments',
  '只能解决评论主题': 'Only root comment threads can be resolved',
  '只能重开评论主题': 'Only root comment threads can be reopened',
  '已删除评论不可编辑': 'Deleted comments cannot be edited',
  '已删除评论不可解决': 'Deleted comments cannot be resolved',
  '已删除评论不可重开': 'Deleted comments cannot be reopened',
  '评论已被其他操作更新，请刷新后重试': 'Comment was updated by another operation; please refresh and try again',
  '通知不存在': 'Notification not found',

  // Attachments, calendar, webhooks
  '附件不存在': 'Attachment not found',
  '附件文件不存在': 'Attachment file is missing',
  '附件目标不存在': 'Attachment target not found',
  '只能删除自己上传的附件': 'You can only delete attachments you uploaded',
  '该附件不支持文本预览': 'Text preview is not supported for this attachment',
  '单个附件不能超过 20 MB': 'Attachment size cannot exceed 20 MB',
  '分片上传会话不存在或已过期': 'Chunk upload session does not exist or has expired',
  '分片数量必须大于 0': 'Chunk count must be greater than 0',
  '分片索引超出范围': 'Chunk index is out of range',
  '附件 SHA-256 校验不匹配': 'Attachment SHA-256 checksum mismatch',
  '附件分片路径无效': 'Invalid attachment chunk path',
  '附件路径无效': 'Invalid attachment path',
  '日历订阅令牌无效或已过期': 'Calendar subscription token is invalid or expired',
  'Webhook 地址必须使用 http:// 或 https:// 协议': 'Webhook URL must use http:// or https://',
  '禁止将 Webhook 发送至本地或内网地址': 'Sending Webhooks to localhost or private network addresses is forbidden',

  // Plugins & AI worker / stream
  '插件清单无效': 'Invalid plugin manifest',
  '插件加载失败': 'Failed to load plugin',
  '插件不存在': 'Plugin not found',
  '插件配置无效': 'Invalid plugin configuration',
  '插件配置不完整': 'Plugin configuration is incomplete',
  '插件输入无效': 'Invalid plugin input',
  '插件执行超时': 'Plugin execution timed out',
  '插件执行失败': 'Plugin execution failed',
  '插件导出失败': 'Plugin export failed',
  '插件导出结果无效': 'Invalid plugin export result',
  '插件返回格式无效': 'Invalid plugin response format',
  '插件不支持流式输出': 'Plugin does not support streaming output',
  '插件动作不存在': 'Plugin action not found',
  '插件流式动作不存在': 'Plugin stream action not found',
  '插件流式动作目标无效': 'Invalid plugin stream target',
  '插件目标无效': 'Invalid plugin target',
  '插件任务目标无效': 'Invalid plugin job target',
  '会议导出器不存在': 'Meeting exporter not found',
  '插件事件不存在': 'Plugin event not found',
  '只有失败事件可以重试': 'Only failed events can be retried',
  'AI 任务不存在': 'AI task not found',
  '无权查看此 AI 任务': 'You do not have permission to view this AI task',
  '无权操作此 AI 任务': 'You do not have permission to operate on this AI task',
  '当前 AI 任务无法取消': 'This AI task cannot be canceled',
  '当前 AI 草稿无法丢弃': 'This AI draft cannot be dismissed',
  '当前 AI 任务无法重新运行': 'This AI task cannot be rerun',
  '当前 AI 草稿无法应用': 'This AI draft cannot be applied',
  '任务筛选参数不完整': 'Incomplete task filter parameters',
  'AI 工作简报生成失败，请稍后重试': 'Failed to generate AI work brief, please try again later',
  'AI 工作简报请求失败，请稍后重试': 'AI work brief request failed, please try again later',
  'AI 工作简报返回格式无效': 'Invalid AI work brief response format',
  'AI 工作简报未返回流式内容': 'AI work brief returned no stream content',
  '认证或权限失败；检查管理员插件设置中的 API Key、服务地址和权限。':
    'Authentication or permission failed; check API Key, endpoint URL, and permissions in plugin settings.',
  'AI 服务额度不足；请充值或更换有可用额度的 API Key。':
    'Insufficient AI service balance; please top up or replace the API Key.',
  '找不到 AI 服务或模型；检查服务地址和模型名称。':
    'AI service or model not found; check endpoint URL and model name.',
  'AI 服务响应超时；请稍后重试或检查超时设置。':
    'AI service timed out; please try again later or check timeout settings.',
  'AI 服务限流或配额已用尽；请稍后重试并检查服务额度。':
    'AI service rate-limited or quota exhausted; please try again later and check quota.',
  'AI 服务返回 HTTP 状态错误。':
    'AI service returned an HTTP status error.',
  '无法连接 AI 服务；检查服务地址和网络。':
    'Unable to connect to AI service; check endpoint URL and network.',
  'AI 插件配置不完整；请联系管理员检查插件设置。':
    'AI plugin configuration is incomplete; please check plugin settings.',
  'AI 任务输入不符合插件要求。':
    'AI task input does not meet plugin requirements.',
  'AI 服务返回内容与插件格式不兼容。':
    'AI service response is incompatible with plugin format.',
  'AI 任务执行失败；请查看技术详情或联系管理员。':
    'AI task execution failed; check technical details or contact an administrator.',
  '服务重启，未重复发送 AI 请求':
    'Server restarted; AI request was not resent',
  '服务重启，事件重新排队':
    'Server restarted; event was re-queued',

  // Frontend fallback error messages
  '议题保存失败': 'Failed to save agenda item',
  'AI 提炼失败，请检查议题记录格式': 'AI extraction failed, please check notes format',
  'AI 提炼失败，请检查笔记标签格式': 'AI extraction failed, please check notes format',
  '议题状态更新失败': 'Failed to update agenda status',
  '请选择目标议题': 'Please select a target agenda item',
  '产出迁移失败': 'Failed to migrate outcomes',
  '转为开放问题失败': 'Failed to convert to open question',
  '目标会议加载失败': 'Failed to load target meetings',
  '请选择目标会议': 'Please select a target meeting',
  '议题复制失败': 'Failed to copy agenda item',
  '更新行动项失败': 'Failed to update action item',
  '结束时间必须晚于开始时间': 'End time must be after start time',
  '准备信息保存失败': 'Failed to save preparation info',
  '会议加载失败': 'Failed to load meeting',
  '会议保存失败': 'Failed to save meeting',
  '会议状态更新失败': 'Failed to update meeting status',
  '议题刷新失败': 'Failed to refresh agenda',
  '会议导出失败': 'Failed to export meeting',
  '议题排序失败': 'Failed to reorder agenda items',
  '议题添加失败': 'Failed to add agenda item',
  '议题操作失败': 'Agenda action failed',
  '议题已有产出，请先迁移产出，或将议题标记为取消。':
    'This agenda item already has outcomes. Please migrate its outcomes or cancel the item first.',
  '议题删除失败': 'Failed to delete agenda item',
  '议题移动失败': 'Failed to move agenda item',
  '议题开始失败': 'Failed to start agenda item',
  '插件列表加载失败': 'Failed to load plugins',
  '插件配置保存失败': 'Failed to save plugin configuration',
  '敏感配置清除失败': 'Failed to clear secret configuration',
  '插件状态更新失败': 'Failed to update plugin state',
  '插件事件重试失败': 'Failed to retry plugin event',
}

export const ZH_ERROR_MAP: Record<string, string> = Object.fromEntries(
  Object.entries(EN_ERROR_MAP).map(([zh, en]) => [en, zh]),
)

export const EN_ERROR_CODE_MAP: Record<string, string> = {
  invalid_credentials: 'Incorrect username or password',
  invalid_request: 'Invalid request parameters',
  validation_error: 'Invalid request parameters',
  forbidden: 'Permission denied',
  admin_required: 'Administrator privileges required',
  not_authenticated: 'Please sign in first',
  active_user_required: 'Account is not active yet',
  not_found: 'Resource not found',
  method_not_allowed: 'HTTP method not allowed',
  http_error: 'Unable to process request',
  meeting_locked: 'Meeting is locked',
  meeting_completed: 'Completed meeting cannot be modified',
  meeting_immutable: 'Meeting cannot be modified in its current state',
  version_conflict: 'Record was updated by another operation; please refresh and try again',
  provider_auth_failed:
    'Authentication or permission failed; check API Key, endpoint URL, and permissions in plugin settings.',
  provider_insufficient_balance:
    'Insufficient AI service balance; please top up or replace the API Key.',
  provider_not_found:
    'AI service or model not found; check endpoint URL and model name.',
  provider_timeout:
    'AI service timed out; please try again later or check timeout settings.',
  provider_rate_limited:
    'AI service rate-limited or quota exhausted; please try again later and check quota.',
  provider_http_error:
    'AI service returned an HTTP status error.',
  provider_network_error:
    'Unable to connect to AI service; check endpoint URL and network.',
  plugin_not_configured:
    'AI plugin configuration is incomplete; please check plugin settings.',
  plugin_input_invalid:
    'AI task input does not meet plugin requirements.',
  plugin_output_invalid:
    'AI service response is incompatible with plugin format.',
  plugin_failed:
    'AI task execution failed; check technical details or contact an administrator.',
  process_restarted:
    'Server restarted; AI request was not resent',
  ManifestError: 'Invalid plugin manifest',
}

export function translateBackendError(msg: string, code?: string | null): string {
  if (!msg) return msg
  const trimmed = msg.trim()

  if (locale.value !== 'en') {
    if (ZH_ERROR_MAP[trimmed]) {
      return ZH_ERROR_MAP[trimmed]
    }
    const enChunkMatch = trimmed.match(/^Chunk\s+(\d+)\s+has not been uploaded yet$/)
    if (enChunkMatch) {
      return `分片 ${enChunkMatch[1]} 尚未上传`
    }
    const enWebhookStatusMatch = trimmed.match(/^Webhook returned error status:\s*(.+)$/)
    if (enWebhookStatusMatch) {
      return `Webhook返回错误状态码: ${enWebhookStatusMatch[1]}`
    }
    const enWebhookErrorMatch = trimmed.match(/^Webhook delivery failed:\s*(.+)$/)
    if (enWebhookErrorMatch) {
      return `Webhook发送失败: ${enWebhookErrorMatch[1]}`
    }
    return msg
  }

  if (EN_ERROR_MAP[trimmed]) {
    return EN_ERROR_MAP[trimmed]
  }

  const chunkMatch = trimmed.match(/^分片\s+(\d+)\s+尚未上传$/)
  if (chunkMatch) {
    return `Chunk ${chunkMatch[1]} has not been uploaded yet`
  }
  const webhookStatusMatch = trimmed.match(/^Webhook返回错误状态码:\s*(.+)$/)
  if (webhookStatusMatch) {
    return `Webhook returned error status: ${webhookStatusMatch[1]}`
  }
  const webhookErrorMatch = trimmed.match(/^Webhook发送失败:\s*(.+)$/)
  if (webhookErrorMatch) {
    return `Webhook delivery failed: ${webhookErrorMatch[1]}`
  }

  if (code && EN_ERROR_CODE_MAP[code]) {
    return EN_ERROR_CODE_MAP[code]
  }

  return msg
}

export function errorMessage(reason: unknown, fallback: string): string {
  if (reason instanceof Error) {
    const code = 'code' in reason && typeof (reason as { code?: unknown }).code === 'string'
      ? (reason as { code: string }).code
      : null
    const translated = translateBackendError(reason.message, code)
    if (locale.value === 'en' && CJK_RE.test(translated) && fallback && !CJK_RE.test(fallback)) {
      return fallback
    }
    return translated
  }
  return translateBackendError(fallback)
}
