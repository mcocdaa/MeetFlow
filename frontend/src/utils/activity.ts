type ActivityPayload = Record<string, unknown> | null | undefined

/**
 * Event label templates for the project activity ledger.
 *
 * Each entry is `[withSubject, withoutSubject]`; the subject is taken from
 * `payload.title`, then `payload.name`, then `payload.filename`. Unknown event types
 * fall back to the raw `event_type` so the ledger never shows invented text.
 */
const ACTIVITY_TEMPLATES: Record<string, [string, string]> = {
  'project.created': ['创建了项目「{subject}」', '创建了项目'],
  'project.updated': ['更新了项目「{subject}」', '更新了项目'],
  'project.progress_posted': ['发布了项目进展「{subject}」', '发布了项目进展'],
  'project.progress_updated': ['更新了项目进展「{subject}」', '更新了项目进展'],
  'project.deleted': ['删除了项目「{subject}」', '删除了项目'],

  'meeting.created': ['创建了会议「{subject}」', '创建了会议'],
  'meeting.updated': ['更新了会议「{subject}」', '更新了会议'],
  'meeting.amended': ['补充了会议记录「{subject}」', '补充了会议记录'],
  'meeting.canceled': ['取消了会议「{subject}」', '取消了会议'],
  'meeting.completed': ['结束了会议「{subject}」', '结束了会议'],
  'meeting.reopened': ['重新打开了会议「{subject}」', '重新打开了会议'],

  'agenda.started': ['开始了议题「{subject}」', '开始了议题'],
  'agenda.reordered': ['调整了议题顺序', '调整了议题顺序'],
  'agenda.converted_to_question': ['把议题转为开放问题「{subject}」', '把议题转为开放问题'],
  'agenda.copied': ['复制了议题「{subject}」', '复制了议题'],
  'agenda.outcomes_migrated': ['迁移了议题产出「{subject}」', '迁移了议题产出'],

  'attachment.uploaded': ['上传了附件「{subject}」', '上传了附件'],
  'attachment.deleted': ['删除了附件「{subject}」', '删除了附件'],

  'decision.created': ['创建了决策「{subject}」', '创建了决策'],
  'decision.updated': ['更新了决策「{subject}」', '更新了决策'],
  'decision.reviewed': ['评审了决策「{subject}」', '评审了决策'],
  'decision.finalized': ['定稿了决策「{subject}」', '定稿了决策'],
  'decision.withdrawn': ['撤回了决策「{subject}」', '撤回了决策'],
  'decision.superseded': ['替代了决策「{subject}」', '替代了决策'],

  'action.created': ['创建了行动项「{subject}」', '创建了行动项'],

  'question.created': ['创建了开放问题「{subject}」', '创建了开放问题'],
  'question.updated': ['更新了开放问题「{subject}」', '更新了开放问题'],
  'question.scheduled': ['排期了开放问题「{subject}」', '排期了开放问题'],
  'question.resolved': ['解决了开放问题「{subject}」', '解决了开放问题'],
}

function subjectOf(payload: ActivityPayload): string | null {
  if (!payload) return null
  for (const key of ['title', 'name', 'filename'] as const) {
    const value = payload[key]
    if (typeof value === 'string' && value.trim()) return value
  }
  return null
}

/** Human-readable Chinese label for an activity ledger event. */
export function activityLabel(eventType: string, payload?: ActivityPayload): string {
  const template = ACTIVITY_TEMPLATES[eventType]
  if (!template) return eventType
  const subject = subjectOf(payload)
  return (subject ? template[0] : template[1]).replace('{subject}', subject ?? '')
}
