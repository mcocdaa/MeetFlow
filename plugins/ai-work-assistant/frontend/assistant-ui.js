const ACTIVE_JOB_STATUSES = new Set(['queued', 'requesting'])
const POLL_INTERVAL_MS = 3_000

const assistantDefinitions = [
  {
    slot: 'meeting-summary-editor',
    actionId: 'ai-work-assistant.meeting_summary',
    menuTitle: 'AI 协助纪要',
    label: '生成会议纪要',
    busyLabel: '正在生成会议纪要…',
    targetType: 'meeting',
  },
  {
    slot: 'project-update-editor',
    actionId: 'ai-work-assistant.project_progress',
    menuTitle: 'AI 协助进展',
    label: '总结项目进展',
    busyLabel: '正在总结项目进展…',
    targetType: 'project',
  },
  {
    slot: 'action-composer',
    actionId: 'ai-work-assistant.action_suggestions',
    menuTitle: 'AI 协助行动项',
    label: '生成行动项建议',
    busyLabel: '正在建议行动项…',
    targetType: 'meeting',
  },
  {
    slot: 'decision-composer',
    actionId: 'ai-work-assistant.decision_suggestions',
    menuTitle: 'AI 协助决策',
    label: '生成决策建议',
    busyLabel: '正在生成决策建议…',
    targetType: 'meeting',
  },
  {
    slot: 'question-composer',
    actionId: 'ai-work-assistant.open_question_suggestions',
    menuTitle: 'AI 协助问题',
    label: '梳理开放问题',
    busyLabel: '正在梳理开放问题…',
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

function failureMessage(jobOrError) {
  if (jobOrError && typeof jobOrError === 'object' && typeof jobOrError.error_message === 'string') {
    return jobOrError.error_message
  }
  if (jobOrError instanceof Error && jobOrError.message) return jobOrError.message
  return 'AI 生成失败，请稍后重试'
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

      const setBusy = (active, label = '') => emit('update:busy', { active, label })
      const notice = (message) => emit('notice', message)

      async function run() {
        if (running.value) return
        running.value = true
        setBusy(true, definition.busyLabel)
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
            notice(failureMessage(job))
            return
          }
          if (typeof job.result?.markdown !== 'string') {
            notice('AI 未返回可用结果')
            return
          }
          emit('update:modelValue', job.result.markdown)
        } catch (error) {
          notice(failureMessage(error))
        } finally {
          running.value = false
          setBusy(false)
        }
      }

      return () => h('div', { class: 'ai-work-assistant-control' }, [
        h('div', { class: 'ai-work-assistant-menu-heading' }, [
          h('span', { class: 'ai-work-assistant-menu-title' }, definition.menuTitle),
          h('span', { class: 'ai-work-assistant-menu-tag' }, '当前编辑块'),
        ]),
        h('button', {
          type: 'button',
          class: 'ai-work-assistant-menu-action is-primary',
          disabled: running.value,
          onClick: run,
        }, [
          h('span', running.value ? definition.busyLabel : definition.label),
        ]),
      ])
    },
  }
}

function createTaskExtension(pluginApi) {
  const vue = pluginApi.vue || pluginApi
  const { h } = vue
  return {
    props: { job: { type: Object, required: true } },
    setup(props) {
      return () => h('details', { class: 'ai-work-assistant-task' }, [
        h('summary', '查看 AI 结果'),
        props.job.result?.markdown ? h('pre', props.job.result.markdown) : null,
      ])
    },
  }
}

export function registerAiWorkAssistant(api) {
  assistantDefinitions.forEach((definition) => {
    api.registerEditorAssistant(definition.slot, createAssistantComponent(api, definition))
  })
  api.registerTaskExtension('ai-work-assistant', createTaskExtension(api))
}
