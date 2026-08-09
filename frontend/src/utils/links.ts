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

export function subjectLabel(subjectType: string): string {
  if (subjectType === 'meeting') return '会议'
  if (subjectType === 'agenda_item') return '议题'
  if (subjectType === 'decision') return '决策'
  if (subjectType === 'project') return '项目'
  return '行动项'
}
