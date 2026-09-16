import { ref } from 'vue'

import { api } from '../api/client'
import type { Project } from '../domain/projects'

/**
 * Display-name dictionary aggregated from project memberships.
 *
 * There is no user-directory endpoint, so global views resolve names from the memberships
 * embedded in `GET /api/projects`. Users who were removed from every project keep the
 * `用户·{id 前 8 位}` fallback (see spec §15, decision 2). The module-level singleton mirrors
 * the existing reactive-store pattern (`auth/session.ts`, `useInboxUnread`) instead of Pinia.
 */

export const userNames = ref<Record<string, string>>({})

/** Loads the `userId -> display_name` map; keeps the previous map when the request fails. */
export async function loadUserNames(): Promise<void> {
  let projects: Project[]
  try {
    projects = await api<Project[]>('/api/projects')
  } catch {
    return
  }

  const next: Record<string, string> = {}
  for (const project of projects ?? []) {
    for (const membership of project?.memberships ?? []) {
      const user = membership?.user
      if (!user?.id || !user.display_name) continue
      next[user.id] = user.display_name
    }
  }
  userNames.value = next
}

/** Resolves a user id to a readable name, falling back to a shortened id. */
export function nameOf(userId: string | null | undefined): string {
  if (!userId) return '未指定'
  return userNames.value[userId] ?? `用户·${userId.slice(0, 8)}`
}
