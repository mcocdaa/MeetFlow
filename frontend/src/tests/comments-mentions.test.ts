import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import MentionTextarea from '../components/MentionTextarea.vue'

const participants = [
  { user: { id: 'u1', username: 'lin', display_name: '林宇' }, participation_role: 'host', position: 0 },
  { user: { id: 'u2', username: 'wangmin', display_name: '王敏' }, participation_role: 'attendee', position: 1 },
]

describe('meeting mentions', () => {
  it('filters participants after @ and inserts the selected mention', async () => {
    const { emitted } = render(MentionTextarea, { props: { modelValue: '', participants, label: '评论内容' } })
    const input = screen.getByRole('combobox', { name: '评论内容' })
    await fireEvent.update(input, '@王')
    expect(screen.getByRole('listbox', { name: '会议参与者' })).toBeInTheDocument()
    await fireEvent.keyDown(input, { key: 'Enter' })
    const values = emitted()['update:modelValue'] ?? []
    const mentions = emitted()['update:mentionIds'] ?? []
    expect(values[values.length - 1]).toEqual(['@王敏 '])
    expect(mentions[mentions.length - 1]).toEqual([['u2']])
  })
})
