import { resolveConflict, parseChangedCols } from '../conflict';

const localBase = (overrides: Record<string, unknown> = {}) => ({
  id: 'loc1',
  server_id: 'srv1',
  _status: 'synced' as const,
  updated_at: 1000,
  discipline: 'trap',
  ...overrides,
});

const serverBase = (overrides: Record<string, unknown> = {}) => ({
  server_id: 'srv1',
  updated_at: 2000,
  discipline: 'skeet',
  ...overrides,
});

describe('sync/conflict', () => {
  test('server-authoritative tables always use_server', () => {
    const r = resolveConflict({
      tableName: 'consent_records',
      local: localBase(),
      server: serverBase(),
      locallyChanged: new Set(['granted']),
    });
    expect(r.kind).toBe('use_server');
  });

  test('append-only tables (shots) use_server when server_id matches', () => {
    const r = resolveConflict({
      tableName: 'shots',
      local: localBase(),
      server: serverBase(),
      locallyChanged: new Set(),
    });
    expect(r.kind).toBe('use_server');
    expect(r.reason).toContain('append-only');
  });

  test('athlete-owned mutable: server newer, no local changes -> use_server', () => {
    const r = resolveConflict({
      tableName: 'sessions',
      local: localBase({ updated_at: 1000 }),
      server: serverBase({ updated_at: 2000 }),
      locallyChanged: new Set(),
    });
    expect(r.kind).toBe('use_server');
  });

  test('athlete-owned mutable: local newer -> use_local', () => {
    const r = resolveConflict({
      tableName: 'sessions',
      local: localBase({ updated_at: 5000, discipline: 'doubles_trap' }),
      server: serverBase({ updated_at: 2000 }),
      locallyChanged: new Set(['discipline']),
    });
    expect(r.kind).toBe('use_local');
  });

  test('athlete-owned mutable: server newer with local dirty cols -> merge_fields', () => {
    const r = resolveConflict({
      tableName: 'sessions',
      local: localBase({ updated_at: 1000, discipline: 'doubles_trap' }),
      server: serverBase({ updated_at: 2000, discipline: 'skeet', started_at: 999 }),
      locallyChanged: new Set(['discipline']),
    });
    expect(r.kind).toBe('merge_fields');
    // Server's started_at preserved, local's discipline preserved.
    expect(r.patch?.started_at).toBe(999);
    expect(r.patch?.discipline).toBe('doubles_trap');
  });

  test('unknown table -> skip', () => {
    const r = resolveConflict({
      tableName: 'nonexistent',
      local: localBase(),
      server: serverBase(),
      locallyChanged: new Set(),
    });
    expect(r.kind).toBe('skip');
  });

  test('parseChangedCols handles null, empty, single, and multiple', () => {
    expect(parseChangedCols(null)).toEqual(new Set());
    expect(parseChangedCols(undefined)).toEqual(new Set());
    expect(parseChangedCols('')).toEqual(new Set());
    expect(parseChangedCols('a')).toEqual(new Set(['a']));
    expect(parseChangedCols('a,b, c')).toEqual(new Set(['a', 'b', 'c']));
  });
});
