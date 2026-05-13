/**
 * Wire protocol between the mobile sync engine and the backend.
 *
 * The shape mirrors WatermelonDB's pull/push contract (Nozbe's docs) but
 * is hand-defined so we never accidentally couple the wire to its internal
 * shapes. Backend handlers will live at:
 *
 *   GET  /sync/pull?since=<last_pulled_at>
 *   POST /sync/push    body: PushPayload
 *
 * The `last_pulled_at` cursor is server-issued; the device stores it
 * verbatim and never inspects it. This lets the backend swap from
 * wall-clock to logical-clock (LSN, Postgres replication slot) later
 * without a client update.
 *
 * Sprint 5 EPIC 5.2.
 */

export interface PullChanges {
  /** Per-table create/update/delete buckets. Keys are table names from
   *  `schema.TABLES`. Values are row objects keyed by server_id. */
  changes: {
    [tableName: string]: {
      created: (Record<string, unknown> & { server_id: string })[];
      updated: (Record<string, unknown> & { server_id: string })[];
      deleted: string[]; // server_ids tombstoned on the server
    };
  };
  /** Cursor the device hands back on its next pull. Opaque string. */
  timestamp: string;
}

export interface PushPayload {
  /** The cursor we last successfully pulled. The server uses this to
   *  detect cross-pull conflicts during the push. */
  last_pulled_at: string;
  /** Per-table buckets, same shape as pull but with local rows that need
   *  to be persisted server-side. */
  changes: {
    [tableName: string]: {
      created: Record<string, unknown>[];
      updated: (Record<string, unknown> & { server_id: string })[];
      deleted: string[]; // server_ids
    };
  };
}

export interface PushResult {
  /** Per-table map: local primary key → newly-issued server_id for rows that
   *  were created. The device patches the local row with this server_id so
   *  subsequent updates can target it. */
  server_ids: {
    [tableName: string]: {
      [localId: string]: string;
    };
  };
  /** Rows the server rejected (validation, RLS, joint-controller missing).
   *  The device must surface these to the user, not silently drop them. */
  rejected: {
    table: string;
    local_id: string;
    reason: string;
  }[];
  /** The new pull cursor — clients should adopt it before the next pull. */
  timestamp: string;
}

/**
 * Validates a PushPayload against the local schema. Returns the offending
 * (table, column) pairs the payload would push; an empty array means safe
 * to ship. Run at the engine boundary so a corrupted DB cannot poison the
 * server.
 */
export function validatePushPayload(
  payload: PushPayload,
  validColumnsByTable: Record<string, readonly string[]>,
): { table: string; column: string }[] {
  const errors: { table: string; column: string }[] = [];

  for (const [table, bucket] of Object.entries(payload.changes)) {
    const valid = validColumnsByTable[table];
    if (!valid) {
      errors.push({ table, column: "<unknown table>" });
      continue;
    }
    const validSet = new Set([...valid, "id"]); // local "id" is internal but
    // the engine may include it for round-trip resolution

    for (const row of [...bucket.created, ...bucket.updated]) {
      for (const col of Object.keys(row)) {
        if (!validSet.has(col)) {
          errors.push({ table, column: col });
        }
      }
    }
  }

  return errors;
}

export function emptyPullChanges(): PullChanges {
  return { changes: {}, timestamp: "" };
}
