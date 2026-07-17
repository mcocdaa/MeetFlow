import { reactive } from 'vue'

import { api } from '../api/client'

export type SessionUser = {
  id: string
  username: string
  display_name: string
  role: 'admin' | 'member'
  status: 'active'
}

export const session = reactive<{ user: SessionUser | null; loaded: boolean }>({
  user: null,
  loaded: false,
})

export async function loadSession(): Promise<void> {
  try {
    session.user = await api<SessionUser>('/api/auth/me')
  } catch {
    session.user = null
  } finally {
    session.loaded = true
  }
}

export function clearSession(): void {
  session.user = null
  session.loaded = true
}
