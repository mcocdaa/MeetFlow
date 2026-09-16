export function subjectHref(
  subjectType: string,
  subjectId: string,
  meetingId?: string | null,
): string {
  if (subjectType === 'meeting') return `/meetings/${subjectId}`
  if (subjectType === 'agenda_item') return meetingId ? `/meetings/${meetingId}` : '/meetings'
  if (subjectType === 'decision') return `/decisions?highlight=${subjectId}`
  if (subjectType === 'project') return `/projects/${subjectId}`
  return `/actions?highlight=${subjectId}`
}

/**
 * Notification deep links prefer the source comment anchor: a mention/reply opens the
 * meeting workspace with the comments drawer focused on that comment. Everything else
 * falls back to the existing subject link.
 */
export function notificationHref(item: {
  subject: { type: string; id: string }
  meeting: { id: string } | null
  source_comment: { id: string } | null
}): string {
  if (item.source_comment && item.meeting) {
    return `/meetings/${item.meeting.id}?comment=${item.source_comment.id}`
  }
  return subjectHref(item.subject.type, item.subject.id, item.meeting?.id)
}

export function subjectLabel(subjectType: string): string {
  if (subjectType === 'meeting') return '会议'
  if (subjectType === 'agenda_item') return '议题'
  if (subjectType === 'decision') return '决策'
  if (subjectType === 'project') return '项目'
  return '行动项'
}
