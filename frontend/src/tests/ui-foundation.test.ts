import { describe, expect, it } from 'vitest'

import { naiveThemeOverrides, priorityTone, statusTone } from '../theme/naive'

describe('naive theme', () => {
  it('maps the brand primary color from the styles.css :root token', () => {
    expect(naiveThemeOverrides.common?.primaryColor).toBe('#0b6a58')
  })

  it('maps statuses to tones', () => {
    expect(statusTone('in_progress')).toBe('success')
    expect(statusTone('proposed')).toBe('warning')
    expect(statusTone('completed')).toBe('completed')
    expect(statusTone('rejected')).toBe('error')
    expect(statusTone('disabled')).toBe('muted')
    expect(statusTone('unknown-status')).toBe('muted')
  })

  it('maps priorities to tones', () => {
    expect(priorityTone('urgent')).toBe('error')
    expect(priorityTone('high')).toBe('warning')
    expect(priorityTone('normal')).toBe('muted')
    expect(priorityTone('low')).toBe('completed')
  })
})
