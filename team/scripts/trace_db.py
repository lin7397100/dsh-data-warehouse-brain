# -*- coding: utf-8 -*-
"""trace_db.py — 数仓专家团台账 SQLite 存储层（混合方案：DB 权威 + JSON 快照兜底）。

表结构：
  traces        一次会话请求的主台账（覆盖率 / 裁定 / 元信息）
  trace_steps   派发步骤明细（专家 / 状态 / 耗时 / 产物），一对多
  violations    违规归因（步骤 / 类型 / 应到专家 / 文案），一对多
  routes        GATE-0 路由判定落盘，按 trace_id 关联
  v_expert_stats 专家派发统计视图（只读聚合）

DB 文件：observed/dwb_team.db（WAL 模式，单文件本地轻量化）。
本模块只被 Python 脚本（trace_log.py / gate_route.py / 迁移脚本）写入；
面板宿主半（Node）经 node:sqlite 只读查询。
"""

import json
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DB_PATH = os.path.join(ROOT, 'observed', 'dwb_team.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
  trace_id       TEXT PRIMARY KEY,
  started        TEXT,
  finished       TEXT,
  task_type      TEXT,
  lane           TEXT,
  fast_lane      INTEGER NOT NULL DEFAULT 0,
  expected_steps TEXT,            -- JSON 数组
  inline_steps   TEXT,            -- JSON 数组
  coverage_rate  REAL,
  coverage_rate_norm REAL,       -- 专家归属归一折算覆盖率（交叉核对口径）
  verdict        TEXT,
  text           TEXT,
  at             TEXT,
  updated_at     TEXT
);

CREATE TABLE IF NOT EXISTS trace_steps (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  trace_id    TEXT NOT NULL,
  step        TEXT NOT NULL,
  owner       TEXT,
  at          TEXT,
  started_at  TEXT,            -- 子代理实际创建/首步时间（纯执行起点）
  finished    TEXT,
  finished_at TEXT,            -- 子代理最后消息/收尾时间（纯执行终点）
  backfill_at TEXT,            -- 父代理回写台账时间
  duration_s  INTEGER,         -- 墙钟耗时（at → finished，含排队/回填缺口）
  duration_pure_s INTEGER,     -- 纯执行耗时（started_at → finished_at）
  status      TEXT,
  artifact    TEXT,
  UNIQUE(trace_id, step, owner)
);

CREATE TABLE IF NOT EXISTS violations (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  trace_id      TEXT NOT NULL,
  step          TEXT,
  kind          TEXT,            -- inline / missing / misdispatch
  expected_owner TEXT,
  message       TEXT NOT NULL,
  UNIQUE(trace_id, message)
);

CREATE TABLE IF NOT EXISTS routes (
  trace_id           TEXT PRIMARY KEY,
  at                 TEXT,
  lane               TEXT,
  task_type          TEXT,
  source             TEXT,
  agreement          TEXT,
  confidence         REAL,
  text               TEXT,
  reasons            TEXT,        -- JSON 数组
  signals            TEXT,        -- JSON 数组
  jev                TEXT,        -- JSON 对象
  sla_target_seconds INTEGER,
  timeout_minutes    INTEGER,
  next               TEXT,
  trace_init         TEXT,
  updated_at         TEXT
);

CREATE VIEW IF NOT EXISTS v_expert_stats AS
SELECT owner,
       COUNT(*) AS dispatches,
       SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS done,
       SUM(CASE WHEN status IN ('failed','blocked') THEN 1 ELSE 0 END) AS failed,
       ROUND(AVG(duration_s), 1) AS avg_duration_s
FROM trace_steps
WHERE owner IS NOT NULL AND owner <> ''
GROUP BY owner;

CREATE INDEX IF NOT EXISTS idx_steps_trace ON trace_steps(trace_id);
CREATE INDEX IF NOT EXISTS idx_violations_trace ON violations(trace_id);
"""


def connect(db_path=None):
    """打开（必要时建库建表）连接，WAL 模式。"""
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript(SCHEMA)
    # 旧库平滑补列：coverage_rate_norm（2026-11-19 新增）
    cols = {r[1] for r in conn.execute('PRAGMA table_info(traces)').fetchall()}
    for col, ddl in [('coverage_rate_norm', 'REAL'), ('degraded_at', 'TEXT'),
                     ('degrade_manifest', 'TEXT'), ('orphan_sessions', 'TEXT')]:
        if col not in cols:
            conn.execute(f'ALTER TABLE traces ADD COLUMN {col} {ddl}')
    # 旧库平滑补列：trace_steps 三时间戳 + 纯执行时长（2026-11-19 新增）
    step_cols = {r[1] for r in conn.execute('PRAGMA table_info(trace_steps)').fetchall()}
    for col, ddl in [('started_at', 'TEXT'), ('finished_at', 'TEXT'),
                     ('backfill_at', 'TEXT'), ('duration_pure_s', 'INTEGER'),
                     ('state', 'TEXT'), ('reason', 'TEXT'), ('error', 'TEXT'),
                     ('retries', 'INTEGER')]:
        if col not in step_cols:
            conn.execute(f'ALTER TABLE trace_steps ADD COLUMN {col} {ddl}')
    return conn


def _j(obj):
    return json.dumps(obj, ensure_ascii=False)


def upsert_trace(conn, obj, now_ts=None):
    """把台账主表 + 步骤 + 违规整体落库（步骤/违规按 trace_id 重建，保证与 JSON 快照一致）。"""
    tid = obj['trace_id']
    conn.execute(
        """INSERT INTO traces
           (trace_id, started, finished, task_type, lane, fast_lane,
            expected_steps, inline_steps, coverage_rate, coverage_rate_norm, verdict, text,
            at, updated_at, degraded_at, degrade_manifest, orphan_sessions)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(trace_id) DO UPDATE SET
             started=excluded.started, finished=excluded.finished,
             task_type=excluded.task_type, lane=excluded.lane,
             fast_lane=excluded.fast_lane, expected_steps=excluded.expected_steps,
             inline_steps=excluded.inline_steps, coverage_rate=excluded.coverage_rate,
             coverage_rate_norm=excluded.coverage_rate_norm,
             verdict=excluded.verdict, text=excluded.text, at=excluded.at,
             updated_at=excluded.updated_at, degraded_at=excluded.degraded_at,
             degrade_manifest=excluded.degrade_manifest,
             orphan_sessions=excluded.orphan_sessions""",
        (tid, obj.get('started'), obj.get('finished'), obj.get('task_type'),
         obj.get('lane'), 1 if obj.get('fast_lane') else 0,
         _j(obj.get('expected_steps') or []), _j(obj.get('inline_steps') or []),
         obj.get('coverage_rate'), obj.get('coverage_rate_norm'),
         obj.get('verdict'), obj.get('text'),
         obj.get('at') or obj.get('started'), now_ts,
         obj.get('degraded_at'), obj.get('degrade_manifest'),
         _j(obj.get('orphan_sessions') or [])),
    )
    replace_steps(conn, tid, obj.get('dispatched') or [])
    replace_violations(conn, tid, obj.get('violations') or [])


def replace_steps(conn, trace_id, dispatched):
    conn.execute('DELETE FROM trace_steps WHERE trace_id=?', (trace_id,))
    for e in dispatched:
        conn.execute(
            """INSERT OR IGNORE INTO trace_steps
               (trace_id, step, owner, at, started_at, finished, finished_at,
                backfill_at, duration_s, duration_pure_s, status, artifact,
                state, reason, error, retries)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (trace_id, e.get('step'), e.get('owner'), e.get('at'),
             e.get('started_at'), e.get('finished'), e.get('finished_at'),
             e.get('backfill_at'), e.get('duration_s'), e.get('duration_pure_s'),
             e.get('status') or 'started', e.get('artifact'),
             e.get('state'), e.get('reason'), e.get('error'), e.get('retries') or 0),
        )


def replace_violations(conn, trace_id, messages):
    """违规文案整体重建；kind/step/expected_owner 从文案解析（结构化留痕便于后续筛选）。"""
    conn.execute('DELETE FROM violations WHERE trace_id=?', (trace_id,))
    for msg in messages:
        step, kind, expected = _parse_violation(msg)
        conn.execute(
            """INSERT OR IGNORE INTO violations
               (trace_id, step, kind, expected_owner, message)
               VALUES (?,?,?,?,?)""",
            (trace_id, step, kind, expected, msg),
        )


def _parse_violation(msg):
    """从违规文案粗解析步骤号 / 类型 / 应到专家。"""
    step, kind, expected = None, None, None
    text = str(msg or '')
    if text.startswith('Step '):
        head = text[5:].split(' ', 1)[0]
        step = head
    if '错派' in text:
        kind = 'misdispatch'
        if '应为' in text:
            expected = text.split('应为', 1)[1].strip()
    elif '内联' in text:
        kind = 'inline'
    elif '未派发' in text or '跳过' in text:
        kind = 'missing'
    return step, kind, expected


def upsert_route(conn, route, now_ts=None):
    jev = route.get('jev')
    conn.execute(
        """INSERT INTO routes
           (trace_id, at, lane, task_type, source, agreement, confidence, text,
            reasons, signals, jev, sla_target_seconds, timeout_minutes, next,
            trace_init, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(trace_id) DO UPDATE SET
             at=excluded.at, lane=excluded.lane, task_type=excluded.task_type,
             source=excluded.source, agreement=excluded.agreement,
             confidence=excluded.confidence, text=excluded.text,
             reasons=excluded.reasons, signals=excluded.signals, jev=excluded.jev,
             sla_target_seconds=excluded.sla_target_seconds,
             timeout_minutes=excluded.timeout_minutes, next=excluded.next,
             trace_init=excluded.trace_init, updated_at=excluded.updated_at""",
        (route.get('trace_id'), route.get('at'), route.get('lane'),
         route.get('task_type'), route.get('source'), route.get('agreement'),
         (jev or {}).get('confidence') if isinstance(jev, dict) else None,
         route.get('text'), _j(route.get('reasons') or []),
         _j(route.get('signals') or []), _j(jev) if jev is not None else None,
         route.get('sla_target_seconds'), route.get('timeout_minutes'),
         route.get('next'), route.get('trace_init'), now_ts),
    )


def load_trace(conn, trace_id):
    """按 trace_id 重建台账对象（与历史 JSON 结构对齐，供 trace_log 内部读写）。"""
    row = conn.execute('SELECT * FROM traces WHERE trace_id=?', (trace_id,)).fetchone()
    if not row:
        return None
    obj = dict(row)
    obj['fast_lane'] = bool(obj.get('fast_lane'))
    obj['expected_steps'] = json.loads(obj.get('expected_steps') or '[]')
    obj['inline_steps'] = json.loads(obj.get('inline_steps') or '[]')
    obj['orphan_sessions'] = json.loads(obj.get('orphan_sessions') or '[]')
    steps = conn.execute(
        'SELECT step, owner, at, started_at, finished, finished_at, backfill_at, '
        'duration_s, duration_pure_s, status, artifact, state, reason, error, retries '
        'FROM trace_steps WHERE trace_id=?', (trace_id,)).fetchall()
    obj['dispatched'] = [dict(s) for s in steps]
    viols = conn.execute(
        'SELECT message FROM violations WHERE trace_id=? ORDER BY id', (trace_id,)).fetchall()
    obj['violations'] = [v['message'] for v in viols]
    return obj


def latest_trace_id(conn):
    row = conn.execute(
        'SELECT trace_id FROM traces ORDER BY COALESCE(started, at) DESC LIMIT 1').fetchone()
    return row['trace_id'] if row else None
