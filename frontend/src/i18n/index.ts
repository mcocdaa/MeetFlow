import { computed, ref, watch } from 'vue'

export type Locale = 'zh' | 'en'

export const STORAGE_KEY = 'meetflow_lang'

function readInitialLocale(): Locale {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      const saved = window.localStorage.getItem(STORAGE_KEY)
      if (saved === 'en') return 'en'
    }
  } catch {
    // Ignore storage access errors in restricted environments.
  }
  return 'zh'
}

function syncDocumentLocale(next: Locale): void {
  try {
    if (typeof document !== 'undefined' && document.documentElement) {
      document.documentElement.lang = next
    }
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('meetflow:lang-change', { detail: { lang: next } }))
    }
  } catch {
    // Ignore DOM/event errors in restricted environments.
  }
}

export const locale = ref<Locale>(readInitialLocale())
syncDocumentLocale(locale.value)

watch(locale, (next) => {
  syncDocumentLocale(next)
})

export const isEn = computed(() => locale.value === 'en')

export function setLocale(lang: Locale): void {
  const next: Locale = lang === 'en' ? 'en' : 'zh'
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      window.localStorage.setItem(STORAGE_KEY, next)
    }
  } catch {
    // Ignore storage write errors.
  }
  locale.value = next
  syncDocumentLocale(next)
}

export function toggleLocale(): Locale {
  const next: Locale = locale.value === 'zh' ? 'en' : 'zh'
  setLocale(next)
  return next
}

export const messages: Record<Locale, Record<string, string>> = {
  zh: {
    'app.sharedWorkspace': '共享工作区',
    'app.inbox': '收件箱',
    'app.accountMenu': '账户菜单',
    'app.accountSettings': '账号设置',
    'app.logout': '退出登录',
    'app.langToggle': '🌐 EN',
    'sidebar.brandSub': '团队会议工作区',
    'sidebar.workspaceNav': '工作区导航',
    'sidebar.adminNav': '管理员导航',
    'sidebar.adminSection': '管理员',
    'sidebar.forYou': '为你',
    'sidebar.projects': '项目',
    'sidebar.meetings': '会议',
    'sidebar.actions': '行动项',
    'sidebar.decisions': '决策',
    'sidebar.inbox': '收件箱',
    'sidebar.aiTasks': 'AI 任务',
    'sidebar.users': '用户',
    'sidebar.plugins': '插件',
    'sidebar.settings': '设置',
    'meeting.calendar': '日历订阅',
    'meeting.webhook': '推送群聊',
    'meeting.focusMode': '专注模式',
    'meeting.endMeeting': '结束会议',
    'meeting.cancelMeeting': '取消会议',
    'meeting.startMeeting': '开始会议',
    'meeting.prepInfo': '准备信息',
    'meeting.reopen': '重新打开',
    'agenda.queue': '议题队列',
    'agenda.add': '+ 议题',
    'agenda.collapse': '收起',
    'agenda.type': '类型',
    'agenda.duration': '预计时长',
    'agenda.proposer': '提案人',
    'agenda.speaker': '主讲人',
    'agenda.notes': '议题记录',
    'agenda.aiExtract': 'AI 智能提炼',
    'agenda.extracting': '正在提炼…',
    'agenda.outcomes': '本议题产出',
    'agenda.addDecision': '+ 决策',
    'agenda.addAction': '+ 行动',
    'agenda.addQuestion': '+ 开放问题',
    'agenda.fromNotes': '来自议题记录',
    'focus.completeAndNext': '完成并下一项',
    'focus.exitFocus': '退出专注',
    'focus.liveOutcomes': '实时决议与待办',
    'focus.addQuestion': '+ 问题',
  },
  en: {
    'app.sharedWorkspace': 'Shared Workspace',
    'app.inbox': 'Inbox',
    'app.accountMenu': 'Account menu',
    'app.accountSettings': 'Account Settings',
    'app.logout': 'Sign Out',
    'app.langToggle': '🌐 中文',
    'sidebar.brandSub': 'Team Workspace',
    'sidebar.workspaceNav': 'Workspace navigation',
    'sidebar.adminNav': 'Admin navigation',
    'sidebar.adminSection': 'Admin',
    'sidebar.forYou': 'For You',
    'sidebar.projects': 'Projects',
    'sidebar.meetings': 'Meetings',
    'sidebar.actions': 'Actions',
    'sidebar.decisions': 'Decisions',
    'sidebar.inbox': 'Inbox',
    'sidebar.aiTasks': 'AI Tasks',
    'sidebar.users': 'Users',
    'sidebar.plugins': 'Plugins',
    'sidebar.settings': 'Settings',
    'meeting.calendar': 'Calendar',
    'meeting.webhook': 'Webhook',
    'meeting.focusMode': 'Focus Mode',
    'meeting.endMeeting': 'End Meeting',
    'meeting.cancelMeeting': 'Cancel',
    'meeting.startMeeting': 'Start Meeting',
    'meeting.prepInfo': 'Prep Info',
    'meeting.reopen': 'Reopen',
    'agenda.queue': 'Agenda Queue',
    'agenda.add': '+ Agenda',
    'agenda.collapse': 'Close',
    'agenda.type': 'Type',
    'agenda.duration': 'Duration',
    'agenda.proposer': 'Proposer',
    'agenda.speaker': 'Speaker',
    'agenda.notes': 'Agenda Notes',
    'agenda.aiExtract': 'AI Extract',
    'agenda.extracting': 'Extracting…',
    'agenda.outcomes': 'Topic Outcomes',
    'agenda.addDecision': '+ Decision',
    'agenda.addAction': '+ Action',
    'agenda.addQuestion': '+ Question',
    'agenda.fromNotes': 'From Notes',
    'focus.completeAndNext': 'Complete & Next',
    'focus.exitFocus': 'Exit Focus',
    'focus.liveOutcomes': 'Live Outcomes',
    'focus.addQuestion': '+ Question',
  },
}

export function t(key: string, params?: Record<string, string | number>): string {
  const dict = messages[locale.value] ?? messages.zh
  let template = dict[key] ?? messages.zh[key] ?? key
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      template = template.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v))
    }
  }
  return template
}

export function tr(zhText: string, enText: string): string {
  return locale.value === 'en' ? enText : zhText
}

export const SEEDED_ZH_TO_EN: Record<string, string> = {
  'MeetFlow 核心研发': 'MeetFlow Core R&D',
  '团队会议工作区与实时决议双向流转引擎': 'Team meeting workspace and real-time outcome sync engine',
  'Q3 架构演进与双语协作周会': 'Q3 Architecture Evolution & Bilingual Sync',
  '确认 Canonical REST API 收敛、专注模式双向同步与群聊集成方案。':
    'Confirm Canonical REST API convergence, Focus Mode two-way sync, and Webhook integration.',
  '本次周会确认了 Canonical REST API 统一收敛方案、专注模式双向同步机制及日历/群聊集成节奏。':
    'Confirmed Canonical REST API convergence plan, Focus Mode two-way sync mechanism, and Calendar/Webhook integration schedule.',
  '参会人围绕 REST 契约、插件沙箱与专注模式实时联动进行了对齐。':
    'Participants aligned on REST contracts, plugin sandbox, and Focus Mode real-time sync.',
  '林宇': 'Lin Yu',
  '系统管理员': 'System Admin',
  '乔安': 'Qiao An',
  '陈晨': 'Chen Chen',
  '统一 REST API 与插件契约收敛': 'Unify REST API & Plugin Contract Convergence',
  '会议专注模式与笔记双向同步压测': 'Focus Mode & Two-Way Notes Sync Stress Test',
  '日历订阅 ICS 签名与群聊推送联调': 'Calendar ICS Signing & Webhook Push Integration',
  '### 核心讨论记录': '### Core Discussion Notes',
  '- 团队一致决定采用 Canonical REST API 统一接入标准，废弃旧版兼容层':
    '- Team decided to standardize on Canonical REST API and deprecate legacy compatibility layer',
  '- 请 @lin 在本周五前完成网关鉴权与插件沙箱回归测试':
    '- @lin to complete gateway auth and plugin sandbox regression tests by Friday',
  '- 存量历史纪要数据迁移窗口是否需要灰度双写验证？':
    '- Does the historical meeting notes migration window require canary dual-write verification?',
  '团队一致决定采用 Canonical REST API 统一接入标准，废弃旧版兼容层':
    'Team decided to standardize on Canonical REST API and deprecate legacy compatibility layer',
  '请 @lin 在本周五前完成网关鉴权与插件沙箱回归测试':
    '@lin to complete gateway auth and plugin sandbox regression tests by Friday',
  '存量历史纪要数据迁移窗口是否需要灰度双写验证？':
    'Does the historical meeting notes migration window require canary dual-write verification?',
  '### 专注模式走查': '### Focus Mode Walkthrough',
  '- 专注模式默认开启实时决议与待办分栏联动':
    '- Enable live outcomes split-pane sync by default in Focus Mode',
  '- 请 @lin 补充专注模式快捷键与状态流转端到端测试':
    '- @lin to add end-to-end tests for Focus Mode shortcuts and status transitions',
  '- 跨项目开放问题池是否支持一键排入下周周会？':
    '- Should the cross-project open question pool support one-click scheduling into next week sync?',
  '专注模式默认开启实时决议与待办分栏联动':
    'Enable live outcomes split-pane sync by default in Focus Mode',
  '请 @lin 补充专注模式快捷键与状态流转端到端测试':
    '@lin to add end-to-end tests for Focus Mode shortcuts and status transitions',
  '补充专注模式快捷键与状态流转端到端测试':
    'Add end-to-end tests for Focus Mode shortcuts and status transitions',
  '跨项目开放问题池是否支持一键排入下周周会？':
    'Should the cross-project open question pool support one-click scheduling into next week sync?',
  '### 日历与群聊推送联调': '### Calendar & Webhook Integration',
  '确认采用 HMAC-SHA256 签名保护个人 ICS 订阅源':
    'Confirm HMAC-SHA256 signing for personal ICS subscription feeds',
  '完成飞书与钉钉群机器人卡片推送重试验证':
    'Verify Feishu and DingTalk webhook card delivery retries',
  '是否开启跨项目 Webhook 汇总通知？':
    'Should cross-project Webhook digest notifications be enabled?',
  '林宇 (Lin Yu)': 'Lin Yu',
  'AI 原生会议工作流、双向行动项同步与中英双语界面升级':
    'AI-native meeting workflow, two-way action sync, and bilingual UI upgrade',
  '聚焦会前准备、会中专注研讨与会后归档闭环。':
    'Focus on pre-meeting prep, live focused discussion, and post-meeting archive loop.',
  'Q3 架构演进与中英双语体验评审': 'Q3 Architecture Evolution & Bilingual UX Review',
  '评审页内 ✨ AI 智能提炼、双向行动项状态机及中英双语无缝切换体验。':
    'Review in-place ✨ AI Smart Extract, two-way action state machine, and seamless bilingual switching.',
  '页内 ✨ AI 智能提炼与结构化产出': 'In-place ✨ AI Smart Extract & Structured Outcomes',
  '围绕会议记录与 AI 提炼流程达成以下结论：':
    'Key conclusions on meeting notes and AI extraction workflow:',
  '团队一致决定采用页内 ✨ AI 智能提炼直接写入当前议题记录，彻底移除冗余弹窗':
    'Unanimously decided to use in-place ✨ AI Smart Extract directly in agenda notes, removing redundant modals',
  '采用页内 ✨ AI 智能提炼直接写入当前议题记录，彻底移除冗余弹窗':
    'Use in-place ✨ AI Smart Extract directly in agenda notes, removing redundant modals',
  '请 @admin 完善中英双语标签 (@决策/@Decision、@行动/@Action) 解析与单元测试':
    'Please @admin refine bilingual tag (@Decision, @Action) parsing and unit tests',
  '完善中英双语标签 (@决策/@Decision、@行动/@Action) 解析与单元测试':
    'Refine bilingual tag (@Decision, @Action) parsing and unit tests',
  '请 @admin 完善中英双语结构化标签解析与自动化单元测试':
    'Please @admin refine bilingual structured tag parsing and automated unit tests',
  '完善中英双语结构化标签解析与自动化单元测试':
    'Refine bilingual structured tag parsing and automated unit tests',
  '后续是否支持自定义 Webhook 卡片签名轮换策略？':
    'Should custom Webhook card signature rotation policies be supported next?',
  '沉浸式专注模式与实时倒计时': 'Immersive Focus Mode & Live Countdown',
  '专注模式分栏同步展示实时决议与待办卡片':
    'Focus Mode split-pane displays live decisions and action cards in sync',
  '校验 960x600 与 1200x800 视口下按钮单行排版':
    'Validate single-line button layout at 960x600 and 1200x800 viewports',
  'iCal 日历订阅与飞书/钉钉群卡片推送': 'iCal Calendar Subscription & Feishu/DingTalk Cards',
  '默认启用 RFC 5545 签名日历订阅源': 'Enable RFC 5545 signed calendar subscription feeds by default',
  '完成飞书与钉钉交互卡片回归验证': 'Complete Feishu and DingTalk interactive card regression verification',
  '分布式缓存容灾演练与网关限流压测': 'Distributed Cache DR Drill & Gateway Rate-Limit Stress Test',
  '启用 Redis Sentinel 自动主从切换方案': 'Enable Redis Sentinel Automatic Failover Plan',
  '完成网关限流压测脚本验证': 'Complete Gateway Rate-Limit Stress Test Script Verification',
  '跨机房专线延迟峰值如何兜底？': 'How to Mitigate Cross-DC Dedicated Line Latency Spikes?',
  '把聚焦模式补齐键盘快捷键与中英双语切换支持': 'Complete keyboard shortcuts and bilingual switching support for Focus Mode',
  '周会例行同步': 'Weekly Sync',
  '双周架构评审': 'Bi-weekly Architecture Review',
  '每周三 10:00 固定同步': 'Every Wednesday at 10:00',
  '确认采用页内 ✨ AI 智能提炼直接写入当前议题记录，彻底移除冗余弹窗':
    'Confirm in-place ✨ AI Smart Extract directly in agenda notes, removing redundant modals',
}

export const SEEDED_EN_TO_ZH: Record<string, string> = Object.fromEntries(
  Object.entries(SEEDED_ZH_TO_EN).map(([zh, en]) => [en, zh]),
)

const SORTED_ZH_ENTRIES = Object.entries(SEEDED_ZH_TO_EN).sort((a, b) => b[0].length - a[0].length)
const SORTED_EN_ENTRIES = Object.entries(SEEDED_EN_TO_ZH).sort((a, b) => b[0].length - a[0].length)

export function translateSeededText(text: string, lang: Locale = locale.value): string {
  if (!text) return text
  const trimmed = text.trim()
  if (lang === 'en') {
    if (SEEDED_ZH_TO_EN[trimmed]) return SEEDED_ZH_TO_EN[trimmed]
    const discussMatch = trimmed.match(/^###\s+(.+?)\s+·\s+讨论要点$/)
    if (discussMatch) {
      return `### ${translateSeededText(discussMatch[1], 'en')} · Key Discussion Points`
    }
    const decDefaultMatch = trimmed.match(/^确认「(.+?)」核心实施方案与演进路径$/)
    if (decDefaultMatch) {
      return `Confirm core implementation plan and rollout path for "${translateSeededText(decDefaultMatch[1], 'en')}"`
    }
    const actDefaultMatch = trimmed.match(/^完成「(.+?)」接口联调与自动化回归测试$/)
    if (actDefaultMatch) {
      return `Complete API integration and automated regression tests for "${translateSeededText(actDefaultMatch[1], 'en')}"`
    }
    const qDefaultMatch = trimmed.match(/^「(.+?)」存量数据迁移窗口是否需要灰度验证？$/)
    if (qDefaultMatch) {
      return `Does the legacy data migration window for "${translateSeededText(qDefaultMatch[1], 'en')}" require canary verification?`
    }
    const decFallbackMatch = trimmed.match(/^确认推进「(.+?)」方案落地$/)
    if (decFallbackMatch) {
      return `Confirm rollout plan for "${translateSeededText(decFallbackMatch[1], 'en')}"`
    }
    const actFallbackMatch = trimmed.match(/^跟进「(.+?)」后续实施与联调验证$/)
    if (actFallbackMatch) {
      return `Follow up on implementation and integration testing for "${translateSeededText(actFallbackMatch[1], 'en')}"`
    }
    const qFallbackMatch = trimmed.match(/^「(.+?)」跨模块边界细节待最终确认$/)
    if (qFallbackMatch) {
      return `Cross-module boundary details for "${translateSeededText(qFallbackMatch[1], 'en')}" pending final confirmation`
    }
    let replaced = text
    for (const [zh, en] of SORTED_ZH_ENTRIES) {
      if (zh.length >= 4 && replaced.includes(zh)) {
        replaced = replaced.split(zh).join(en)
      }
    }
    return replaced
  }

  if (SEEDED_EN_TO_ZH[trimmed]) return SEEDED_EN_TO_ZH[trimmed]
  const enDiscussMatch = trimmed.match(/^###\s+(.+?)\s+·\s+Key Discussion Points$/)
  if (enDiscussMatch) {
    return `### ${translateSeededText(enDiscussMatch[1], 'zh')} · 讨论要点`
  }
  const enDecDefaultMatch = trimmed.match(/^Confirm core implementation plan and rollout path for "(.+?)"$/)
  if (enDecDefaultMatch) {
    return `确认「${translateSeededText(enDecDefaultMatch[1], 'zh')}」核心实施方案与演进路径`
  }
  const enActDefaultMatch = trimmed.match(/^Complete API integration and automated regression tests for "(.+?)"$/)
  if (enActDefaultMatch) {
    return `完成「${translateSeededText(enActDefaultMatch[1], 'zh')}」接口联调与自动化回归测试`
  }
  const enQDefaultMatch = trimmed.match(/^Does the legacy data migration window for "(.+?)" require canary verification\?$/)
  if (enQDefaultMatch) {
    return `「${translateSeededText(enQDefaultMatch[1], 'zh')}」存量数据迁移窗口是否需要灰度验证？`
  }
  const enDecFallbackMatch = trimmed.match(/^Confirm rollout plan for "(.+?)"$/)
  if (enDecFallbackMatch) {
    return `确认推进「${translateSeededText(enDecFallbackMatch[1], 'zh')}」方案落地`
  }
  const enActFallbackMatch = trimmed.match(/^Follow up on implementation and integration testing for "(.+?)"$/)
  if (enActFallbackMatch) {
    return `跟进「${translateSeededText(enActFallbackMatch[1], 'zh')}」后续实施与联调验证`
  }
  const enQFallbackMatch = trimmed.match(/^Cross-module boundary details for "(.+?)" pending final confirmation$/)
  if (enQFallbackMatch) {
    return `「${translateSeededText(enQFallbackMatch[1], 'zh')}」跨模块边界细节待最终确认`
  }
  let replaced = text
  for (const [en, zh] of SORTED_EN_ENTRIES) {
    if (en.length >= 6 && replaced.includes(en)) {
      replaced = replaced.split(en).join(zh)
    }
  }
  return replaced
}

function normalizeActionBracketToken(token: string, lang: Locale): string {
  const lower = token.trim().toLowerCase()
  if (lang === 'en') {
    if (lower === '待办' || lower === '待开始' || lower === 'todo' || lower === 'open') return 'open'
    if (lower === '进行中' || lower === 'doing' || lower === 'progress' || lower === 'in_progress') return 'in_progress'
    if (lower === '已完成' || lower === '完成' || lower === 'done' || lower === 'completed') return 'done'
    if (lower === '已取消' || lower === '取消' || lower === 'canceled' || lower === 'cancelled') return 'canceled'
    return token
  }
  if (lower === 'open' || lower === 'todo' || lower === '待办' || lower === '待开始') return '待办'
  if (lower === 'in_progress' || lower === 'doing' || lower === 'progress' || lower === '进行中') return '进行中'
  if (lower === 'done' || lower === 'completed' || lower === '已完成' || lower === '完成') return '已完成'
  if (lower === 'canceled' || lower === 'cancelled' || lower === '已取消' || lower === '取消') return '已取消'
  return token
}

export function translateNotesMarkdown(md: string, lang: Locale = locale.value): string {
  if (!md) return md
  return md
    .split('\n')
    .map((rawLine) => {
      const trimmed = rawLine.trim().replace(/\\([[\]])/g, '$1')
      if (!trimmed) return rawLine

      const decMatch = trimmed.match(/^@(?:决策|Decision|decision):\s*(.+)$/)
      if (decMatch) {
        const prefix = lang === 'en' ? '@Decision:' : '@决策:'
        return `${prefix} ${translateSeededText(decMatch[1], lang)}`
      }

      const qMatch = trimmed.match(/^@(?:开放问题|问题|Question|question|OpenQuestion):\s*(.+)$/)
      if (qMatch) {
        const prefix = lang === 'en' ? '@Question:' : '@开放问题:'
        return `${prefix} ${translateSeededText(qMatch[1], lang)}`
      }

      const actMatch = trimmed.match(/^@(?:行动|Action|action):\s*((?:\[[^\]]+\])*)\s*(.+)$/)
      if (actMatch) {
        const prefix = lang === 'en' ? '@Action:' : '@行动:'
        const rawBrackets = actMatch[1] || ''
        const normalizedBrackets = rawBrackets.replace(/\[([^\]]+)\]/g, (_, inner: string) => {
          if (inner.startsWith('@') || /^\d{4}-\d{2}-\d{2}$/.test(inner)) {
            return `[${inner}]`
          }
          return `[${normalizeActionBracketToken(inner, lang)}]`
        })
        return `${prefix}${normalizedBrackets} ${translateSeededText(actMatch[2], lang)}`
      }

      return translateSeededText(rawLine, lang)
    })
    .join('\n')
}

export function useI18n() {
  return {
    locale,
    isEn,
    setLocale,
    toggleLocale,
    t,
    tr,
    translateSeededText,
    translateNotesMarkdown,
  }
}
