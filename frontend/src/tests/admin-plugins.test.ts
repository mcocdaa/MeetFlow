import { fireEvent, screen, waitFor } from '@testing-library/vue'
import { beforeEach, expect, it, vi } from 'vitest'

import AdminPluginsView from '../views/AdminPluginsView.vue'
import { renderWithProviders } from './helpers'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))

const plugin = {
  id: 'ai-summary', name: 'AI Meeting Summary', version: '0.1.0', description: '生成会议纪要草稿',
  enabled: true, effective_enabled: true, load_error: null,
  config_schema: {
    fields: [
      { key: 'base_url', type: 'string', required: true, label: 'API 地址' },
      { key: 'limit', type: 'number', required: false, label: '数量' },
      { key: 'include_done', type: 'boolean', required: false, label: '包含已完成' },
    ],
    secrets: [{ key: 'api_key', required: true, label: 'API Key' }],
  },
  config: { base_url: 'https://api.example.com', limit: 5, include_done: false, api_key: { configured: true } },
  api_version: 2, loaded: true,
  capabilities: { exporters: ['ai-summary.markdown'], event_subscriptions: [], ui_slots: ['home.secondary-card'] },
}

const failedEvent = {
  event_id: 'evt-1', event_type: 'meeting.completed', status: 'failed', attempts: 5, last_error: 'timeout',
}

beforeEach(() => {
  apiMock.mockReset()
})

it('renders manifest-driven fields and saves replacement secret values', async () => {
  apiMock.mockResolvedValueOnce({ plugins: [plugin], errors: [] }).mockResolvedValueOnce({ items: [] }).mockResolvedValueOnce(plugin).mockResolvedValueOnce({ plugins: [plugin], errors: [] }).mockResolvedValueOnce({ items: [] })
  renderWithProviders(AdminPluginsView)
  expect(await screen.findByText('AI Meeting Summary')).toBeInTheDocument()
  expect(screen.getByText('ai-summary.markdown')).toBeInTheDocument()
  expect(screen.getByText('已配置')).toBeInTheDocument()
  await fireEvent.update(screen.getByLabelText('API Key'), 'new-secret')
  await fireEvent.update(screen.getByLabelText('数量'), '10')
  await fireEvent.click(screen.getByRole('switch', { name: '包含已完成' }))
  await fireEvent.click(screen.getByRole('button', { name: '保存配置' }))
  expect(apiMock).toHaveBeenCalledWith('/api/admin/plugins/ai-summary/config', expect.objectContaining({
    method: 'PUT', body: expect.stringContaining('new-secret'),
  }))
  const configCall = apiMock.mock.calls.find(([path]) => path === '/api/admin/plugins/ai-summary/config')
  expect(JSON.parse(configCall?.[1].body)).toMatchObject({ limit: 10, include_done: true })
})

it('clears a stored secret after confirming in the popconfirm', async () => {
  apiMock
    .mockResolvedValueOnce({ plugins: [plugin], errors: [] })
    .mockResolvedValueOnce({ items: [] })
    .mockResolvedValueOnce(plugin)
    .mockResolvedValueOnce({ plugins: [plugin], errors: [] })
    .mockResolvedValueOnce({ items: [] })
  renderWithProviders(AdminPluginsView)
  await screen.findByText('已配置')

  await fireEvent.click(screen.getByRole('button', { name: '清除 API Key' }))
  expect(await screen.findByText('确定清除已保存的敏感配置吗？')).toBeVisible()
  await fireEvent.click(screen.getByRole('button', { name: '确认清除' }))

  await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/admin/plugins/ai-summary/config', {
    method: 'PUT', body: JSON.stringify({ api_key: null }),
  }))
})

it('shows discovery errors that do not have a valid plugin descriptor', async () => {
  apiMock.mockResolvedValue({ plugins: [], errors: [{ plugin_id: 'registry', error_type: 'ManifestError', message: '插件清单无效' }] })
  renderWithProviders(AdminPluginsView)
  expect(await screen.findByText(/插件清单无效/)).toBeInTheDocument()
})

it('shows that enabled state changes take effect after restart', async () => {
  apiMock.mockResolvedValueOnce({ plugins: [plugin], errors: [] }).mockResolvedValueOnce({ items: [] }).mockResolvedValueOnce(plugin).mockResolvedValueOnce({ plugins: [plugin], errors: [] }).mockResolvedValueOnce({ items: [] })
  renderWithProviders(AdminPluginsView)
  await screen.findByText('AI Meeting Summary')

  await fireEvent.click(screen.getByRole('switch', { name: '启用 AI Meeting Summary' }))

  expect(apiMock).toHaveBeenCalledWith('/api/admin/plugins/ai-summary/enabled', expect.objectContaining({ method: 'PUT' }))
  expect(screen.getByText('重启后生效')).toBeInTheDocument()
})

it('shows context scope and external network capability badges', async () => {
  const networked = {
    ...plugin,
    capabilities: { ...plugin.capabilities, context_scopes: ['project', 'meeting'], external_network: true },
  }
  apiMock.mockResolvedValueOnce({ plugins: [networked], errors: [] }).mockResolvedValueOnce({ items: [] })
  renderWithProviders(AdminPluginsView)

  expect(await screen.findByText('上下文范围：project')).toBeInTheDocument()
  expect(screen.getByText('上下文范围：meeting')).toBeInTheDocument()
  const warning = screen.getByText('可访问外部网络').closest('.n-tag')
  expect(warning).not.toBeNull()
  expect(warning).toHaveClass('capability-warning')
})

it('shows failed outbox events in a table capped at the fixed limit', async () => {
  apiMock.mockResolvedValueOnce({ plugins: [], errors: [] }).mockResolvedValueOnce({ items: [failedEvent] })
  renderWithProviders(AdminPluginsView)

  expect(await screen.findByText('meeting.completed')).toBeInTheDocument()
  expect(screen.getByText('5')).toBeInTheDocument()
  expect(screen.getByText('timeout')).toBeInTheDocument()
  expect(screen.getByText('最多显示 50 条，可用状态筛选')).toBeInTheDocument()
  expect(document.querySelector('.n-data-table')).not.toBeNull()
  expect(apiMock).toHaveBeenCalledWith('/api/admin/plugins/events?status=failed&limit=50')
})

it('keeps primary failed events visible when diagnostics refresh fails', async () => {
  apiMock
    .mockResolvedValueOnce({
      plugins: [],
      errors: [],
      events: [{ event_id: 'evt-primary', event_type: 'meeting.completed', status: 'failed', attempts: 5, last_error: 'timeout' }],
    })
    .mockRejectedValueOnce(new Error('诊断接口不可用'))

  renderWithProviders(AdminPluginsView)

  expect(await screen.findByText('meeting.completed')).toBeInTheDocument()
})

it('retries one failed event and refreshes the diagnostic list', async () => {
  let resolveRetry!: (value: unknown) => void
  const retryResponse = new Promise((resolve) => { resolveRetry = resolve })
  const retryEvent = { event_id: 'evt-retry', event_type: 'meeting.completed', status: 'failed', attempts: 5, last_error: 'timeout' }
  apiMock
    .mockResolvedValueOnce({ plugins: [], errors: [] })
    .mockResolvedValueOnce({ items: [retryEvent] })
    .mockReturnValueOnce(retryResponse)
    .mockResolvedValueOnce({ plugins: [], errors: [] })
    .mockResolvedValueOnce({ items: [] })
  renderWithProviders(AdminPluginsView)
  await screen.findByText('meeting.completed')

  await fireEvent.click(screen.getByRole('button', { name: '重试' }))
  expect(screen.getByRole('button', { name: /重试中…/ })).toBeDisabled()
  resolveRetry({ status: 'queued' })

  await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/admin/plugins/events/evt-retry/retry', { method: 'POST' }))
  await waitFor(() => expect(screen.queryByText('meeting.completed')).not.toBeInTheDocument())
})

it('keeps a failed event visible when retry fails', async () => {
  const errorEvent = { event_id: 'evt-error', event_type: 'meeting.completed', status: 'failed', attempts: 5, last_error: 'timeout' }
  apiMock
    .mockResolvedValueOnce({ plugins: [], errors: [] })
    .mockResolvedValueOnce({ items: [errorEvent] })
    .mockRejectedValueOnce(new Error('重试接口不可用'))
  renderWithProviders(AdminPluginsView)
  await screen.findByText('meeting.completed')

  await fireEvent.click(screen.getByRole('button', { name: '重试' }))

  expect(await screen.findByText('重试接口不可用')).toBeInTheDocument()
  expect(screen.getByText('meeting.completed')).toBeInTheDocument()
})
