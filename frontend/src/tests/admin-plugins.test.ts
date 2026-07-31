import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeEach, expect, it, vi } from 'vitest'

import AdminPluginsView from '../views/AdminPluginsView.vue'

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

beforeEach(() => apiMock.mockReset())

it('renders manifest-driven fields and saves replacement secret values', async () => {
  apiMock.mockResolvedValueOnce({ plugins: [plugin], errors: [] }).mockResolvedValueOnce({ items: [] }).mockResolvedValueOnce(plugin).mockResolvedValueOnce({ plugins: [plugin], errors: [] }).mockResolvedValueOnce({ items: [] })
  render(AdminPluginsView)
  expect(await screen.findByText('AI Meeting Summary')).toBeInTheDocument()
  expect(screen.getByText('ai-summary.markdown')).toBeInTheDocument()
  expect(screen.getByText('已配置')).toBeInTheDocument()
  await fireEvent.update(screen.getByLabelText('API Key'), 'new-secret')
  await fireEvent.update(screen.getByLabelText('数量'), '10')
  await fireEvent.click(screen.getByRole('checkbox', { name: '包含已完成' }))
  await fireEvent.click(screen.getByRole('button', { name: '保存配置' }))
  expect(apiMock).toHaveBeenCalledWith('/api/admin/plugins/ai-summary/config', expect.objectContaining({
    method: 'PUT', body: expect.stringContaining('new-secret'),
  }))
  const configCall = apiMock.mock.calls.find(([path]) => path === '/api/admin/plugins/ai-summary/config')
  expect(JSON.parse(configCall?.[1].body)).toMatchObject({ limit: 10, include_done: true })
})

it('shows discovery errors that do not have a valid plugin descriptor', async () => {
  apiMock.mockResolvedValue({ plugins: [], errors: [{ plugin_id: 'registry', error_type: 'ManifestError', message: '插件清单无效' }] })
  render(AdminPluginsView)
  expect(await screen.findByText(/插件清单无效/)).toBeInTheDocument()
})

it('shows that enabled state changes take effect after restart', async () => {
  apiMock.mockResolvedValueOnce({ plugins: [plugin], errors: [] }).mockResolvedValueOnce({ items: [] }).mockResolvedValueOnce(plugin).mockResolvedValueOnce({ plugins: [plugin], errors: [] }).mockResolvedValueOnce({ items: [] })
  render(AdminPluginsView)
  await screen.findByText('AI Meeting Summary')
  await fireEvent.click(screen.getByRole('checkbox', { name: '启用 AI Meeting Summary' }))
  expect(apiMock).toHaveBeenCalledWith('/api/admin/plugins/ai-summary/enabled', expect.objectContaining({ method: 'PUT' }))
  expect(screen.getByText('重启后生效')).toBeInTheDocument()
})

it('shows failed outbox events without exposing event payloads', async () => {
  apiMock.mockResolvedValueOnce({ plugins: [], errors: [] }).mockResolvedValueOnce({
    items: [{ event_id: 'evt-1', event_type: 'meeting.completed', status: 'failed', attempts: 5, last_error: 'timeout' }],
  })
  render(AdminPluginsView)
  expect(await screen.findByText(/meeting\.completed · 已重试 5 次/)).toBeInTheDocument()
  expect(screen.getByText(/timeout/)).toBeInTheDocument()
})
