export type WorkspaceCapability = 'manage' | 'contribute' | 'comment' | 'view'

type CapabilitySource = {
  capabilities?: Partial<Record<`can_${WorkspaceCapability}`, boolean>>
} | null | undefined

/**
 * Single entry point for permission-driven rendering. Reads only the server-provided
 * `capabilities` object; never derives capabilities from `session.user.role`. A missing
 * capability field means "not allowed".
 *
 * `view` maps to `can_view`, which current project/meeting payloads do not expose
 * (backend keeps it internal); it is reserved for future server-provided sources.
 */
export function can(source: CapabilitySource, capability: WorkspaceCapability): boolean {
  return source?.capabilities?.[`can_${capability}`] === true
}
