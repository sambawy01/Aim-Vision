/**
 * Sync engine — coordinates pull, conflict resolution, and push.
 *
 * Architecture (Sprint 5 EPIC 5.2):
 *
 *   pull -> for each row: resolveConflict -> apply to LocalStore
 *   push -> gather dirty rows from LocalStore -> validate -> POST -> patch server_ids
 *
 * The engine is decoupled from WatermelonDB through the LocalStore
 * interface. Tests substitute a Map-backed in-memory store and exercise
 * the full state machine without booting any native module. The real
 * WatermelonDB-backed implementation comes once we verify Hermes/Fabric
 * compatibility on RN 0.76 (Sprint 5 EPIC 5.4 sub-task).
 */

import { resolveConflict, parseChangedCols } from './conflict';
import {
  type PullChanges,
  type PushPayload,
  type PushResult,
  validatePushPayload,
} from './protocol';
import { columnsForTable, pushableTables, TABLES } from './schema';

export interface LocalRow extends Record<string, unknown> {
  id: string; // local primary key
  server_id?: string;
  _status: 'synced' | 'created' | 'updated' | 'deleted';
  _changed?: string; // CSV of column names dirty since last push
  updated_at: number;
}

export interface LocalStore {
  /** Returns all rows for a table where `_status !== 'synced'`. Used to
   *  build a push payload. */
  collectDirty(tableName: string): Promise<LocalRow[]>;

  /** Finds a row by server_id, used during pull conflict resolution. */
  findByServerId(tableName: string, serverId: string): Promise<LocalRow | null>;

  /** Inserts or replaces a row (post-conflict). Marks `_status = 'synced'`. */
  upsertSynced(tableName: string, row: Record<string, unknown>): Promise<void>;

  /** After a successful push, patches a created row with its new server_id
   *  and clears `_status` + `_changed`. */
  acceptCreate(tableName: string, localId: string, serverId: string): Promise<void>;

  /** Clears `_status` + `_changed` on a row whose update was accepted. */
  acceptUpdate(tableName: string, serverId: string): Promise<void>;

  /** Hard-deletes a row whose tombstone was accepted by the server. */
  acceptDelete(tableName: string, serverId: string): Promise<void>;

  /** Cursor durability: read and write the opaque pull cursor. */
  getCursor(): Promise<string>;
  setCursor(cursor: string): Promise<void>;
}

export interface Transport {
  pull(since: string): Promise<PullChanges>;
  push(payload: PushPayload): Promise<PushResult>;
}

export interface SyncResult {
  pulled: { [tableName: string]: number };
  pushed: { [tableName: string]: number };
  conflicts: number;
  rejected: PushResult['rejected'];
}

export class SyncEngine {
  constructor(
    private readonly store: LocalStore,
    private readonly transport: Transport,
    /** Side-channel for the engine to surface UI-visible warnings (rejected
     *  rows, conflicts the policy could not auto-resolve). Defaults to a
     *  no-op so unit tests do not need to mock it. */
    private readonly onWarning: (msg: string) => void = () => {},
  ) {}

  async syncOnce(): Promise<SyncResult> {
    const cursor = await this.store.getCursor();
    const pullChanges = await this.transport.pull(cursor);

    let conflicts = 0;
    const pulled: { [t: string]: number } = {};

    for (const [tableName, bucket] of Object.entries(pullChanges.changes)) {
      let count = 0;
      for (const created of bucket.created) {
        await this.applyPulledRow(tableName, created, /*isCreate*/ true);
        count++;
      }
      for (const updated of bucket.updated) {
        const local = await this.store.findByServerId(tableName, updated.server_id);
        if (!local) {
          await this.store.upsertSynced(tableName, updated);
        } else {
          const resolution = resolveConflict({
            tableName,
            local: local as LocalRow & { updated_at: number; server_id?: string },
            server: updated as Record<string, unknown> & {
              updated_at: number;
              server_id: string;
            },
            locallyChanged: parseChangedCols(local._changed),
          });
          conflicts++;
          if (resolution.kind === 'use_server' || resolution.kind === 'merge_fields') {
            await this.store.upsertSynced(
              tableName,
              resolution.kind === 'merge_fields' ? resolution.patch! : updated,
            );
          } else if (resolution.kind === 'skip') {
            this.onWarning(`sync: ${resolution.reason} (${tableName}/${updated.server_id})`);
          }
        }
        count++;
      }
      for (const sid of bucket.deleted) {
        await this.store.acceptDelete(tableName, sid);
        count++;
      }
      pulled[tableName] = count;
    }

    await this.store.setCursor(pullChanges.timestamp);

    const payload: PushPayload = {
      last_pulled_at: pullChanges.timestamp,
      changes: {},
    };
    const pushed: { [t: string]: number } = {};

    for (const tableName of pushableTables()) {
      const dirty = await this.store.collectDirty(tableName);
      if (dirty.length === 0) continue;

      const created: Record<string, unknown>[] = [];
      const updated: (Record<string, unknown> & { server_id: string })[] = [];
      const deleted: string[] = [];
      for (const row of dirty) {
        if (row._status === 'created') created.push(row);
        else if (row._status === 'updated' && row.server_id)
          updated.push(row as Record<string, unknown> & { server_id: string });
        else if (row._status === 'deleted' && row.server_id) deleted.push(row.server_id);
      }
      payload.changes[tableName] = { created, updated, deleted };
      pushed[tableName] = created.length + updated.length + deleted.length;
    }

    const validColumns: Record<string, readonly string[]> = {};
    for (const t of TABLES) validColumns[t.name] = columnsForTable(t.name);
    const errors = validatePushPayload(payload, validColumns);
    if (errors.length > 0) {
      const first = errors.slice(0, 3).map((e) => `${e.table}.${e.column}`);
      throw new Error(
        `sync: push payload contains unknown columns: ${first.join(', ')}${
          errors.length > 3 ? '...' : ''
        }`,
      );
    }

    const result =
      Object.keys(payload.changes).length === 0
        ? { server_ids: {}, rejected: [], timestamp: pullChanges.timestamp }
        : await this.transport.push(payload);

    for (const [tableName, idMap] of Object.entries(result.server_ids)) {
      for (const [localId, serverId] of Object.entries(idMap)) {
        await this.store.acceptCreate(tableName, localId, serverId);
      }
    }
    for (const [tableName, bucket] of Object.entries(payload.changes)) {
      for (const row of bucket.updated) {
        await this.store.acceptUpdate(tableName, row.server_id);
      }
      for (const sid of bucket.deleted) {
        await this.store.acceptDelete(tableName, sid);
      }
    }
    for (const rej of result.rejected) {
      this.onWarning(`sync: server rejected ${rej.table}/${rej.local_id}: ${rej.reason}`);
    }
    if (result.timestamp) await this.store.setCursor(result.timestamp);

    return { pulled, pushed, conflicts, rejected: result.rejected };
  }

  private async applyPulledRow(
    tableName: string,
    row: Record<string, unknown> & { server_id: string },
    _isCreate: boolean,
  ): Promise<void> {
    const local = await this.store.findByServerId(tableName, row.server_id);
    if (!local) {
      await this.store.upsertSynced(tableName, row);
      return;
    }
    // Race: server says "create" but we already have a row with this
    // server_id. Treat as an update and run conflict resolution.
    const resolution = resolveConflict({
      tableName,
      local: local as LocalRow & { updated_at: number; server_id?: string },
      server: row as Record<string, unknown> & { updated_at: number; server_id: string },
      locallyChanged: parseChangedCols(local._changed),
    });
    if (resolution.kind === 'use_server') {
      await this.store.upsertSynced(tableName, row);
    } else if (resolution.kind === 'merge_fields' && resolution.patch) {
      await this.store.upsertSynced(tableName, resolution.patch);
    }
  }
}
