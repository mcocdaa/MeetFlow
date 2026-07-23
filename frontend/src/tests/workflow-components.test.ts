import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AttachmentPanel from '../components/AttachmentPanel.vue'
import PluginActionPanel from '../components/PluginActionPanel.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))

function selectFile(input: HTMLElement, file: File) {
  Object.defineProperty(input, 'files', { configurable: true, value: [file] })
  input.dispatchEvent(new Event('change', { bubbles: true }))
}

describe('meeting workflow components', () => {
  beforeEach(() => apiMock.mockReset())

  it('uploads a file and asks the parent to refresh attachments', async () => {
    apiMock.mockResolvedValue({ id: 'a1' })
    const { emitted } = render(AttachmentPanel, { props: { meetingId: 'm1', attachments: [] } })
    const file = new File(['notes'], 'notes.txt', { type: 'text/plain' })
    selectFile(screen.getByLabelText('上传附件'), file)
    await fireEvent.click(screen.getByRole('button', { name: '上传' }))
    expect(apiMock).toHaveBeenCalledWith('/api/attachments/meeting/m1', expect.objectContaining({ method: 'POST', body: expect.any(FormData) }))
    expect(emitted().changed).toHaveLength(1)
  })

  it('rejects a file over 20 MB before sending it', async () => {
    const { emitted } = render(AttachmentPanel, { props: { meetingId: 'm1', attachments: [] } })
    const file = new File([new Uint8Array(20 * 1024 * 1024 + 1)], 'large.bin')
    selectFile(screen.getByLabelText('上传附件'), file)
    await fireEvent.click(screen.getByRole('button', { name: '上传' }))
    expect(await screen.findByText('单个附件不能超过 20 MB')).toBeInTheDocument()
    expect(apiMock).not.toHaveBeenCalled()
    expect(emitted().changed).toBeUndefined()
  })

  it('runs a plugin action and exposes an editable draft without auto-saving', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/plugins/actions') return Promise.resolve([{ action_id: 'test-ai.summarize', label: '生成会议纪要', description: '生成可编辑草稿', input_schema: { type: 'object' } }])
      return Promise.resolve({ markdown: '# Draft summary', suggested_patch: { conclusions_markdown: 'Draft conclusion' } })
    })
    render(PluginActionPanel, { props: { meetingId: 'm1' } })
    await fireEvent.click(await screen.findByRole('button', { name: '生成会议纪要' }))
    expect(await screen.findByDisplayValue('# Draft summary')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith('/api/meetings/m1/plugin-actions/test-ai.summarize', {
      method: 'POST', body: '{}',
    })
    expect(apiMock).not.toHaveBeenCalledWith('/api/meetings/m1', expect.objectContaining({ method: 'PUT' }))
  })

  it('emits the edited plugin patch only after confirmation', async () => {
    apiMock.mockImplementation((path: string) => path === '/api/plugins/actions'
      ? Promise.resolve([{ action_id: 'test-ai.summarize', label: '生成会议纪要', description: '', input_schema: {} }])
      : Promise.resolve({ markdown: 'draft', suggested_patch: { conclusions_markdown: 'old' } }))
    const { emitted } = render(PluginActionPanel, { props: { meetingId: 'm1' } })
    await fireEvent.click(await screen.findByRole('button', { name: '生成会议纪要' }))
    await fireEvent.update(await screen.findByLabelText('建议关键结论'), 'edited')
    await fireEvent.click(screen.getByRole('button', { name: '应用到会议草稿' }))
    await waitFor(() => expect(emitted()).toHaveProperty('apply.0.0', { conclusions_markdown: 'edited' }))
  })

  it('builds typed, action-scoped inputs from JSON Schema', async () => {
    apiMock.mockImplementation((path: string) => path === '/api/plugins/actions'
      ? Promise.resolve([{
          action_id: 'tools.export', label: '导出', description: '',
          input_schema: { type: 'object', required: ['limit'], properties: {
            limit: { type: 'number', title: '数量' },
            include_done: { type: 'boolean', title: '包含已完成' },
            format: { type: 'string', title: '格式', enum: ['md', 'json'] },
          } },
        }])
      : Promise.resolve({ markdown: 'done' }))
    render(PluginActionPanel, { props: { meetingId: 'm1' } })
    await screen.findByRole('button', { name: '导出' })
    await fireEvent.update(screen.getByLabelText('数量'), '12')
    await fireEvent.click(screen.getByRole('checkbox', { name: '包含已完成' }))
    await fireEvent.update(screen.getByLabelText('格式'), 'json')
    await fireEvent.click(screen.getByRole('button', { name: '导出' }))
    expect(apiMock).toHaveBeenCalledWith('/api/meetings/m1/plugin-actions/tools.export', {
      method: 'POST', body: JSON.stringify({ limit: 12, include_done: true, format: 'json' }),
    })
  })

  it('omits blank optional plugin inputs instead of sending invalid empty strings', async () => {
    apiMock.mockImplementation((path: string) => path === '/api/plugins/actions'
      ? Promise.resolve([{
          action_id: 'tools.preview', label: '预览', description: '',
          input_schema: { type: 'object', properties: { limit: { type: 'integer', title: '可选数量' } } },
        }])
      : Promise.resolve({ markdown: 'preview' }))
    render(PluginActionPanel, { props: { meetingId: 'm1' } })
    await fireEvent.click(await screen.findByRole('button', { name: '预览' }))
    expect(apiMock).toHaveBeenCalledWith('/api/meetings/m1/plugin-actions/tools.preview', {
      method: 'POST', body: '{}',
    })
  })

  it('blocks a plugin action when a required input is blank', async () => {
    apiMock.mockResolvedValue([{
      action_id: 'tools.send', label: '发送', description: '',
      input_schema: { type: 'object', required: ['channel'], properties: { channel: { type: 'string', title: '频道' } } },
    }])
    render(PluginActionPanel, { props: { meetingId: 'm1' } })
    await fireEvent.click(await screen.findByRole('button', { name: '发送' }))
    expect(await screen.findByText('请填写频道')).toBeInTheDocument()
    expect(apiMock).not.toHaveBeenCalledWith('/api/meetings/m1/plugin-actions/tools.send', expect.anything())
  })
})
