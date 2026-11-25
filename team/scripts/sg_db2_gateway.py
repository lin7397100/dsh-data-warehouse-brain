#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sg-db2-gateway — DB2 访问前置拦截网关

替代直接调用 DeferExecuteTool(mcp__db2__*) 的唯一合法通道。
每次 SQL 执行前强制校验：谁在调用？是否合规？

用法：
  python sg_db2_gateway.py exec "<SQL>"        — 执行 SQL（需通过门禁）
  python sg_db2_gateway.py status               — 查看当前门禁状态

门禁规则（三层，按优先级；2026-11-05 与实现对齐）：
  G1 · 调用者身份 — health=critical 时须为 Agent，且声明身份必须与
                    trace.dispatched 交叉校验（环境变量自证不成立）
  G2 · 治理审查   — 只认 sg-governance 的实际派发记录；
                    violations 里的 governance-degraded 声明不构成授权
  G3 · 语句级只读语法校验 — SELECT/WITH 起手 + 单语句 + 写关键字词边界
                    + REPLACE INTO / ADMIN_CMD 语句级拦截

前置条件：活动 trace 由 G2 校验（无 trace 直接拦截）；health.json 连续
3 条违规判 critical。本网关不直连 DB2，通过后仍须由 sg-development 经
DB2 MCP 执行。

⚠ G3 是静态只读语法校验，**不核验编译产物**；G3 PASS ≠ 编译通过 / 执行授权。
  REPLACE(...) 是 DB2 合法标量函数，只拦 REPLACE INTO 语句形态。

退出码：
  0 = 门禁放行（SQL 尚未执行）
  1 = 门禁拦截（违规）
  2 = 配置错误
"""

import json
import os
import subprocess
import sys
import re

BASE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(BASE)
TRACE_DIR = os.path.join(PKG, 'observed', 'traces')
LATEST = os.path.join(TRACE_DIR, '_latest.json')
HEALTH_PATH = os.path.join(PKG, 'knowledge', 'design', 'supervision', 'health.json')


def load_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def get_active_trace():
    latest = load_json(LATEST)
    if not latest:
        return None
    path = os.path.join(TRACE_DIR, f'{latest["trace_id"]}.json')
    return load_json(path)


def check_health():
    """返回当前健康状态：ok / warning / critical"""
    health = load_json(HEALTH_PATH)
    if not health or not health.get('traces'):
        return 'ok'

    recent = health['traces'][-5:]
    violations = [t for t in recent if t.get('verdict') != '通过']
    if not violations:
        return 'ok'

    consecutive = 0
    for t in reversed(recent):
        if t.get('verdict') != '通过':
            consecutive += 1
        else:
            break

    if consecutive >= 3:
        return 'critical'
    elif consecutive >= 1:
        return 'warning'
    return 'ok'


# ---- 加固：移植同包 sgdw_sql_exec.py 的只读护栏（G3 修复） ----
_WRITE_KEYWORDS = (
    "INSERT", "UPDATE", "DELETE", "MERGE", "DROP", "CREATE", "ALTER",
    "TRUNCATE", "GRANT", "REVOKE", "CALL", "COMMIT", "ROLLBACK",
)


def _strip_literals(sql):
    """先剥离字符串字面量与 -- / /* */ 注释，避免误判列名或字面量中的关键字。"""
    s = re.sub(r"'(?:[^']|'')*'", "''", sql, flags=re.IGNORECASE)
    s = re.sub(r"--[^\n]*", " ", s)
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.DOTALL)
    return s


def is_caller_agent():
    """
    判断调用者是否是 Agent（子专家）。

    DSH 下 `delegate_expert` 派发后子专家运行在独立会话上下文中。
    通过以下信号判断（DSH 唯一信号集）：
    1. 环境变量 DSH_AGENT_ROLE / DSH_AGENT_ID / DSH_SUBAGENT 存在 → 是 Agent
    2. 都没有 → 保守视为编排器本身（DSH 主会话只有 DSH_SESSION_ID，不构成子专家信号）
    """
    for key in ('DSH_AGENT_ROLE', 'DSH_AGENT_ID', 'DSH_SUBAGENT'):
        val = os.environ.get(key, '')
        if val:
            return True, val

    # 无法确定 → 保守处理：假设是编排器本身
    return False, 'unknown'


def gate_g1_identity(trace):
    """G1: 调用者身份校验"""
    is_agent, role = is_caller_agent()
    health = check_health()

    if health == 'critical':
        # exit 3 模式下，编排器本人完全禁止访问 DB2
        if not is_agent:
            return False, f'G1拦截: 健康状态=critical(exit3)，编排器本人禁止访问DB2。SQL必须经 Agent(sg-development) 派发执行'
        # 加固：环境变量可自设，必须同时在本条 trace 的派发记录中能找到同一 Agent
        dispatched = (trace or {}).get('dispatched', []) or []
        matched = any(d.get('owner', '') == role for d in dispatched)
        if not matched:
            return False, f'G1拦截: 声明身份({role})未在trace派发记录中，环境变量自证不成立'
        return True, f'G1通过: Agent({role})在critical模式下获准访问(已与trace交叉校验)'

    if health == 'warning':
        if not is_agent:
            # exit 1/2: 编排器本人禁止直接访问 DB2（2026-11-13 硬拦截升级）
            # 此前 TR-20261112-1011-164E 的 E4 违规正是由此假绿灯放行
            return False, ('G1拦截: 健康状态=warning(exit1/2)，编排器本人禁止直接访问DB2。'
                          'SQL必须经 Agent(sg-development) 派发执行。'
                          '若派发通道故障(如 TEAM_DISPATCH_FAILED)，唯一合法动作为停止并告知用户，禁止编排器内联取数。')
        else:
            return True, f'G1通过: Agent({role})访问'

    return True, 'G1通过: 健康状态ok'


def gate_g2_governance(trace, sql):
    """G2: SQL 是否经 sg-governance 审查"""
    if not trace:
        return False, 'G2拦截: 无活动trace，未执行GATE-1 init'

    dispatched = trace.get('dispatched', [])
    # 🔧 P1 修复（2026-11-06）：原为 step in ('5','governance') 严格等值，
    # 导致 step='governance治理审查'（带中文后缀）、'5a' 等合法变体被误判为未派发。
    # 改为：step 归一化后 startswith 匹配。
    def _is_gov_step(step):
        st = str(step or '').strip().lower()
        return st in ('5',) or st.startswith('governance') or st.startswith('5.')             or st.startswith('5a') or st.startswith('5b')

    gov_approved = any(
        d.get('owner', '') == 'sg-governance' and _is_gov_step(d.get('step', ''))
        for d in dispatched
    )

    if gov_approved:
        return True, 'G2通过: sg-governance已派发'

    # 加固：撤销「violations 字符串声明即放行」旁路。
    # 任何 governance-degraded 声明都不构成授权；门禁结论只认已落地的派发记录。
    violations = trace.get('violations', [])
    has_degraded = any('governance' in v.lower() for v in violations)
    if has_degraded:
        return False, 'G2拦截: governance降级声明不构成授权，须实际派发sg-governance'
    return False, 'G2拦截: sg-governance未派发。SQL不得执行'


def gate_g3_compile(trace, sql):
    """G3: 语句级只读校验（移植 sgdw_sql_exec._is_readonly 并补多语句/REPLACE/ADMIN_CMD）。"""
    s = _strip_literals(sql).upper()
    head = s.lstrip()
    if not (head.startswith("SELECT") or head.startswith("WITH")):
        return False, 'G3拦截: SQL必须以SELECT或WITH开头'

    # 多语句拼接一律拒绝（DB2 允许分号分隔的复合语句）
    parts = [p for p in s.split(";") if p.strip()]
    if len(parts) > 1:
        return False, 'G3拦截: 检测到多语句拼接，只读通道仅允许单条语句'

    for kw in _WRITE_KEYWORDS:
        if re.search(r"\b" + kw + r"\b", s):
            return False, 'G3拦截: SQL包含禁止关键字 %s，只允许SELECT只读查询' % kw

    # REPLACE 语句级判别：REPLACE INTO 拦截，REPLACE(...) 标量函数放行
    if re.search(r"\bREPLACE\s+INTO\b", s):
        return False, 'G3拦截: REPLACE INTO 为写操作'
    # 可执行过程调用（DB2 ADMIN_CMD 可承载任意管理命令）
    if re.search(r"\bADMIN_CMD\b", s):
        return False, 'G3拦截: 可执行过程调用 ADMIN_CMD 不在只读白名单'

    return True, 'G3通过: 语句级只读校验通过'


def cmd_exec(args):
    """执行 SQL（需通过门禁）"""
    sql = args.sql
    trace = get_active_trace()
    health = check_health()

    print(f'=== DB2 Gateway 门禁检查 ===')
    print(f'  健康状态: {health}')
    print(f'  活动trace: {trace["trace_id"] if trace else "无"}')
    print()

    # G1: 身份
    g1_ok, g1_msg = gate_g1_identity(trace)
    g1_mark = 'PASS' if g1_ok else 'FAIL'
    print(f'  [G1 身份] {g1_mark} {g1_msg}')
    if not g1_ok:
        # 拦截时也写入 trace，留痕可审计
        if trace:
            trace.setdefault('g1_blocks', []).append({
                'sql': sql[:500],
                'health': health,
                'reason': g1_msg,
                'timestamp': __import__('datetime').datetime.now().isoformat(),
            })
            json.dump(trace, open(
                os.path.join(TRACE_DIR, f'{trace["trace_id"]}.json'),
                'w', encoding='utf-8'
            ), ensure_ascii=False, indent=2)
            print(f'  已记录 G1 拦截到 trace/{trace["trace_id"]}.json')
        return 1

    # G2: 治理审查
    g2_ok, g2_msg = gate_g2_governance(trace, sql)
    g2_mark = 'PASS' if g2_ok else 'FAIL'
    print(f'  [G2 治理] {g2_mark} {g2_msg}')
    if not g2_ok:
        return 1

    # G3: 语句级只读语法校验（非编译审查）
    g3_ok, g3_msg = gate_g3_compile(trace, sql)
    g3_mark = 'PASS' if g3_ok else 'FAIL'
    print(f'  [G3 语法] {g3_mark} {g3_msg}')
    if not g3_ok:
        return 1

    print()
    print('所有门禁通过。SQL 已放行，请通过 DeferExecuteTool(mcp__db2__execute_sql) 执行。')
    print('注意：G3 仅做静态只读语法校验，不核验编译产物；G3 PASS ≠ 编译通过 / 执行授权。')
    print()
    print(f'SQL: {sql[:200]}{"..." if len(sql) > 200 else ""}')

    # 写入 trace 记录
    if trace:
        trace.setdefault('sql_audit', []).append({
            'sql': sql[:500],
            'gates': {'G1': g1_ok, 'G2': g2_ok, 'G3': g3_ok},
            'health': health,
            'timestamp': __import__('datetime').datetime.now().isoformat(),
        })
        json.dump(trace, open(
            os.path.join(TRACE_DIR, f'{trace["trace_id"]}.json'),
            'w', encoding='utf-8'
        ), ensure_ascii=False, indent=2)
        print()
        print(f'已记录到 trace/{trace["trace_id"]}.json')

    return 0


def cmd_status(args):
    """查看当前门禁状态"""
    trace = get_active_trace()
    health = check_health()

    print('=== DB2 Gateway 状态 ===')
    print(f'  健康: {health}')
    print(f'  Trace: {trace["trace_id"] if trace else "无"}')
    if trace:
        dispatched = trace.get('dispatched', [])
        print(f'  已派发: {len(dispatched)} 位专家')
        for d in dispatched:
            print(f'    - {d.get("owner", "?")} (step={d.get("step", "?")})')
        violations = trace.get('violations', [])
        if violations:
            print(f'  违规: {len(violations)} 条')
    print()

    g1_ok, g1_msg = gate_g1_identity(trace)
    g2_ok, g2_msg = gate_g2_governance(trace, 'SELECT 1 FROM SYSIBM.SYSDUMMY1')
    g3_ok, g3_msg = gate_g3_compile(trace, 'SELECT 1 FROM SYSIBM.SYSDUMMY1')

    g1_mark = 'PASS' if g1_ok else 'FAIL'
    g2_mark = 'PASS' if g2_ok else 'FAIL'
    g3_mark = 'PASS' if g3_ok else 'FAIL'
    print(f'  G1身份: {g1_mark} {g1_msg}')
    print(f'  G2治理: {g2_mark} {g2_msg}')
    print(f'  G3语法: {g3_mark} {g3_msg}')

    return 0


def main():
    import argparse
    ap = argparse.ArgumentParser(description='DB2 访问前置拦截网关')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p1 = sub.add_parser('exec', help='执行 SQL（需通过门禁）')
    p1.add_argument('sql', help='待执行的 SQL 语句')

    p2 = sub.add_parser('status', help='查看当前门禁状态')

    args = ap.parse_args()
    return {'exec': cmd_exec, 'status': cmd_status}[args.cmd](args)


if __name__ == '__main__':
    sys.exit(main())