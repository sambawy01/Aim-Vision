/**
 * Conflict resolution policy for the sync engine.
 *
 * Three classes of records that need different policies:
 *
 * 1. Athlete-owned mutable (sessions metadata, shot annotations)
 *    -> last-write-wins (LWW) by updated_at. Field-level merge optional.
 *
 * 2. Immutable append-only (shots, shot_events, recordings)
 *    -> first-write-wins on server_id; later writes ignored. ADR-0006 says
 *       the Shot itself is immutable, every diagnostic update is a new
 *       ShotEvent. We do not silently overwrite an event payload.
 *
 * 3. Server-authoritative (consent_records, tenancy.*)
 *    -> server always wins. Local copy is read-cache. Sprint 17 WithdrawalRequest
 *       will flip consent into a CRDT but we are not building that here.
 *
 * Sprint 5 EPIC 5.2 deliverable. Pure functions so the policy is unit-testable
 * without a live database.
 */

import { TABLES } from './schema';

export type ResolutionKind = 'use_local' | 'use_server' | 'merge_fields' | 'skip';

export interface ConflictResolution {
  kind: ResolutionKind;
  /** Field-level merge result when kind === 'merge_fields'. Sparse — only
   *  the columns whose value should change. */
  patch?: Record<string, unknown>;
  /** Operator log entry. Persisted to the audit table so we have a record
   *  of every conflict the engine resolved. */
  reason: string;
}

const APPEND_ONLY_TABLES = new Set(['shots', 'shot_events', 'recordings']);
const SERVER_AUTHORITATIVE_TABLES = new Set(['consent_records']);

export interface ConflictInput {
  tableName: string;
  /** The local row, including server_id if it was previously synced. */
  local: Record<string, unknown> & { updated_at: number; server_id?: string };
  /** The server-authoritative row, as returned by a pull. */
  server: Record<string, unknown> & { updated_at: number; server_id: string };
  /** Fields the local side has modified since the last successful push.
   *  Drives field-level LWW for athlete-owned mutables. */
  locallyChanged: ReadonlySet<string>;
}

/**
 * Resolve a conflict between a local row and a server row. Both must
 * reference the same `server_id`. The caller is responsible for matching
 * them up; this function only decides the merge policy.
 */
export function resolveConflict(input: ConflictInput): ConflictResolution {
  const { tableName, local, server, locallyChanged } = input;

  if (!TABLES.some((t) => t.name === tableName)) {
    return {
      kind: 'skip',
      reason: `unknown table "${tableName}" — refusing to merge`,
    };
  }

  if (SERVER_AUTHORITATIVE_TABLES.has(tableName)) {
    return {
      kind: 'use_server',
      reason: `${tableName} is server-authoritative`,
    };
  }

  if (APPEND_ONLY_TABLES.has(tableName)) {
    if (local.server_id && local.server_id === server.server_id) {
      return {
        kind: 'use_server',
        reason: `${tableName} is append-only; server row wins on collision`,
      };
    }
    return {
      kind: 'skip',
      reason: `${tableName} append-only with no matching server_id — keep local for next push`,
    };
  }

  // Athlete-owned mutable: field-level LWW.
  if (locallyChanged.size === 0) {
    return {
      kind: 'use_server',
      reason: 'no local changes — adopt server copy',
    };
  }

  if (local.updated_at <= server.updated_at) {
    // Server has a strictly newer or equal write. We still want to keep our
    // local edits on columns the server has not touched between our last
    // pull and this conflict. Without per-column timestamps from the server
    // we conservatively only preserve `_status === 'updated'` columns that
    // the local side claims dirty.
    const patch: Record<string, unknown> = { ...server };
    for (const col of locallyChanged) {
      patch[col] = local[col];
    }
    return {
      kind: 'merge_fields',
      patch,
      reason: `LWW server-newer, preserving ${locallyChanged.size} locally-dirty column(s)`,
    };
  }

  return {
    kind: 'use_local',
    reason: 'LWW local-newer',
  };
}

/** Set difference helper used by callers building the `locallyChanged`
 *  argument from the WatermelonDB `_changed` CSV column. */
export function parseChangedCols(changedCsv: string | null | undefined): Set<string> {
  if (!changedCsv) return new Set();
  return new Set(
    changedCsv
      .split(',')
      .map((c) => c.trim())
      .filter(Boolean),
  );
}
