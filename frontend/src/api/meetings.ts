import { api, apiDownload } from './client'
import type { Meeting, MeetingParticipantWrite } from '../domain/meetings'

export type LifecycleAction = 'start' | 'finish' | 'cancel' | 'reopen'

export type MeetingUpdate = {
  expected_version: number
  title: string
  purpose_markdown: string
  raw_notes_markdown: string
  summary_markdown: string
  scheduled_start: string
  scheduled_end: string
  host_user_id?: string | null
  recorder_user_id?: string | null
  participants?: MeetingParticipantWrite[]
}

export function getMeeting(id: string) {
  return api<Meeting>(`/api/meetings/${id}`)
}

export function runMeetingLifecycle(id: string, action: LifecycleAction, expectedVersion: number) {
  return api<Meeting>(`/api/meetings/${id}/${action}`, {
    method: 'POST',
    body: JSON.stringify({ expected_version: expectedVersion }),
  })
}

export function downloadMeetingExport(id: string, exporterId: string) {
  return apiDownload(`/api/meetings/${id}/plugin-exports/${encodeURIComponent(exporterId)}`, { method: 'POST' })
}

export type MeetingIngestPayload = {
  agenda_title?: string
  agenda_item_id?: string | number | null
  notes_markdown: string
  auto_complete_agenda?: boolean
}

export type MeetingIngestResponse = Meeting & {
  meeting?: Meeting
  ingested_agenda_item_id: string
  decisions: number
  actions: number
  questions: number
  extracted: {
    decisions: number
    actions: number
    questions: number
  }
}

export type ApiKeyInfo = {
  api_key: string
  token_prefix: string
  user_id: string
  username: string
}

export function ingestMeetingNotes(id: string, payload: MeetingIngestPayload) {
  return api<MeetingIngestResponse>(`/api/v1/meetings/${id}/ingest`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchApiKey() {
  return api<ApiKeyInfo>('/api/v1/auth/api-key')
}

export function rotateApiKey() {
  return api<ApiKeyInfo>('/api/v1/auth/api-key/rotate', {
    method: 'POST',
  })
}

export function smartStructureAgendaNotes(rawMarkdown: string, agendaTitle: string): string {
  const title = agendaTitle.trim() || '当前议题'
  const trimmed = rawMarkdown.trim()

  if (!trimmed) {
    return [
      `### ${title} · 讨论要点`,
      `@决策: 确认「${title}」核心实施方案与演进路径`,
      `@行动:[open] 完成「${title}」接口联调与自动化回归测试`,
      `@开放问题: 「${title}」存量数据迁移窗口是否需要灰度验证？`,
    ].join('\n')
  }

  const lines = trimmed.split(/\r?\n/)
  const normalizedLines: string[] = []
  const existingTags = new Set<string>()
  const extractedTags: string[] = []

  for (const originalLine of lines) {
    const rawLine = originalLine.replace(/\\([[\]])/g, '$1')
    const bulletTagMatch = rawLine.match(/^\s*[-*•]\s*(@(?:决策|行动|开放问题|问题):.+)$/)
    if (bulletTagMatch) {
      const tagLine = bulletTagMatch[1].trim()
      normalizedLines.push(tagLine)
      existingTags.add(tagLine)
      continue
    }

    const stripped = rawLine.trim()
    if (/^@(?:决策|行动|开放问题|问题):/.test(stripped)) {
      normalizedLines.push(stripped)
      existingTags.add(stripped)
      continue
    }

    normalizedLines.push(rawLine)

    const cleanLine = stripped.replace(/^[-*•\d.)\s]+/, '').trim()
    if (!cleanLine || cleanLine.startsWith('#') || cleanLine.startsWith('```')) {
      continue
    }

    if (/(?:决定|确定|决议|统一采用|采用|拍板|一致同意|定稿|结论[：:])/.test(cleanLine)) {
      const content = cleanLine.replace(/^(?:团队一致决定|一致决定|决定|确定|决议|结论[：:])\s*/, '').trim()
      if (content) {
        const tag = `@决策: ${content}`
        if (!existingTags.has(tag)) extractedTags.push(tag)
      }
    } else if (/(?:待确认|疑问|是否|如何|待评估|[？?]$)/.test(cleanLine)) {
      const content = cleanLine.replace(/^(?:待确认[：:]?|疑问[：:]?|问题[：:]?)\s*/, '').trim()
      if (content) {
        const tag = `@开放问题: ${content}`
        if (!existingTags.has(tag)) extractedTags.push(tag)
      }
    } else if (/(?:负责|跟进|待办|完成|推进|输出|补充|联调|验证|编写|提交)/.test(cleanLine)) {
      const content = cleanLine.replace(/^(?:待办[：:]?|行动[：:]?)\s*/, '').trim()
      if (content) {
        const ownerMatch = content.match(/@([a-zA-Z0-9_-]+)/)
        const ownerTag = ownerMatch ? `[@${ownerMatch[1]}]` : ''
        const tag = `@行动:[open]${ownerTag} ${content}`
        if (!existingTags.has(tag)) extractedTags.push(tag)
      }
    }
  }

  const dedupedExtracted = extractedTags.filter((tag) => !existingTags.has(tag))
  if (dedupedExtracted.length > 0) {
    return `${normalizedLines.join('\n')}\n\n${dedupedExtracted.join('\n\n')}`
  }

  if (existingTags.size === 0) {
    return [
      normalizedLines.join('\n'),
      '',
      `@决策: 确认推进「${title}」方案落地`,
      '',
      `@行动:[open] 跟进「${title}」后续实施与联调验证`,
      '',
      `@开放问题: 「${title}」跨模块边界细节待最终确认`,
    ].join('\n')
  }

  return normalizedLines.join('\n')
}

