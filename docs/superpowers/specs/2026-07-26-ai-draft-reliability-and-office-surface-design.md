# AI Draft Reliability and Office Surface Design

## Goal

Make AI output behave like a reliable, local draft workflow and make the
surfaces that host it feel like a concise office application rather than a
marketing page.

## Scope

This iteration changes the AI draft lifecycle and the shared visual tokens used
by work surfaces. It does not add new AI actions, agent/tool calling, or a new
page layout.

## AI draft lifecycle

1. Submitting an AI action returns its serialized job immediately. The action
   panel emits that job to its current page.
2. The inline draft panel accepts the returned job when its target and action
   match, renders it immediately, and continues polling while it is queued or
   requesting. The user never needs a manual refresh to discover a new draft.
3. Applying a draft records the existing `applied_at` history and removes it
   from the inline pending-draft list.
4. Discarding a succeeded, unapplied draft calls a dedicated endpoint. It
   records `dismissed_at` and `dismissed_by`, so the choice survives reloads.
5. Normal target-scoped job lists return pending drafts only: neither applied
   nor dismissed jobs appear as editable suggestions. The AI task centre opts
   into history and continues to show every job with its terminal state.
6. A draft can only be dismissed after it succeeds and before it is applied.
   Invalid transitions return a conflict response without changing history.

## Data and API design

`plugin_jobs` gains nullable `dismissed_at` and `dismissed_by` fields. A new
`POST /api/plugin-jobs/{job_id}/dismiss` endpoint persists this transition.
`GET /api/plugin-jobs` gains `include_history=false`; only callers that need
task history set it to true. Serialized jobs expose dismissal fields so the
task centre can render an accurate state.

## Inline draft interaction

The draft editor remains editable in place. Its primary apply action sits in a
separate action rail below the editor, with a top divider and breathing room;
it must not visually attach to the textarea edge. Discard remains a secondary
header action. The panel does not jump the page or refresh the whole route.

## Visual direction

Use a restrained “metal office” system:

- cool silver-gray canvas and near-white work surfaces;
- hairline slate borders, 8–12 px radii, and shallow shadows;
- a very subtle cool gradient only on persistent chrome and AI/tool surfaces;
- deep green reserved for primary actions, active states, and small labels;
- slightly tighter default page, panel, and section spacing.

This is a token-and-surface pass. Dense forms, data tables, and responsive
layouts keep their existing structure. No image assets, glossy effects, or
large decorative gradients are introduced.

## Verification

Backend tests cover persisted dismissal, list filtering, and invalid state
transitions. Frontend tests cover immediate tracking after submission and
server-backed dismissal. The existing frontend suite stays below 100 tests.
The deployment check rebuilds the Docker service and verifies its health
endpoint after migrations run.
