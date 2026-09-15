import { ref, type Ref } from 'vue'

import { ApiError } from '../api/client'

/**
 * Shared optimistic-concurrency primitive for entities saved with `expected_version`.
 *
 * Only `version_conflict` 409 responses enter `conflict`; every other failure lands in `error`
 * so views can render it inline. `status === 409` is checked explicitly because the backend also
 * uses 409 for other codes (for example `derived_outcome_read_only`).
 */

export type VersionConflict = { actualVersion: number; error: unknown }

export function useVersionedSave<T>(
  save: (version: number) => Promise<T>,
  getVersion: () => number,
): {
  conflict: Ref<VersionConflict | null>
  saving: Ref<boolean>
  error: Ref<string>
  submit: () => Promise<T | null>
  retryWith: (actualVersion: number) => Promise<T | null>
  reset: () => void
} {
  const conflict = ref<VersionConflict | null>(null)
  const saving = ref(false)
  const error = ref('')

  async function run(version: number): Promise<T | null> {
    saving.value = true
    error.value = ''
    try {
      const result = await save(version)
      conflict.value = null
      return result
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409 && reason.code === 'version_conflict') {
        conflict.value = {
          actualVersion: Number(reason.details?.actual_version ?? getVersion()),
          error: reason,
        }
        return null
      }
      error.value = reason instanceof Error ? reason.message : String(reason)
      return null
    } finally {
      saving.value = false
    }
  }

  return {
    conflict,
    saving,
    error,
    submit: () => run(getVersion()),
    retryWith: (actualVersion: number) => run(actualVersion),
    reset: () => {
      conflict.value = null
      error.value = ''
    },
  }
}
