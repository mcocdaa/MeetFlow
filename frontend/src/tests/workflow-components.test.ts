import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AttachmentPanel from '../components/AttachmentPanel.vue'

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

})
