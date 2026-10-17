const ACTIVE_JOB_STATUSES = new Set(['queued', 'requesting'])
const POLL_INTERVAL_MS = 3_000

const EN_WORKER_ERROR_MAP = {
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
}

const langSubscribers = new Set()
let observersInstalled = false

function isEn() {
  try {
    if (typeof globalThis.localStorage?.getItem === 'function') {
      const stored = globalThis.localStorage.getItem('meetflow_lang')
      if (stored === 'en') return true
      if (stored === 'zh') return false
    }
  } catch {
    // Ignore storage errors in restricted environments.
  }
  try {
    const docLang = globalThis.document?.documentElement?.lang
    if (docLang) return docLang.toLowerCase().startsWith('en')
  } catch {
    // Ignore DOM errors in restricted environments.
  }
  return false
}

function notifyLangSubscribers(eventOrRecords) {
  let en = isEn()
  if (eventOrRecords && typeof eventOrRecords === 'object' && 'detail' in eventOrRecords && eventOrRecords.detail?.lang) {
    en = eventOrRecords.detail.lang === 'en'
  } else if (Array.isArray(eventOrRecords)) {
    const docLang = globalThis.document?.documentElement?.lang
    if (docLang === 'en' || docLang === 'zh') {
      en = docLang === 'en'
    }
  }
  for (const sub of langSubscribers) {
    sub.value = en
  }
}

function ensureLangObservers() {
  if (observersInstalled) return
  observersInstalled = true
  try {
    if (typeof globalThis.addEventListener === 'function') {
      globalThis.addEventListener('meetflow:lang-change', notifyLangSubscribers)
      globalThis.addEventListener('storage', notifyLangSubscribers)
    }
    if (typeof MutationObserver !== 'undefined' && globalThis.document?.documentElement) {
      const observer = new MutationObserver(notifyLangSubscribers)
      observer.observe(globalThis.document.documentElement, {
        attributes: true,
        attributeFilter: ['lang'],
      })
    }
  } catch {
    // Ignore observer errors in restricted environments.
  }
}

function createReactiveLangGetter(vue) {
  ensureLangObservers()
  if (vue && typeof vue.ref === 'function') {
    const langSignal = vue.ref(isEn())
    langSubscribers.add(langSignal)
    return () => langSignal.value
  }
  return isEn
}

const assistantDefinitions = [
  {
    slot: 'meeting-summary-editor',
    actionId: 'ai-work-assistant.meeting_summary',
    menuTitle: 'AI 协助纪要',
    menuTitleEn: 'AI Summary Assistant',
    label: '生成会议纪要',
    labelEn: 'Generate Meeting Minutes',
    busyLabel: '正在生成会议纪要…',
    busyLabelEn: 'Generating meeting minutes…',
    targetType: 'meeting',
  },
  {
    slot: 'agenda-notes-editor',
    actionId: 'ai-work-assistant.agenda_notes',
    menuTitle: 'AI 协助议题',
    menuTitleEn: 'AI Agenda Assistant',
    label: '整理议题记录',
    labelEn: 'Organize Agenda Notes',
    busyLabel: '正在整理议题记录…',
    busyLabelEn: 'Organizing agenda notes…',
    targetType: 'agenda_item',
  },
  {
    slot: 'project-update-editor',
    actionId: 'ai-work-assistant.project_progress',
    menuTitle: 'AI 协助进展',
    menuTitleEn: 'AI Progress Assistant',
    label: '总结项目进展',
    labelEn: 'Summarize Project Progress',
    busyLabel: '正在总结项目进展…',
    busyLabelEn: 'Summarizing project progress…',
    targetType: 'project',
  },
  {
    slot: 'action-composer',
    actionId: 'ai-work-assistant.action_suggestions',
    menuTitle: 'AI 协助行动项',
    menuTitleEn: 'AI Action Assistant',
    label: '生成行动项建议',
    labelEn: 'Suggest Action Items',
    busyLabel: '正在建议行动项…',
    busyLabelEn: 'Suggesting action items…',
    targetType: 'meeting',
  },
  {
    slot: 'decision-composer',
    actionId: 'ai-work-assistant.decision_suggestions',
    menuTitle: 'AI 协助决策',
    menuTitleEn: 'AI Decision Assistant',
    label: '生成决策建议',
    labelEn: 'Suggest Decisions',
    busyLabel: '正在生成决策建议…',
    busyLabelEn: 'Suggesting decisions…',
    targetType: 'meeting',
  },
  {
    slot: 'question-composer',
    actionId: 'ai-work-assistant.open_question_suggestions',
    menuTitle: 'AI 协助问题',
    menuTitleEn: 'AI Question Assistant',
    label: '梳理开放问题',
    labelEn: 'Extract Open Questions',
    busyLabel: '正在梳理开放问题…',
    busyLabelEn: 'Extracting open questions…',
    targetType: 'meeting',
  },
]

function contextFor(props, fallbackTargetType) {
  const context = props.context && typeof props.context === 'object' ? props.context : {}
  return {
    targetType: context.targetType || context.target_type || props.targetType || fallbackTargetType,
    targetId: context.targetId || context.target_id || props.targetId || '',
    metadata: context.metadata || props.metadata || {},
  }
}

function waitForNextPoll() {
  return new Promise((resolve) => globalThis.setTimeout(resolve, POLL_INTERVAL_MS))
}

async function waitForTerminalJob(request, submittedJob) {
  let job = submittedJob
  while (ACTIVE_JOB_STATUSES.has(job.status)) {
    await waitForNextPoll()
    job = await request(`/api/plugin-jobs/${job.id}`)
  }
  return job
}

function failureMessage(jobOrError, en = isEn()) {
  let raw = ''
  if (jobOrError && typeof jobOrError === 'object' && typeof jobOrError.error_message === 'string') {
    raw = jobOrError.error_message
  } else if (jobOrError instanceof Error && jobOrError.message) {
    raw = jobOrError.message
  }
  if (raw) {
    return en ? (EN_WORKER_ERROR_MAP[raw] || raw) : raw
  }
  return en ? 'AI generation failed, please try again later' : 'AI 生成失败，请稍后重试'
}

function createAssistantComponent(pluginApi, definition) {
  const vue = pluginApi.vue || pluginApi
  const { h, ref } = vue
  const request = pluginApi.api

  return {
    props: {
      modelValue: { type: String, default: '' },
      context: { type: Object, default: () => ({}) },
      targetType: { type: String, default: '' },
      targetId: { type: String, default: '' },
      metadata: { type: Object, default: () => ({}) },
    },
    emits: ['update:modelValue', 'update:busy', 'notice'],
    setup(props, { emit }) {
      const running = ref(false)
      const reactiveIsEn = createReactiveLangGetter(vue)

      const setBusy = (active, label = '') => emit('update:busy', { active, label })
      const notice = (message) => emit('notice', message)

      async function run() {
        if (running.value) return
        running.value = true
        const enNow = reactiveIsEn()
        const busyText = enNow ? definition.busyLabelEn : definition.busyLabel
        setBusy(true, busyText)
        try {
          const context = contextFor(props, definition.targetType)
          const submittedJob = await request('/api/plugin-jobs', {
            method: 'POST',
            body: JSON.stringify({
              action_id: definition.actionId,
              target_type: context.targetType,
              target_id: context.targetId,
              input: { current_markdown: props.modelValue },
            }),
          })
          const job = await waitForTerminalJob(request, submittedJob)
          if (job.status !== 'succeeded') {
            notice(failureMessage(job, reactiveIsEn()))
            return
          }
          if (typeof job.result?.markdown !== 'string') {
            notice(reactiveIsEn() ? 'AI returned no usable result' : 'AI 未返回可用结果')
            return
          }
          emit('update:modelValue', job.result.markdown)
        } catch (error) {
          notice(failureMessage(error, reactiveIsEn()))
        } finally {
          running.value = false
          setBusy(false)
        }
      }

      return () => {
        const en = reactiveIsEn()
        return h('div', { class: 'ai-work-assistant-control' }, [
          h('div', { class: 'ai-work-assistant-menu-heading' }, [
            h('span', { class: 'ai-work-assistant-menu-title' }, en ? definition.menuTitleEn : definition.menuTitle),
            h('span', { class: 'ai-work-assistant-menu-tag' }, en ? 'Current Block' : '当前编辑块'),
          ]),
          h('button', {
            type: 'button',
            class: 'ai-work-assistant-menu-action is-primary',
            disabled: running.value,
            onClick: run,
          }, [
            h('span', running.value ? (en ? definition.busyLabelEn : definition.busyLabel) : (en ? definition.labelEn : definition.label)),
          ]),
        ])
      }
    },
  }
}

function createTaskExtension(pluginApi) {
  const vue = pluginApi.vue || pluginApi
  const { h } = vue
  return {
    props: { job: { type: Object, required: true } },
    setup(props) {
      const reactiveIsEn = createReactiveLangGetter(vue)
      // Keep the card quiet for jobs without a result (failed/queued): an empty
      // "查看 AI 结果" disclosure would only add noise next to the error message.
      return () => {
        const en = reactiveIsEn()
        return props.job.result?.markdown
          ? h('details', { class: 'ai-work-assistant-task' }, [
            h('summary', en ? 'View AI Result' : '查看 AI 结果'),
            h('pre', props.job.result.markdown),
          ])
          : null
      }
    },
  }
}

export function registerAiWorkAssistant(api) {
  assistantDefinitions.forEach((definition) => {
    api.registerEditorAssistant(definition.slot, createAssistantComponent(api, definition))
  })
  api.registerTaskExtension('ai-work-assistant', createTaskExtension(api))
}
