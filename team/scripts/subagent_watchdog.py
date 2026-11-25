# -*- coding: utf-8 -*-
"""subagent_watchdog.py — 子代理终态看门狗 + 错误序列化 + 降级收尾（2026-11-19 根治项）

背景（TR-20261119-1631-62A2 复盘）：
  1. 子代理回合以 error / aborted 终止后，旧回收器只看 projcache 的 settled 标志，
     把「已死」会话误判为「仍在运行」，主理人 wait_agent 死等到超时；
  2. 回执里的 Error 对象未序列化，模型 / 看板只看到 `[object Object]`；
  3. 父会话 dispose 前不扫描已落盘的中间产物，整链成果随终止一起丢失。

本模块在自有台账层补齐这三项（DSH 内置 subagent 插件源码封闭在基座包内，不可直接改）：
  - inspect_session：读 projcache + 转录 zstd，识别 completed / error / aborted / stalled / running；
  - serialize_error：把 Error / dict / 字符串统一转成可读文本，杜绝 [object Object]；
  - scan_trace：把终态与可读错误快照回写台账（不重算覆盖率，覆盖率仍归 report）；
  - degrade_finalize：终止前扫描该 trace 已落盘产物，写降级清单 manifest，可用图表 HTML 兜底复制。

用法：
  python subagent_watchdog.py scan   [--trace-id TR-...] [--json]
  python subagent_watchdog.py degrade [--trace-id TR-...] [--yes]
"""

import argparse
import glob
import json
import os
import re
import shutil
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(BASE)
TRACE_DIR = os.path.join(PKG, 'observed', 'traces')
DEGRADE_DIR = os.path.join(PKG, 'observed', 'degrade')
REPORT_DIR = os.path.join(PKG, 'observed', 'report')
ANALYSIS_DIR = os.path.join(PKG, 'artifacts', 'analysis')

PROJCACHE_DIR = os.path.join(os.path.expanduser('~'), '.dsh', 'storages',
                             'session_projcache', 'sessions')
TRANSCRIPT_ROOT = os.path.join(os.path.expanduser('~'), '.dsh', 'sessions')

# 静默阈值：最后消息距今超过该时长且无在途工具调用，判 stalled（默认 10 分钟）
STALL_MS = 10 * 60 * 1000
# 单路子代理自动重试预算（与 parallel_coordination §4「补派 1 次」对齐，留 1 次余量）
MAX_RETRIES = 2

# 阶段 → 产物目录（用于降级收尾扫描）
STAGE_DIRS = {
    'ontology': os.path.join(PKG, 'observed', 'ontology'),
    'caliber': os.path.join(PKG, 'observed', 'caliber'),
    'dsl': os.path.join(PKG, 'observed', 'dsl'),
    'sql': os.path.join(PKG, 'observed', 'sql'),
    'audit': os.path.join(PKG, 'observed', 'audit'),
    'quality': os.path.join(PKG, 'observed', 'quality'),
    'lineage': os.path.join(PKG, 'observed', 'lineage'),
    'data': os.path.join(PKG, 'observed', 'data'),
    'report': REPORT_DIR,
    'analysis': ANALYSIS_DIR,
}


def now():
    return datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')


def _parse_ms(iso):
    if not iso:
        return None
    try:
        return int(datetime.strptime(iso, '%Y-%m-%dT%H:%M:%S+08:00').timestamp() * 1000)
    except Exception:
        return None


def _load_json(path):
    try:
        return json.load(open(path, encoding='utf-8'))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 错误序列化（根治项 2）
# ---------------------------------------------------------------------------
def serialize_error(err):
    """把任意错误形态转成可读单行文本；禁止向上层透传 [object Object]。

    支持：Exception 实例、{kind,error:{message,code}}、{message,code,stack}、
    字符串、None；无法解析时给兜底说明而不是对象字面量。
    """
    if err is None:
        return ''
    if isinstance(err, str):
        return err.strip()
    if isinstance(err, Exception):
        parts = [type(err).__name__]
        if getattr(err, 'args', None):
            parts.append(str(err.args[0]))
        code = getattr(err, 'code', None)
        if code:
            parts.append(f'code={code}')
        return ': '.join(p for p in parts if p)
    if isinstance(err, dict):
        inner = err.get('error')
        if isinstance(inner, dict):
            err = inner
        bits = []
        for key in ('kind', 'code', 'message'):
            val = err.get(key)
            if val and isinstance(val, str):
                bits.append(f'{key}={val}')
        nested = err.get('reason')
        if isinstance(nested, dict):
            bits.append('reason=' + serialize_error(nested))
        elif nested:
            bits.append(f'reason={nested}')
        stack = err.get('stack')
        if isinstance(stack, str) and stack:
            bits.append('stack=' + stack.splitlines()[0][:120])
        if bits:
            return '；'.join(bits)
        # 字典无可读字段：摘键名，避免输出 [object Object]
        return '错误对象（字段: %s）' % ', '.join(sorted(err.keys())[:6])
    text = str(err)
    if text == '[object Object]' or text == '{}':
        return '（错误对象未序列化，原始内容无法读取）'
    return text


# ---------------------------------------------------------------------------
# 会话终态识别（根治项 1）
# ---------------------------------------------------------------------------
def _read_transcript_ends(session_id):
    """解压子代理转录 zstd，返回全部 turn/end 事件（按出现顺序）。

    转录为多帧 zstd jsonl；zstandard 不可用或文件缺失时返回空列表，不阻断主流程。
    保留全部事件是为了记录「首轮 error → 重试后 completed」的历史，避免只看末轮掩盖失败。
    """
    hits = glob.glob(os.path.join(TRANSCRIPT_ROOT, '*', session_id, 'session.v4.jsonl.zstd'))
    if not hits:
        return []
    try:
        import zstandard as zstd  # 延迟导入，缺失时降级为仅看 projcache
    except Exception:
        return []
    try:
        d = zstd.ZstdDecompressor()
        with d.stream_reader(open(hits[0], 'rb')) as r:
            lines = r.read().decode('utf-8', 'replace').splitlines()
        ends = []
        for ln in lines:
            try:
                o = json.loads(ln)
            except Exception:
                continue
            if o.get('type') == 'turn/end':
                ends.append(o)
        return ends
    except Exception:
        return []


def inspect_session(session_id):
    """汇总单个子代理会话的终态判定。

    返回 dict:
      session_id, preset, state(completed/error/aborted/stalled/running/unknown),
      reason, error, last_ms, created_ms, pending_calls, response, transcript_end
    """
    proj = _load_json(os.path.join(PROJCACHE_DIR, f'{session_id}.json')) or {}
    rows = proj.get('record', {}).get('rows', {})
    preset = (rows.get('agentPreset', {}).get('val')
              or rows.get('subagent', {}).get('val', {}).get('identity', {}).get('mode'))
    stats = rows.get('sessionStats', {}).get('val', {}) or {}
    tc = rows.get('timeContext', {}).get('val', {}) or {}
    timing = rows.get('subagentTiming', {}).get('val', {}) or {}
    turns = rows.get('turnOutline', {}).get('val', {}).get('turns', [])
    response = (turns[-1].get('response') or '').strip() if turns else ''

    created = (proj.get('record', {}).get('identity', {}).get('createdAt'))
    last = tc.get('lastMessageTime')
    pending = stats.get('pendingCalls') or {}

    ends = _read_transcript_ends(session_id)
    end_event = ends[-1] if ends else None
    reason = None
    err_text = ''
    end_kind = None
    error_history = []
    if end_event:
        reason = end_event.get('data', {}).get('reason') or {}
        end_kind = reason.get('kind')
        if end_kind == 'error':
            err_text = serialize_error(reason.get('error') or reason)
        elif end_kind == 'aborted':
            err_text = serialize_error(reason)
    # 历史回合：除末轮外的 error/aborted 留痕（重试审计用）
    for ev in ends[:-1]:
        r = ev.get('data', {}).get('reason') or {}
        if r.get('kind') in ('error', 'aborted'):
            error_history.append(serialize_error(r.get('error') or r))

    now_ms = int(datetime.now().timestamp() * 1000)

    if end_kind == 'completed' or timing.get('lastTurnCompleted'):
        state = 'completed'
    elif end_kind == 'error':
        state = 'error'
    elif end_kind == 'aborted':
        state = 'aborted'
    elif last and not pending and now_ms - last > STALL_MS:
        state = 'stalled'
    elif last or created:
        state = 'running'
    else:
        state = 'unknown'

    return {
        'session_id': session_id,
        'preset': preset,
        'state': state,
        'reason': end_kind,
        'error': err_text,
        'error_history': error_history,
        'created_ms': created,
        'last_ms': last,
        'pending_calls': sorted(pending.keys()) if isinstance(pending, dict) else [],
        'response': response[:300],
        'transcript_end': bool(end_event),
    }


def _list_child_sessions():
    out = []
    if not os.path.isdir(PROJCACHE_DIR):
        return out
    for fn in os.listdir(PROJCACHE_DIR):
        if not fn.endswith('.json') or fn.startswith(('session-', '_')):
            continue
        out.append(inspect_session(fn[:-5]))
    return out


def _norm_owner(owner):
    owner = str(owner or '')
    return owner if owner.startswith('sg-') else 'sg-' + owner


def _match_child(entry, children):
    """按 preset + 创建时间窗匹配子代理；同步骤多笔时取最新创建的一笔。"""
    owner = _norm_owner(entry.get('owner'))
    started_ms = None
    at = entry.get('at')
    if at:
        try:
            started_ms = int(datetime.strptime(at, '%Y-%m-%dT%H:%M:%S+08:00').timestamp() * 1000)
        except Exception:
            started_ms = None
    cands = [c for c in children if c['preset'] == owner]
    if started_ms:
        cands = [c for c in cands if c['created_ms'] is None or c['created_ms'] >= started_ms - 60000]
    if not cands:
        return None
    cands.sort(key=lambda c: c['created_ms'] or 0)
    return cands[-1]


def _load_trace(trace_id):
    """读台账：SQLite 优先，JSON 快照兜底。"""
    try:
        import trace_db
        conn = trace_db.connect()
        obj = trace_db.load_trace(conn, trace_id) if trace_id else None
        conn.close()
        if obj:
            return obj
    except Exception:
        obj = None
    if trace_id:
        return _load_json(os.path.join(TRACE_DIR, f'{trace_id}.json'))
    latest = _load_json(os.path.join(TRACE_DIR, '_latest.json'))
    if latest:
        return _load_json(os.path.join(TRACE_DIR, f"{latest['trace_id']}.json"))
    return None


def scan_trace(trace_id=None, persist=True):
    """扫描台账各派发步骤的子代理终态，回写 state/error/retries 快照。

    不重算覆盖率与违规清单（归 report 命令）；只补终态与可读错误。
    返回 (obj, rows)。
    """
    obj = _load_trace(trace_id)
    if not obj:
        raise SystemExit('❌ 未找到活动 trace 台账')
    children = _list_child_sessions()
    rows = []
    matched_ids = set()
    for e in obj.get('dispatched', []):
        child = _match_child(e, children)
        if child is None:
            row = {'step': e.get('step'), 'owner': _norm_owner(e.get('owner')),
                   'state': 'unknown', 'error': '', 'session_id': None}
        else:
            matched_ids.add(child['session_id'])
            row = {
                'step': e.get('step'),
                'owner': _norm_owner(e.get('owner')),
                'state': child['state'],
                'reason': child['reason'],
                'error': child['error'],
                'error_history': child['error_history'],
                'session_id': child['session_id'],
                'last_ms': child['last_ms'],
                'response': child['response'],
            }
            # 回写台账条目（保留既有耗时/产物字段）
            e['state'] = child['state']
            e['reason'] = child['reason']
            e['error'] = child['error']
            e['error_history'] = child['error_history']
            e['session_id'] = child['session_id']
            e.setdefault('retries', 0)
            if child['state'] in ('error', 'aborted', 'stalled'):
                e['needs_retry'] = e['retries'] < MAX_RETRIES
            else:
                e['needs_retry'] = False
        rows.append(row)

    # 孤儿会话：台账未登记但实际派生过的子代理（如主理人 dispose 前补派后未 mark）。
    # 非 completed 的孤儿单独留痕，避免已死会话被漏判。按本链路时间窗过滤，排除父会话自身。
    start_ms = _parse_ms(obj.get('started') or obj.get('at'))
    matched_last = [c['last_ms'] for c in children if c['session_id'] in matched_ids and c['last_ms']]
    upper_ms = (max(matched_last) + 15 * 60 * 1000) if matched_last else None
    orphans = []
    for c in children:
        if c['session_id'] in matched_ids:
            continue
        preset = str(c['preset'] or '')
        if preset.endswith('-lead') or preset == 'data-warehouse-brain-team-lead':
            continue
        if start_ms and c['created_ms'] and c['created_ms'] < start_ms - 60000:
            continue
        if upper_ms and c['created_ms'] and c['created_ms'] > upper_ms:
            continue
        if c['state'] in ('error', 'aborted', 'stalled'):
            orphans.append({
                'session_id': c['session_id'], 'preset': c['preset'],
                'state': c['state'], 'error': c['error'],
                'error_history': c['error_history'],
            })
    obj['orphan_sessions'] = orphans

    if persist:
        _persist(obj)
    return obj, rows


def _persist(obj):
    os.makedirs(TRACE_DIR, exist_ok=True)
    json.dump(obj, open(os.path.join(TRACE_DIR, f"{obj['trace_id']}.json"), 'w',
                        encoding='utf-8'), ensure_ascii=False, indent=2)
    try:
        import trace_db
        conn = trace_db.connect()
        trace_db.upsert_trace(conn, obj, now_ts=now())
        conn.commit()
        conn.close()
    except Exception as e:  # noqa: BLE001
        print(f'⚠️  SQLite 写入失败（JSON 快照已保留）: {serialize_error(e)}')


# ---------------------------------------------------------------------------
# 降级收尾（根治项 3）
# ---------------------------------------------------------------------------
def _stage_files(trace_id):
    """扫描各阶段目录中文件名含 trace_id 的产物。"""
    products = []
    for stage, directory in STAGE_DIRS.items():
        if not os.path.isdir(directory):
            continue
        for path in glob.glob(os.path.join(directory, f'*{trace_id}*')):
            if os.path.isfile(path):
                st = os.stat(path)
                products.append({
                    'stage': stage,
                    'path': os.path.relpath(path, PKG),
                    'bytes': st.st_size,
                    'mtime': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%dT%H:%M:%S+08:00'),
                })
    products.sort(key=lambda p: (p['stage'], p['path']))
    return products


def degrade_finalize(trace_id=None, yes=False):
    """终止 / 降级前扫描已落盘产物，写降级清单，并把可用图表 HTML 兜底复制到 report 目录。"""
    obj, rows = scan_trace(trace_id, persist=False)
    tid = obj['trace_id']
    products = _stage_files(tid)

    error_steps = [r for r in rows if r['state'] in ('error', 'aborted', 'stalled', 'unknown')]
    done_steps = [r for r in rows if r['state'] == 'completed']
    orphans = obj.get('orphan_sessions', [])
    missing = [s for s in obj.get('expected_steps', [])
               if not any(r['step'] == s and r['state'] == 'completed' for r in rows)]

    # 兜底复制：analysis 下的图表 HTML 复制到 report 目录（不覆盖既有同名文件）
    fallback_copies = []
    os.makedirs(REPORT_DIR, exist_ok=True)
    for p in products:
        if p['stage'] == 'analysis' and p['path'].lower().endswith('.html'):
            src = os.path.join(PKG, p['path'])
            dst = os.path.join(REPORT_DIR, os.path.basename(src))
            if not os.path.exists(dst):
                shutil.copy2(src, dst)
                fallback_copies.append(os.path.relpath(dst, PKG))

    manifest = {
        'trace_id': tid,
        'generated_at': now(),
        'mode': 'degrade_finalize',
        'summary': {
            'completed': len(done_steps),
            'error_or_stalled': len(error_steps) + len(orphans),
            'missing_expected': missing,
            'product_count': len(products),
            'report_present': any(p['stage'] == 'report' for p in products),
        },
        'error_steps': [
            {'step': r['step'], 'owner': r['owner'], 'state': r['state'],
             'error': r['error'], 'session_id': r.get('session_id')}
            for r in error_steps
        ] + [
            {'step': None, 'owner': o['preset'], 'state': o['state'],
             'error': o['error'], 'session_id': o['session_id'], 'orphan': True}
            for o in orphans
        ],
        'products': products,
        'fallback_copies': fallback_copies,
        'note': '本清单为降级收尾快照：已落盘产物保持不可变；缺失步骤须按 parallel_coordination §4 单路补派，'
                '禁止重跑全链路；未校准口径与假 0 约束沿用 quality 闸门结论。',
    }
    os.makedirs(DEGRADE_DIR, exist_ok=True)
    mpath = os.path.join(DEGRADE_DIR, f'degrade_manifest_{tid}.json')
    manifest['degrade_manifest'] = os.path.relpath(mpath, PKG)
    json.dump(manifest, open(mpath, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

    obj['verdict'] = '降级交付（部分产物）'
    obj['degraded_at'] = now()
    obj['degrade_manifest'] = os.path.relpath(mpath, PKG)
    _persist(obj)
    return manifest


def _print_scan(rows):
    print('=' * 62)
    print(f'{"Step":<6}{"专家":<28}{"终态":<10}{"错误 / 说明"}')
    print('-' * 62)
    for r in rows:
        err = r.get('error') or ''
        print(f'{str(r["step"]):<6}{r["owner"]:<28}{r["state"]:<10}{err[:40]}')
    print('=' * 62)


def main():
    ap = argparse.ArgumentParser(description='子代理终态看门狗 / 降级收尾')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p1 = sub.add_parser('scan', help='扫描子代理终态并回写台账')
    p1.add_argument('--trace-id', default=None)
    p1.add_argument('--json', action='store_true', help='只输出 JSON')
    p2 = sub.add_parser('degrade', help='扫描已有产物并写降级清单')
    p2.add_argument('--trace-id', default=None)
    p2.add_argument('--yes', action='store_true')
    a = ap.parse_args()

    if a.cmd == 'scan':
        obj, rows = scan_trace(a.trace_id)
        if a.json:
            print(json.dumps({'trace_id': obj['trace_id'], 'rows': rows},
                             ensure_ascii=False, indent=2))
        else:
            _print_scan(rows)
        return 0
    if a.cmd == 'degrade':
        manifest = degrade_finalize(a.trace_id, yes=a.yes)
        print(f'✅ 降级清单已写: {manifest["degrade_manifest"] if "degrade_manifest" in manifest else ""}')
        print(f'   已完成 {manifest["summary"]["completed"]} 步，异常/停滞 {manifest["summary"]["error_or_stalled"]} 步，'
              f'产物 {manifest["summary"]["product_count"]} 份')
        if manifest['fallback_copies']:
            print('   兜底复制: ' + ', '.join(manifest['fallback_copies']))
        return 0
    return 1


if __name__ == '__main__':
    sys.exit(main())
