export type StatusKind =
  | 'meeting'
  | 'agenda'
  | 'decision'
  | 'action'
  | 'question'
  | 'project'
  | 'user'
  | 'job'
  | 'priority'

export const MEETING_STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  ready: '待开始',
  in_progress: '进行中',
  completed: '已完成',
  canceled: '已取消',
}

export const AGENDA_STATUS_LABELS: Record<string, string> = {
  planned: '待开始',
  in_progress: '进行中',
  completed: '已完成',
  skipped: '已跳过',
  canceled: '已取消',
}

export const DECISION_STATUS_LABELS: Record<string, string> = {
  proposed: '待确认',
  final: '已生效',
  superseded: '已替代',
  withdrawn: '已撤回',
}

export const ACTION_STATUS_LABELS: Record<string, string> = {
  open: '待开始',
  in_progress: '进行中',
  done: '已完成',
  canceled: '已取消',
}

export const QUESTION_STATUS_LABELS: Record<string, string> = {
  open: '待解答',
  scheduled: '已排期',
  resolved: '已解决',
  dropped: '已放弃',
}

export const PROJECT_STATUS_LABELS: Record<string, string> = {
  planned: '计划中',
  active: '进行中',
  paused: '已暂停',
  completed: '已完成',
  canceled: '已取消',
}

export const USER_STATUS_LABELS: Record<string, string> = {
  pending: '待审批',
  active: '已启用',
  rejected: '已拒绝',
  disabled: '已归档',
}

export const JOB_STATUS_LABELS: Record<string, string> = {
  queued: '排队中',
  requesting: '生成中',
  succeeded: '已生成',
  failed: '失败',
  interrupted: '中断',
  canceled: '已取消',
  dismissed: '已丢弃',
  applied: '已应用',
}

export const PRIORITY_LABELS: Record<string, string> = {
  urgent: '紧急',
  high: '高',
  normal: '普通',
  low: '低',
}

const LABELS_BY_KIND: Record<StatusKind, Record<string, string>> = {
  meeting: MEETING_STATUS_LABELS,
  agenda: AGENDA_STATUS_LABELS,
  decision: DECISION_STATUS_LABELS,
  action: ACTION_STATUS_LABELS,
  question: QUESTION_STATUS_LABELS,
  project: PROJECT_STATUS_LABELS,
  user: USER_STATUS_LABELS,
  job: JOB_STATUS_LABELS,
  priority: PRIORITY_LABELS,
}

export function statusLabel(kind: StatusKind, status: string): string {
  return LABELS_BY_KIND[kind][status] ?? status
}

export const meetingStatusLabel = (status: string) => statusLabel('meeting', status)
export const agendaStatusLabel = (status: string) => statusLabel('agenda', status)
export const decisionStatusLabel = (status: string) => statusLabel('decision', status)
export const actionStatusLabel = (status: string) => statusLabel('action', status)
export const questionStatusLabel = (status: string) => statusLabel('question', status)
export const projectStatusLabel = (status: string) => statusLabel('project', status)
export const userStatusLabel = (status: string) => statusLabel('user', status)
export const jobStatusLabel = (status: string) => statusLabel('job', status)
export const priorityLabel = (priority: string) => statusLabel('priority', priority)
