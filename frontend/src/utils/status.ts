import type { AgendaItem } from '../domain/meetings'

const AGENDA_STATUS_LABELS: Record<AgendaItem['status'], string> = {
  planned: '待开始',
  in_progress: '进行中',
  completed: '已完成',
  skipped: '已跳过',
  canceled: '已取消',
}

export function agendaStatusLabel(status: AgendaItem['status']): string {
  return AGENDA_STATUS_LABELS[status]
}
