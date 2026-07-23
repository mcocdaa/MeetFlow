export type Versioned = { version: number }

export type UserRef = {
  id: string
  username: string
  display_name: string
  avatar_color?: string
}

export type Page<T> = {
  items: T[]
  total: number
  limit: number
  offset: number
}

export type ApiErrorBody = {
  error: {
    code: string
    message: string
    details?: Record<string, unknown>
  }
}
