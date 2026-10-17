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

export function useI18n() {
  return {
    locale,
    isEn,
    setLocale,
    toggleLocale,
    t,
    tr,
  }
}
