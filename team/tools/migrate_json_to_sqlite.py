#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""migrate_json_to_sqlite.py — 把历史 JSON 台账/路由一次性回填进 SQLite（幂等，可重复跑）。

读取：
  observed/traces/*.json   单次任务 trace 台账
  observed/routes/*.json   GATE-0 路由判定落盘
写入：
  observed/dwb_team.db     traces / trace_steps / violations / routes

用法：
  python tools/migrate_json_to_sqlite.py            # 回填并打印统计
  python tools/migrate_json_to_sqlite.py --dry-run  # 只统计不落库
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import trace_db  # noqa: E402

TRACE_DIR = os.path.join(ROOT, 'observed', 'traces')
ROUTE_DIR = os.path.join(ROOT, 'observed', 'routes')


def _load_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description='历史 JSON 台账回填 SQLite')
    ap.add_argument('--dry-run', action='store_true', help='只统计，不写库')
    args = ap.parse_args()

    conn = None if args.dry_run else trace_db.connect()
    n_trace = n_step = n_viol = n_route = 0

    for name in sorted(os.listdir(TRACE_DIR)):
        if not name.lower().endswith('.json') or name.startswith('_'):
            continue
        obj = _load_json(os.path.join(TRACE_DIR, name))
        if not obj or not obj.get('trace_id'):
            continue
        n_trace += 1
        n_step += len(obj.get('dispatched') or [])
        n_viol += len(obj.get('violations') or [])
        if not args.dry_run:
            trace_db.upsert_trace(conn, obj, now_ts=obj.get('finished') or obj.get('started'))

    for name in sorted(os.listdir(ROUTE_DIR)):
        if not name.lower().endswith('.json'):
            continue
        route = _load_json(os.path.join(ROUTE_DIR, name))
        if not route or not route.get('trace_id'):
            continue
        n_route += 1
        if not args.dry_run:
            trace_db.upsert_route(conn, route, now_ts=route.get('at'))

    if conn:
        conn.commit()
        # 回填后统计库内实际行数
        n_trace = conn.execute('SELECT COUNT(*) c FROM traces').fetchone()['c']
        n_step = conn.execute('SELECT COUNT(*) c FROM trace_steps').fetchone()['c']
        n_viol = conn.execute('SELECT COUNT(*) c FROM violations').fetchone()['c']
        n_route = conn.execute('SELECT COUNT(*) c FROM routes').fetchone()['c']
        conn.close()

    print(f'traces: {n_trace}  trace_steps: {n_step}  violations: {n_viol}  routes: {n_route}')
    if args.dry_run:
        print('（dry-run，未写库）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
