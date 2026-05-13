/**
 * Pure-TS tests for the sync schema. No native modules, no babel-preset-flow,
 * just type-level + value-level assertions on the schema definitions.
 *
 * The mobile-ci jest job is currently advisory (`continue-on-error: true`)
 * because of unrelated RN 0.76 Flow mapped-type parser limits. These tests
 * still run; they just do not block CI yet.
 */

import { TABLES, columnsForTable, pushableTables, SCHEMA_VERSION } from "../schema";

describe("sync/schema", () => {
  test("schema version is a positive integer", () => {
    expect(Number.isInteger(SCHEMA_VERSION)).toBe(true);
    expect(SCHEMA_VERSION).toBeGreaterThan(0);
  });

  test("every table has tenant_id, _status, created_at, updated_at", () => {
    for (const table of TABLES) {
      const names = table.columns.map((c) => c.name);
      for (const required of ["tenant_id", "_status", "created_at", "updated_at"]) {
        expect(names).toContain(required);
      }
    }
  });

  test("every foreign key column is indexed for query performance", () => {
    const fkSuffixes = ["_id"];
    for (const table of TABLES) {
      for (const col of table.columns) {
        if (col.name === "id" || col.name === "server_id") continue;
        if (fkSuffixes.some((s) => col.name.endsWith(s))) {
          expect(col.isIndexed).toBe(true);
        }
      }
    }
  });

  test("columnsForTable throws on unknown table", () => {
    expect(() => columnsForTable("nope")).toThrow(/Unknown table/);
  });

  test("columnsForTable returns the configured columns", () => {
    const cols = columnsForTable("shots");
    expect(cols).toEqual(
      expect.arrayContaining(["session_id", "monotonic_seq", "device_clock_ns", "tenant_id"]),
    );
  });

  test("pushableTables excludes consent_records (server-authoritative)", () => {
    const t = pushableTables();
    expect(t).not.toContain("consent_records");
    expect(t).toContain("sessions");
    expect(t).toContain("shots");
    expect(t).toContain("shot_events");
  });
});
