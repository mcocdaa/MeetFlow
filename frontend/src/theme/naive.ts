/**
 * Naive UI theme overrides and status tone mapping.
 *
 * The brand's authoritative token values live in `src/styles.css` `:root` (`--green`,
 * `--ink`, ...). Naive cannot read CSS custom properties at runtime, so this file
 * repeats the same literal values; when a brand token changes, update both places.
 * Status colors have a single source of truth here (`statusTone`/`priorityTone`).
 */

import type { GlobalThemeOverrides } from 'naive-ui'

export type StatusTone = 'success' | 'warning' | 'completed' | 'error' | 'muted'

export const naiveThemeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#0b6a58',
    primaryColorHover: '#0d7c67',
    primaryColorPressed: '#075044',
    primaryColorSuppl: '#0d7c67',
    successColor: '#2f9e68',
    warningColor: '#e9a23b',
    errorColor: '#ae3f36',
    infoColor: '#0b6a58',
    borderRadius: '8px',
    textColorBase: '#17232d',
    textColor1: '#17232d',
    textColor2: '#4a545e',
    textColor3: '#66727f',
    borderColor: '#d7dde3',
    dividerColor: '#e5e9ed',
    bodyColor: '#f1f3f5',
    cardColor: '#fbfcfd',
    modalColor: '#ffffff',
    popoverColor: '#ffffff',
    tableColor: '#ffffff',
    fontFamily:
      'Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
  },
  Button: {
    heightMedium: '40px',
    heightSmall: '34px',
    borderRadiusMedium: '8px',
    fontWeight: '700',
  },
  Tag: {
    borderRadius: '999px',
  },
  Card: {
    borderRadius: '12px',
  },
  DataTable: {
    thColor: '#f4f6f8',
    tdColor: '#ffffff',
    borderColor: '#e5e9ed',
  },
  Input: {
    borderRadius: '8px',
  },
}

const SUCCESS_STATUSES = new Set([
  'active',
  'in_progress',
  'final',
  'done',
  'resolved',
  'applied',
  'approved',
  'on_track',
  'succeeded',
])

const WARNING_STATUSES = new Set([
  'pending',
  'draft',
  'ready',
  'planned',
  'open',
  'proposed',
  'scheduled',
  'queued',
  'requesting',
  'at_risk',
  'changes_requested',
])

const COMPLETED_STATUSES = new Set(['completed', 'skipped', 'interrupted'])

const ERROR_STATUSES = new Set([
  'rejected',
  'canceled',
  'withdrawn',
  'superseded',
  'dropped',
  'failed',
  'off_track',
])

const MUTED_STATUSES = new Set(['disabled', 'archived', 'dismissed'])

const PRIORITY_TONES: Record<string, StatusTone> = {
  urgent: 'error',
  high: 'warning',
  normal: 'muted',
  low: 'completed',
}

/** Maps any entity status to a presentation tone; unknown statuses fall back to neutral. */
export function statusTone(status: string): StatusTone {
  if (SUCCESS_STATUSES.has(status)) return 'success'
  if (WARNING_STATUSES.has(status)) return 'warning'
  if (COMPLETED_STATUSES.has(status)) return 'completed'
  if (ERROR_STATUSES.has(status)) return 'error'
  if (MUTED_STATUSES.has(status)) return 'muted'
  return 'muted'
}

/** Maps an action priority to a presentation tone; unknown priorities fall back to neutral. */
export function priorityTone(priority: string): StatusTone {
  return PRIORITY_TONES[priority] ?? 'muted'
}
