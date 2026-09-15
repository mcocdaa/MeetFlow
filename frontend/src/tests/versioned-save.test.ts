import { fireEvent, screen } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'

import { ApiError } from '../api/client'
import VersionConflictDialog from '../components/VersionConflictDialog.vue'
import { useVersionedSave } from '../composables/useVersionedSave'
import { renderWithProviders } from './helpers'

describe('useVersionedSave', () => {
  it('captures a 409 version conflict and retries with the server version', async () => {
    const save = vi.fn()
      .mockRejectedValueOnce(new ApiError(409, 'version_conflict', '内容已更新', { actual_version: 4 }))
      .mockResolvedValueOnce('server-ack')
    const store = useVersionedSave(save, () => 3)

    await store.submit()

    expect(save).toHaveBeenCalledWith(3)
    expect(store.conflict.value).toMatchObject({ actualVersion: 4 })
    expect(store.error.value).toBe('')

    await store.retryWith(4)

    expect(save).toHaveBeenLastCalledWith(4)
    expect(store.conflict.value).toBeNull()
  })

  it('falls back to the tracked version when the conflict carries no details', async () => {
    const save = vi.fn().mockRejectedValue(new ApiError(409, 'version_conflict', '内容已更新'))
    const store = useVersionedSave(save, () => 7)

    await store.submit()

    expect(store.conflict.value).toMatchObject({ actualVersion: 7 })
  })

  it('keeps non-conflict errors out of the conflict state', async () => {
    const save = vi.fn().mockRejectedValue(new ApiError(500, 'server_error', '服务器错误'))
    const store = useVersionedSave(save, () => 1)

    await store.submit()

    expect(store.conflict.value).toBeNull()
    expect(store.error.value).toBe('服务器错误')
  })

  it('resets the conflict and error state', async () => {
    const save = vi.fn().mockRejectedValue(new ApiError(500, 'server_error', '服务器错误'))
    const store = useVersionedSave(save, () => 1)

    await store.submit()
    store.reset()

    expect(store.conflict.value).toBeNull()
    expect(store.error.value).toBe('')
  })

  it('tracks the saving state while the callback is in flight', async () => {
    let resolveSave: ((value: string) => void) | undefined
    const save = vi.fn(() => new Promise<string>((resolve) => { resolveSave = resolve }))
    const store = useVersionedSave(save, () => 2)

    const pending = store.submit()
    expect(store.saving.value).toBe(true)
    resolveSave?.('ok')
    await pending
    expect(store.saving.value).toBe(false)
  })
})

describe('VersionConflictDialog', () => {
  it('shows both drafts and emits the chosen recovery action', async () => {
    // `renderWithProviders` mounts the providers as the root component, so `emitted()` would
    // record the wrapper instead of the dialog; listener props assert the same contract.
    const onClose = vi.fn()
    const onReload = vi.fn()
    const onOverwrite = vi.fn()
    renderWithProviders(VersionConflictDialog, {
      props: {
        localMarkdown: '本地草稿内容',
        serverMarkdown: '服务器版本内容',
        actualVersion: 4,
        onClose,
        onReload,
        onOverwrite,
      },
    })

    await screen.findByText('内容已被其他成员更新')
    expect(screen.getByText('本地草稿')).toBeInTheDocument()
    expect(screen.getByText('服务器版本')).toBeInTheDocument()

    await fireEvent.click(screen.getByRole('button', { name: '复制本地草稿' }))
    await fireEvent.click(screen.getByRole('button', { name: '载入服务器版本' }))
    await fireEvent.click(screen.getByRole('button', { name: '用本地草稿覆盖' }))
    await fireEvent.click(screen.getByRole('button', { name: '关闭' }))

    expect(onReload).toHaveBeenCalledTimes(1)
    expect(onOverwrite).toHaveBeenCalledWith(4)
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
