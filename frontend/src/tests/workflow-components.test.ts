import { fireEvent, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AttachmentPanel from '../components/AttachmentPanel.vue'
import ProjectRecordTabs from '../components/ProjectRecordTabs.vue'
import { renderWithProviders } from './helpers'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))
vi.mock('vue-router', () => ({
  RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
}))

const lin = { id: 'u1', username: 'lin', display_name: '林宇' }
const qiao = { id: 'u2', username: 'qiao', display_name: '乔一' }

const project = {
  id: 'p1', name: 'MeetFlow', slug: 'meetflow', summary: '', description_markdown: '', status: 'active', health: 'on_track',
  lead: lin, target_date: null, version: 3,
  memberships: [
    { role: 'member', user: lin },
    { role: 'stakeholder', user: qiao },
  ],
  capabilities: { can_manage: true, can_contribute: true, can_comment: true },
  updates: [], next_meeting: null, recent_decisions: [], meeting_count: 0, decision_count: 0, open_action_count: 0,
  series_summaries: [], attachments: [], created_by: lin, updated_by: lin, created_at: '', updated_at: '',
} as any

const actionRows = [
  { id: 'a1', content: '确认范围', status: 'open', priority: 'high', owner_user_id: 'u1', due_date: '2026-07-25', meeting_id: 'm1', version: 3, is_derived: false, completed_at: null },
  { id: 'a2', content: '整理纪要', status: 'in_progress', priority: 'normal', owner_user_id: null, due_date: null, meeting_id: null, version: 2, is_derived: false, completed_at: null },
  { id: 'a3', content: '自动跟进', status: 'open', priority: 'normal', owner_user_id: null, due_date: null, meeting_id: null, version: 1, is_derived: true, completed_at: null },
  { id: 'a4', content: '已完成事项', status: 'done', priority: 'low', owner_user_id: 'u2', due_date: null, meeting_id: null, version: 4, is_derived: false, completed_at: '2026-07-20T08:00:00Z' },
]

function renderActionRows(actions: unknown[], canContribute = true) {
  apiMock.mockImplementation((path: string, init?: RequestInit) => {
    if (path.startsWith('/api/actions/') && init?.method === 'PUT') return Promise.resolve({ id: path.split('/').pop() })
    if (path.startsWith('/api/actions?')) return Promise.resolve({ items: actions, total: actions.length })
    return Promise.resolve({})
  })
  return renderWithProviders(ProjectRecordTabs, { props: { project, tab: 'actions', canContribute } })
}

function actionPut(itemId: string, calls = apiMock.mock.calls) {
  return calls.find(([path, init]) => (
    path === `/api/actions/${itemId}` && (init as RequestInit | undefined)?.method === 'PUT'
  ))
}

async function selectOption(selectSelector: string, label: string) {
  await fireEvent.click(document.querySelector(`${selectSelector} .n-base-selection`)!)
  const option = await waitFor(() => {
    const candidate = [...document.querySelectorAll('.n-base-select-option__content')]
      .find((item) => item.textContent === label)
    if (!candidate) throw new Error(`option ${label} is not open yet`)
    return candidate
  })
  await fireEvent.click(option)
}

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

describe('project action rows', () => {
  beforeEach(() => { apiMock.mockReset() })

  it('edits an action through its row drawer', async () => {
    renderActionRows([actionRows[0]])

    await fireEvent.click(await screen.findByRole('button', { name: '编辑行动项“确认范围”' }))
    expect(await screen.findByRole('heading', { name: '编辑行动项' })).toBeInTheDocument()
    await fireEvent.update(screen.getByLabelText('行动项内容'), '确认范围（更新）')
    await selectOption('.action-edit-owner', '乔一')
    await fireEvent.update(screen.getByLabelText('截止日期'), '2026-08-09')
    await selectOption('.action-edit-status', '已完成')
    await fireEvent.click(screen.getByRole('button', { name: '保存行动项' }))

    await waitFor(() => expect(actionPut('a1')).toBeTruthy())
    expect(JSON.parse(String((actionPut('a1')![1] as RequestInit).body))).toEqual({
      content: '确认范围（更新）',
      owner_user_id: 'u2',
      due_date: '2026-08-09',
      priority: 'high',
      status: 'done',
      expected_version: 3,
    })
  })

  it('runs quick status transitions with the action version', async () => {
    renderActionRows([actionRows[0], actionRows[1]])

    await fireEvent.click(await screen.findByRole('button', { name: '开始行动项“确认范围”' }))
    await waitFor(() => expect(actionPut('a1')).toBeTruthy())
    expect(JSON.parse(String((actionPut('a1')![1] as RequestInit).body))).toEqual({
      status: 'in_progress',
      expected_version: 3,
    })

    await fireEvent.click(screen.getByRole('button', { name: '完成行动项“整理纪要”' }))
    await waitFor(() => expect(actionPut('a2')).toBeTruthy())
    expect(JSON.parse(String((actionPut('a2')![1] as RequestInit).body))).toEqual({
      status: 'done',
      expected_version: 2,
    })

    await fireEvent.click(screen.getByRole('button', { name: '取消行动项“确认范围”' }))
    expect(await screen.findByText('确定取消行动项“确认范围”吗？')).toBeInTheDocument()
    await fireEvent.click(screen.getByRole('button', { name: '确认' }))
    await waitFor(() => {
      const canceled = apiMock.mock.calls.some(([path, init]) => (
        path === '/api/actions/a1'
        && (init as RequestInit | undefined)?.method === 'PUT'
        && JSON.parse(String((init as RequestInit).body)).status === 'canceled'
      ))
      expect(canceled).toBe(true)
    })
  })

  it('keeps derived actions read-only', async () => {
    renderActionRows([actionRows[2]])

    expect(await screen.findByText('自动跟进')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '编辑行动项“自动跟进”' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '开始行动项“自动跟进”' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '取消行动项“自动跟进”' })).not.toBeInTheDocument()
  })

  it('shows completed_at for completed actions and hides write entries when read-only', async () => {
    renderActionRows([actionRows[3]], false)

    expect(await screen.findByText('已完成事项')).toBeInTheDocument()
    expect(screen.getByText(/完成于/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '编辑行动项“已完成事项”' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '取消行动项“已完成事项”' })).not.toBeInTheDocument()
  })
})
