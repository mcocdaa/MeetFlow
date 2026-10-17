import { locale, translateSeededText } from '../i18n'

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
  'meeting.started': ['开始了会议「{subject}」', '开始了会议'],
  'meeting.finished': ['结束了会议「{subject}」', '结束了会议'],
  'meeting.amended': ['补充了会议记录「{subject}」', '补充了会议记录'],
  'meeting.canceled': ['取消了会议「{subject}」', '取消了会议'],
  'meeting.completed': ['结束了会议「{subject}」', '结束了会议'],
  'meeting.reopened': ['重新打开了会议「{subject}」', '重新打开了会议'],
  'meeting.notes_ingested': ['提炼并同步了会议纪要「{subject}」', '在会议中完成了 AI 智能提炼'],

  'agenda.created': ['创建了议题「{subject}」', '创建了议题'],
  'agenda.updated': ['更新了议题「{subject}」', '更新了议题'],
  'agenda.deleted': ['删除了议题「{subject}」', '删除了议题'],
  'agenda.moved': ['移动了议题「{subject}」', '移动了议题'],
  'agenda.reordered': ['调整了议题顺序', '调整了议题顺序'],
  'agenda.started': ['开始了议题「{subject}」', '开始了议题'],
  'agenda.completed': ['完成了议题「{subject}」', '完成了议题'],
  'agenda.skipped': ['跳过了议题「{subject}」', '跳过了议题'],
  'agenda.canceled': ['取消了议题「{subject}」', '取消了议题'],
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
  'action.updated': ['更新了行动项「{subject}」', '更新了行动项'],
  'action.completed': ['完成了行动项「{subject}」', '完成了行动项'],
  'action.reopened': ['重新打开了行动项「{subject}」', '重新打开了行动项'],
  'action.status_changed': ['变更了行动项状态「{subject}」', '变更了行动项状态'],

  'question.created': ['创建了开放问题「{subject}」', '创建了开放问题'],
  'question.updated': ['更新了开放问题「{subject}」', '更新了开放问题'],
  'question.scheduled': ['排期了开放问题「{subject}」', '排期了开放问题'],
  'question.resolved': ['解决了开放问题「{subject}」', '解决了开放问题'],

  'comment.created': ['发表了评论', '发表了评论'],
  'comment.replied': ['回复了评论', '回复了评论'],
  'comment.updated': ['编辑了评论', '编辑了评论'],
  'comment.deleted': ['删除了评论', '删除了评论'],
  'comment.resolved': ['解决了评论', '解决了评论'],
  'comment.reopened': ['重新打开了评论', '重新打开了评论'],
}

const EN_ACTIVITY_TEMPLATES: Record<string, [string, string]> = {
  'project.created': ['Created project "{subject}"', 'Created project'],
  'project.updated': ['Updated project "{subject}"', 'Updated project'],
  'project.progress_posted': ['Posted project update "{subject}"', 'Posted project update'],
  'project.progress_updated': ['Updated project progress "{subject}"', 'Updated project progress'],
  'project.deleted': ['Deleted project "{subject}"', 'Deleted project'],

  'meeting.created': ['Created meeting "{subject}"', 'Created meeting'],
  'meeting.updated': ['Updated meeting "{subject}"', 'Updated meeting'],
  'meeting.started': ['Started meeting "{subject}"', 'Started meeting'],
  'meeting.finished': ['Finished meeting "{subject}"', 'Finished meeting'],
  'meeting.amended': ['Amended meeting notes "{subject}"', 'Amended meeting notes'],
  'meeting.canceled': ['Canceled meeting "{subject}"', 'Canceled meeting'],
  'meeting.completed': ['Completed meeting "{subject}"', 'Completed meeting'],
  'meeting.reopened': ['Reopened meeting "{subject}"', 'Reopened meeting'],
  'meeting.notes_ingested': ['Extracted and synced meeting notes "{subject}"', 'Ran AI Smart Extract on meeting notes'],

  'agenda.created': ['Created agenda item "{subject}"', 'Created agenda item'],
  'agenda.updated': ['Updated agenda item "{subject}"', 'Updated agenda item'],
  'agenda.deleted': ['Deleted agenda item "{subject}"', 'Deleted agenda item'],
  'agenda.moved': ['Moved agenda item "{subject}"', 'Moved agenda item'],
  'agenda.reordered': ['Reordered agenda items', 'Reordered agenda items'],
  'agenda.started': ['Started agenda item "{subject}"', 'Started agenda item'],
  'agenda.completed': ['Completed agenda item "{subject}"', 'Completed agenda item'],
  'agenda.skipped': ['Skipped agenda item "{subject}"', 'Skipped agenda item'],
  'agenda.canceled': ['Canceled agenda item "{subject}"', 'Canceled agenda item'],
  'agenda.converted_to_question': ['Converted agenda item to open question "{subject}"', 'Converted agenda item to open question'],
  'agenda.copied': ['Copied agenda item "{subject}"', 'Copied agenda item'],
  'agenda.outcomes_migrated': ['Migrated agenda outcomes "{subject}"', 'Migrated agenda outcomes'],

  'attachment.uploaded': ['Uploaded attachment "{subject}"', 'Uploaded attachment'],
  'attachment.deleted': ['Deleted attachment "{subject}"', 'Deleted attachment'],

  'decision.created': ['Created decision "{subject}"', 'Created decision'],
  'decision.updated': ['Updated decision "{subject}"', 'Updated decision'],
  'decision.reviewed': ['Reviewed decision "{subject}"', 'Reviewed decision'],
  'decision.finalized': ['Finalized decision "{subject}"', 'Finalized decision'],
  'decision.withdrawn': ['Withdrawn decision "{subject}"', 'Withdrawn decision'],
  'decision.superseded': ['Superseded decision "{subject}"', 'Superseded decision'],

  'action.created': ['Created action item "{subject}"', 'Created action item'],
  'action.updated': ['Updated action item "{subject}"', 'Updated action item'],
  'action.completed': ['Completed action item "{subject}"', 'Completed action item'],
  'action.reopened': ['Reopened action item "{subject}"', 'Reopened action item'],
  'action.status_changed': ['Changed action item status "{subject}"', 'Changed action item status'],

  'question.created': ['Created open question "{subject}"', 'Created open question'],
  'question.updated': ['Updated open question "{subject}"', 'Updated open question'],
  'question.scheduled': ['Scheduled open question "{subject}"', 'Scheduled open question'],
  'question.resolved': ['Resolved open question "{subject}"', 'Resolved open question'],

  'comment.created': ['Posted a comment', 'Posted a comment'],
  'comment.replied': ['Replied to a comment', 'Replied to a comment'],
  'comment.updated': ['Edited a comment', 'Edited a comment'],
  'comment.deleted': ['Deleted a comment', 'Deleted a comment'],
  'comment.resolved': ['Resolved a comment', 'Resolved a comment'],
  'comment.reopened': ['Reopened a comment', 'Reopened a comment'],
}

function subjectOf(payload: ActivityPayload): string | null {
  if (!payload) return null
  for (const key of ['title', 'name', 'filename'] as const) {
    const value = payload[key]
    if (typeof value === 'string' && value.trim()) return value
  }
  return null
}

/** Human-readable label for an activity ledger event. */
export function activityLabel(eventType: string, payload?: ActivityPayload): string {
  const dict = locale.value === 'en' ? EN_ACTIVITY_TEMPLATES : ACTIVITY_TEMPLATES
  const template = dict[eventType]
  if (!template) return eventType
  const rawSubject = subjectOf(payload)
  const subject = rawSubject ? translateSeededText(rawSubject, locale.value) : null
  return (subject ? template[0] : template[1]).replace('{subject}', subject ?? '')
}
