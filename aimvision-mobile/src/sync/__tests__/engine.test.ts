/**
 * Engine tests with a Map-backed in-memory LocalStore and a stubbed Transport.
 * No native modules involved.
 */

import { SyncEngine, type LocalRow, type LocalStore, type Transport } from "../engine";
import type { PullChanges, PushPayload, PushResult } from "../protocol";

class MemoryStore implements LocalStore {
  private tables = new Map<string, Map<string, LocalRow>>(); // tableName -> id -> row
  private byServerId = new Map<string, Map<string, string>>(); // tableName -> serverId -> localId
  private cursor = "";

  private bucket(name: string) {
    if (!this.tables.has(name)) this.tables.set(name, new Map());
    if (!this.byServerId.has(name)) this.byServerId.set(name, new Map());
    return this.tables.get(name)!;
  }

  seed(name: string, row: LocalRow) {
    this.bucket(name).set(row.id, { ...row });
    if (row.server_id) this.byServerId.get(name)!.set(row.server_id, row.id);
  }

  rows(name: string): LocalRow[] {
    return Array.from(this.bucket(name).values());
  }

  async collectDirty(name: string): Promise<LocalRow[]> {
    return this.rows(name).filter((r) => r._status !== "synced");
  }

  async findByServerId(name: string, serverId: string): Promise<LocalRow | null> {
    const localId = this.byServerId.get(name)?.get(serverId);
    if (!localId) return null;
    return this.bucket(name).get(localId) ?? null;
  }

  async upsertSynced(name: string, row: Record<string, unknown>): Promise<void> {
    const sid = row.server_id as string;
    let localId = (row.id as string) ?? this.byServerId.get(name)?.get(sid);
    if (!localId) localId = `auto-${sid}`;
    const merged: LocalRow = {
      ...(this.bucket(name).get(localId) ?? {}),
      ...row,
      id: localId,
      _status: "synced",
      _changed: undefined,
      updated_at: (row.updated_at as number) ?? Date.now(),
    } as LocalRow;
    this.bucket(name).set(localId, merged);
    if (sid) this.byServerId.get(name)!.set(sid, localId);
  }

  async acceptCreate(name: string, localId: string, serverId: string): Promise<void> {
    const row = this.bucket(name).get(localId);
    if (!row) return;
    row.server_id = serverId;
    row._status = "synced";
    row._changed = undefined;
    this.byServerId.get(name)!.set(serverId, localId);
  }

  async acceptUpdate(name: string, serverId: string): Promise<void> {
    const localId = this.byServerId.get(name)?.get(serverId);
    if (!localId) return;
    const row = this.bucket(name).get(localId);
    if (row) {
      row._status = "synced";
      row._changed = undefined;
    }
  }

  async acceptDelete(name: string, serverId: string): Promise<void> {
    const localId = this.byServerId.get(name)?.get(serverId);
    if (localId) this.bucket(name).delete(localId);
    this.byServerId.get(name)!.delete(serverId);
  }

  async getCursor(): Promise<string> {
    return this.cursor;
  }
  async setCursor(c: string): Promise<void> {
    this.cursor = c;
  }
}

class StubTransport implements Transport {
  constructor(
    public pullChanges: PullChanges,
    public pushResult: PushResult,
  ) {}
  pushedPayload: PushPayload | null = null;

  async pull(_since: string): Promise<PullChanges> {
    return this.pullChanges;
  }
  async push(payload: PushPayload): Promise<PushResult> {
    this.pushedPayload = payload;
    return this.pushResult;
  }
}

describe("SyncEngine.syncOnce", () => {
  test("pulled creates land as synced rows and cursor advances", async () => {
    const store = new MemoryStore();
    const transport = new StubTransport(
      {
        changes: {
          sessions: {
            created: [
              {
                server_id: "srv-s1",
                org_id: "org1",
                athlete_user_id: "u1",
                discipline: "trap",
                started_at: 1000,
                tenant_id: "org:club1",
                updated_at: 1000,
              },
            ],
            updated: [],
            deleted: [],
          },
        },
        timestamp: "cursor-1",
      },
      { server_ids: {}, rejected: [], timestamp: "cursor-1" },
    );

    const engine = new SyncEngine(store, transport);
    const result = await engine.syncOnce();

    expect(result.pulled.sessions).toBe(1);
    expect(await store.getCursor()).toBe("cursor-1");
    const rows = store.rows("sessions");
    expect(rows).toHaveLength(1);
    expect(rows[0]._status).toBe("synced");
    expect(rows[0].server_id).toBe("srv-s1");
  });

  test("push: locally-created row gets a server_id and is marked synced", async () => {
    const store = new MemoryStore();
    store.seed("sessions", {
      id: "loc-s1",
      _status: "created",
      updated_at: 1500,
      org_id: "org1",
      athlete_user_id: "u1",
      discipline: "trap",
      started_at: 1500,
      tenant_id: "org:club1",
      created_at: 1500,
    });
    const transport = new StubTransport(
      { changes: {}, timestamp: "cursor-0" },
      {
        server_ids: { sessions: { "loc-s1": "srv-new" } },
        rejected: [],
        timestamp: "cursor-2",
      },
    );

    const engine = new SyncEngine(store, transport);
    const result = await engine.syncOnce();

    expect(result.pushed.sessions).toBe(1);
    const row = store.rows("sessions")[0];
    expect(row.server_id).toBe("srv-new");
    expect(row._status).toBe("synced");
    expect(await store.getCursor()).toBe("cursor-2");
  });

  test("push rejection surfaces via onWarning, not by throwing", async () => {
    const store = new MemoryStore();
    store.seed("shots", {
      id: "loc-shot1",
      _status: "created",
      updated_at: 1500,
      session_id: "loc-s1",
      monotonic_seq: 1,
      device_clock_ns: 1_000_000_000,
      server_clock_ns: 1_000_000_500,
      shot_kind: "single",
      tenant_id: "org:club1",
      created_at: 1500,
    });
    const transport = new StubTransport(
      { changes: {}, timestamp: "cursor-0" },
      {
        server_ids: {},
        rejected: [{ table: "shots", local_id: "loc-shot1", reason: "RLS denied" }],
        timestamp: "cursor-3",
      },
    );
    const warnings: string[] = [];
    const engine = new SyncEngine(store, transport, (m) => warnings.push(m));

    await engine.syncOnce();

    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toMatch(/RLS denied/);
  });

  test("server update on a row with local dirty cols -> merge_fields applied", async () => {
    const store = new MemoryStore();
    store.seed("sessions", {
      id: "loc-s1",
      server_id: "srv-s1",
      _status: "updated",
      _changed: "discipline",
      updated_at: 1000,
      org_id: "org1",
      athlete_user_id: "u1",
      discipline: "doubles_trap", // local
      started_at: 999,
      tenant_id: "org:club1",
      created_at: 999,
    });
    const transport = new StubTransport(
      {
        changes: {
          sessions: {
            created: [],
            updated: [
              {
                server_id: "srv-s1",
                org_id: "org1",
                athlete_user_id: "u1",
                discipline: "skeet", // server
                started_at: 1000,
                tenant_id: "org:club1",
                updated_at: 2000,
              },
            ],
            deleted: [],
          },
        },
        timestamp: "cursor-4",
      },
      { server_ids: {}, rejected: [], timestamp: "cursor-4" },
    );

    const engine = new SyncEngine(store, transport);
    await engine.syncOnce();

    const row = store.rows("sessions")[0];
    expect(row.discipline).toBe("doubles_trap");
    expect(row.started_at).toBe(1000);
    expect(row._status).toBe("synced");
  });

  test("push payload with an unknown column throws before contacting the server", async () => {
    const store = new MemoryStore();
    store.seed("sessions", {
      id: "loc-s1",
      _status: "created",
      updated_at: 1500,
      org_id: "org1",
      athlete_user_id: "u1",
      discipline: "trap",
      started_at: 1500,
      tenant_id: "org:club1",
      created_at: 1500,
      // Inject a column the schema does not know about.
      bogus_column: "x",
    } as unknown as LocalRow);
    const transport = new StubTransport(
      { changes: {}, timestamp: "cursor-0" },
      { server_ids: {}, rejected: [], timestamp: "" },
    );
    const engine = new SyncEngine(store, transport);

    await expect(engine.syncOnce()).rejects.toThrow(/unknown columns/);
    expect(transport.pushedPayload).toBeNull();
  });
});
