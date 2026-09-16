import { fireEvent, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AttachmentPanel from '../components/AttachmentPanel.vue'
import { renderWithProviders } from './helpers'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))

function selectFile(input: HTMLElement, file: File) {
  Object.defineProperty(input, 'files', { configurable: true, value: [file] })
  input.dispatchEvent(new Event('change', { bubbles: true }))
}

describe('meeting workflow components', () => {
  beforeEach(() => { apiMock.mockReset() })

  it('uploads a file and asks the parent to refresh attachments', async () => {
    apiMock.mockResolvedValue({ id: 'a1' })
    const uploaded = vi.fn()
    renderWithProviders(AttachmentPanel, { props: { targetId: 'm1', attachments: [], canContribute: true, onUploaded: uploaded } })
    const file = new File(['notes'], 'notes.txt', { type: 'text/plain' })
    selectFile(screen.getByLabelText('上传附件'), file)
    await waitFor(() => expect(screen.getByRole('button', { name: '上传' })).toBeEnabled())
    await fireEvent.click(screen.getByRole('button', { name: '上传' }))
    expect(apiMock).toHaveBeenCalledWith('/api/attachments/meeting/m1', expect.objectContaining({ method: 'POST', body: expect.any(FormData) }))
    expect(uploaded).toHaveBeenCalledWith(expect.objectContaining({ id: 'a1' }))
  })

  it('rejects a file over 20 MB before sending it', async () => {
    const uploaded = vi.fn()
    renderWithProviders(AttachmentPanel, { props: { targetId: 'm1', attachments: [], canContribute: true, onUploaded: uploaded } })
    const file = new File([new Uint8Array(20 * 1024 * 1024 + 1)], 'large.bin')
    selectFile(screen.getByLabelText('上传附件'), file)
    await waitFor(() => expect(screen.getByRole('button', { name: '上传' })).toBeEnabled())
    await fireEvent.click(screen.getByRole('button', { name: '上传' }))
    expect(await screen.findByText('单个附件不能超过 20 MB')).toBeInTheDocument()
    expect(apiMock).not.toHaveBeenCalled()
    expect(uploaded).not.toHaveBeenCalled()
  })

  it('does not offer deletion for a shared attachment the user cannot delete', () => {
    renderWithProviders(AttachmentPanel, {
      props: {
        targetId: 'm1',
        canContribute: true,
        attachments: [{
          id: 'a1',
          target_type: 'meeting',
          target_id: 'm1',
          original_name: 'shared.txt',
          mime_type: 'text/plain',
          size: 6,
          attachment_type: 'file',
          created_by: { id: 'u1', username: 'owner', display_name: 'Owner' },
          created_at: '',
          download_url: '/api/attachments/meeting/m1/a1',
          can_delete: false,
        }],
      },
    })

    expect(screen.queryByRole('button', { name: '删除' })).not.toBeInTheDocument()
  })

  it('deletes an attachment after confirming in the popconfirm', async () => {
    apiMock.mockResolvedValue(undefined)
    const deleted = vi.fn()
    renderWithProviders(AttachmentPanel, {
      props: {
        targetId: 'm1',
        canContribute: true,
        onDeleted: deleted,
        attachments: [{
          id: 'a1',
          target_type: 'meeting',
          target_id: 'm1',
          original_name: 'shared.txt',
          mime_type: 'text/plain',
          size: 6,
          attachment_type: 'file',
          created_by: { id: 'u1', username: 'owner', display_name: 'Owner' },
          created_at: '',
          download_url: '/api/attachments/meeting/m1/a1',
          can_delete: true,
        }],
      },
    })

    await fireEvent.click(screen.getByRole('button', { name: '删除' }))
    expect(await screen.findByText('确定删除附件“shared.txt”吗？')).toBeVisible()
    await fireEvent.click(screen.getByRole('button', { name: '确认' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/api/attachments/meeting/m1/a1', { method: 'DELETE' }))
    expect(deleted).toHaveBeenCalledWith('a1')
  })
})
