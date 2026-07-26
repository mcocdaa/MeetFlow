export type PluginJobStatus = 'queued' | 'requesting' | 'succeeded' | 'failed' | 'interrupted' | 'canceled'

export type PluginJob = {
  id: string
  plugin_id?: string
  action_id: string
  target_type: 'meeting' | 'project'
  target_id: string
  status: PluginJobStatus
  result: { markdown?: string; candidates?: Array<{ content: string }> } | null
  error_message?: string | null
  error_detail?: string | null
  applied_at: string | null
  dismissed_at?: string | null
  dismissed_by?: string | null
  created_at?: string
  started_at?: string | null
  finished_at?: string | null
}
