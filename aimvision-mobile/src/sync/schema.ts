/**
 * Local-side schema for the mobile WatermelonDB store.
 *
 * Mirrors the backend SQLAlchemy schema in `aimvision-backend/app/models/`
 * but only the tables a phone actually needs offline: a session in progress,
 * its shots/recordings/events, and the consent records that gate them.
 * Tenancy + audit tables stay server-side.
 *
 * Two fields are mobile-specific and have no backend counterpart:
 *   - `_status`: per-row sync status driving the engine state machine.
 *   - `_changed`: comma-separated list of columns dirty since the last push.
 *
 * Sprint 5 EPIC 5.2 deliverable per V2 plan. Pure TypeScript so the schema
 * is testable without booting the native WatermelonDB runtime; the
 * native bindings load lazily in `database.ts` (TODO, gated on RN 0.76
 * Hermes compatibility verification).
 */

export type ColumnType = 'string' | 'number' | 'boolean' | 'json';

export interface ColumnSpec {
  name: string;
  type: ColumnType;
  isOptional?: boolean;
  /** True for columns indexed for query performance. WatermelonDB SQLite
   * indexes are cheap; default-true for foreign keys + tenant_id. */
  isIndexed?: boolean;
}

export interface TableSpec {
  name: string;
  columns: ColumnSpec[];
}

/** Sync status for a row, drives the push/pull state machine.
 *  - `synced`: server confirmed last write
 *  - `created`: locally new, awaiting first push
 *  - `updated`: server has older copy, push pending
 *  - `deleted`: tombstoned locally, awaiting server confirmation
 */
export type RowStatus = 'synced' | 'created' | 'updated' | 'deleted';

const tenantScoped: ColumnSpec[] = [
  { name: 'tenant_id', type: 'string', isIndexed: true },
  { name: '_status', type: 'string', isIndexed: true },
  { name: '_changed', type: 'string', isOptional: true },
  { name: 'created_at', type: 'number' },
  { name: 'updated_at', type: 'number' },
];

export const SCHEMA_VERSION = 1;

export const TABLES: readonly TableSpec[] = [
  {
    name: 'sessions',
    columns: [
      { name: 'server_id', type: 'string', isOptional: true, isIndexed: true },
      { name: 'org_id', type: 'string', isIndexed: true },
      { name: 'athlete_user_id', type: 'string', isIndexed: true },
      { name: 'discipline', type: 'string' },
      { name: 'started_at', type: 'number' },
      { name: 'ended_at', type: 'number', isOptional: true },
      ...tenantScoped,
    ],
  },
  {
    name: 'recordings',
    columns: [
      { name: 'server_id', type: 'string', isOptional: true, isIndexed: true },
      { name: 'session_id', type: 'string', isIndexed: true },
      { name: 'storage_uri', type: 'string' },
      { name: 'sha256', type: 'string', isOptional: true },
      { name: 'duration_ms', type: 'number', isOptional: true },
      { name: 'upload_state', type: 'string' },
      { name: 'camera_clock_offset_ms', type: 'number', isOptional: true },
      ...tenantScoped,
    ],
  },
  {
    name: 'shots',
    columns: [
      { name: 'server_id', type: 'string', isOptional: true, isIndexed: true },
      { name: 'session_id', type: 'string', isIndexed: true },
      { name: 'monotonic_seq', type: 'number' },
      { name: 'device_clock_ns', type: 'number' },
      { name: 'server_clock_ns', type: 'number' },
      { name: 'shot_kind', type: 'string' },
      ...tenantScoped,
    ],
  },
  {
    name: 'shot_events',
    columns: [
      { name: 'server_id', type: 'string', isOptional: true, isIndexed: true },
      { name: 'shot_id', type: 'string', isIndexed: true },
      { name: 'event_kind', type: 'string', isIndexed: true },
      { name: 'monotonic_seq', type: 'number' },
      { name: 'payload', type: 'json' },
      { name: 'produced_at', type: 'number' },
      ...tenantScoped,
    ],
  },
  {
    name: 'consent_records',
    columns: [
      { name: 'server_id', type: 'string', isOptional: true, isIndexed: true },
      { name: 'user_id', type: 'string', isIndexed: true },
      { name: 'purpose', type: 'string' },
      { name: 'purpose_version', type: 'string' },
      { name: 'granted', type: 'boolean' },
      { name: 'granted_at', type: 'number' },
      { name: 'revoked_at', type: 'number', isOptional: true },
      { name: 'processing_basis', type: 'string' },
      { name: 'joint_controller_org_ids', type: 'json', isOptional: true },
      { name: 'joint_controller_agreement_ref', type: 'string', isOptional: true },
      ...tenantScoped,
    ],
  },
];

/** Returns the column names for a given table, throwing if the table is
 *  unknown. Sync engine uses this to validate push payloads before they
 *  cross the wire. */
export function columnsForTable(tableName: string): string[] {
  const t = TABLES.find((tbl) => tbl.name === tableName);
  if (!t) throw new Error(`Unknown table: ${tableName}`);
  return t.columns.map((c) => c.name);
}

/** Returns the set of tables that are safe to push without a server-side
 *  conflict resolution policy beyond last-write-wins. Excludes any future
 *  tables that need server-authoritative merges (e.g., consent revocations
 *  must be CRDT-merged once Sprint 17 ships withdrawal flow). */
export function pushableTables(): string[] {
  return TABLES.filter((t) => t.name !== 'consent_records').map((t) => t.name);
}
