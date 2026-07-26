const ACTIVE_JOB_STATUSES = new Set(['queued', 'requesting'])
const POLL_INTERVAL_MS = 3_000

const assistantDefinitions = [
  {
    slot: 'meeting-summary-editor',
    actionId: 'ai-work-assistant.meeting_summary',
    label: '生成会议纪要',
    busyLabel: '正在生成会议纪要…',
    targetType: 'meeting',
  },
  {
    slot: 'project-update-editor',
    actionId: 'ai-work-assistant.project_progress',
    label: '总结项目进展',
    busyLabel: '正在总结项目进展…',
    targetType: 'project',
  },
  {
    slot: 'action-composer',
    actionId: 'ai-work-assistant.action_suggestions',
    label: '建议行动项',
    busyLabel: '正在建议行动项…',
    targetType: 'meeting',
    createsActions: true,
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

function actionEndpoint(context) {
  const projectId = context.metadata.projectId || context.metadata.project_id
  return projectId ? `/api/projects/${projectId}/actions` : ''
}

function createAssistantComponent(pluginApi, definition) {
  const vue = pluginApi.vue || pluginApi
  const { h, ref, onUnmounted } = vue
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
      const candidates = ref([])
      const beforeGeneration = ref(null)

      const setBusy = (active, label = '') => emit('update:busy', { active, label })
      const notice = (message) => emit('notice', message)

      async function run() {
        if (running.value) return
        running.value = true
        beforeGeneration.value = props.modelValue
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
          if (definition.createsActions) {
            candidates.value = (job.result?.candidates || [])
              .filter((candidate) => typeof candidate?.content === 'string' && candidate.content.trim())
              .map((candidate) => ({ content: candidate.content, selected: true }))
            return
          }
          if (typeof job.result?.markdown !== 'string') {
            notice('AI 未返回可用草稿')
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

      function restoreBeforeGeneration(event) {
        if (!definition.createsActions || !candidates.value.length || beforeGeneration.value === null) return
        if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'z') return
        event.preventDefault()
        emit('update:modelValue', beforeGeneration.value)
        candidates.value = []
        beforeGeneration.value = null
      }

      function updateCandidate(index, content) {
        candidates.value[index] = { ...candidates.value[index], content }
      }

      function selectCandidate(index, selected) {
        candidates.value[index] = { ...candidates.value[index], selected }
      }

      async function createSelectedActions() {
        const context = contextFor(props, definition.targetType)
        const endpoint = actionEndpoint(context)
        const selected = candidates.value.filter((candidate) => candidate.selected && candidate.content.trim())
        if (!endpoint || !selected.length) {
          notice('缺少可创建行动项所需的项目信息')
          return
        }
        try {
          for (const candidate of selected) {
            await request(endpoint, {
              method: 'POST',
              body: JSON.stringify({
                project_id: context.metadata.projectId || context.metadata.project_id,
                meeting_id: context.metadata.meetingId || context.metadata.meeting_id || context.targetId,
                agenda_item_id: context.metadata.agendaId || context.metadata.agenda_id || null,
                content: candidate.content.trim(),
                owner_user_id: null,
                due_date: null,
                priority: 'normal',
              }),
            })
          }
          candidates.value = candidates.value.filter((candidate) => !candidate.selected)
        } catch (error) {
          notice(failureMessage(error))
        }
      }

      if (onUnmounted) onUnmounted(() => { candidates.value = [] })

      return () => {
        const controls = [
          h('button', {
            type: 'button',
            class: 'button button-quiet',
            disabled: running.value,
            onClick: run,
          }, running.value ? definition.busyLabel : definition.label),
        ]
        if (definition.createsActions && candidates.value.length) {
          controls.push(h('section', {
            class: 'ai-work-assistant-candidates',
            tabindex: -1,
            onKeydown: restoreBeforeGeneration,
          }, [
            h('p', 'AI 建议行动项（尚未创建）'),
            ...candidates.value.map((candidate, index) => h('label', { key: `${index}-${candidate.content}` }, [
              h('input', {
                type: 'checkbox',
                checked: candidate.selected,
                onChange: (event) => selectCandidate(index, event.target.checked),
              }),
              h('input', {
                value: candidate.content,
                'aria-label': `行动项建议 ${index + 1}`,
                onInput: (event) => updateCandidate(index, event.target.value),
              }),
            ])),
            h('button', {
              type: 'button',
              class: 'button button-primary',
              onClick: createSelectedActions,
            }, `创建所选行动项 (${candidates.value.filter((candidate) => candidate.selected).length})`),
          ]))
        }
        return h('div', { class: 'ai-work-assistant-control' }, controls)
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
      return () => h('details', { class: 'ai-work-assistant-task' }, [
        h('summary', '查看 AI 草稿'),
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
