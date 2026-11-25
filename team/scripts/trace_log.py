# -*- coding: utf-8 -*-
"""trace_log.py — 派发覆盖率记录器（阶段3 · 失败信号基础设施）

用法：
  # 任务开始时初始化
  python trace_log.py init --task-type T3 --fast-lane false \
         --expected 0.5a,0.5b,2,3,4,5,6,7,8

  # 每完成一步记录
  python trace_log.py mark --step 0.5a --dispatched sg-ontology

  # 任务结束时报告 + 写 health.json
  python trace_log.py report [--violations "内联Step2,内联Step5"]

输出：observed/traces/<trace_id>.json + 控制台覆盖率报告
退出码：0 = 覆盖率达标；1 = 未达标（调度违规）
"""

import argparse
import json
import os
import sys
from datetime import datetime

import trace_db
import subagent_watchdog as wd

# 强制 UTF-8 输出：Windows GBK 控制台打印 emoji/中文会 UnicodeEncodeError 崩退出码 1，
# 导致 health-check / init / mark 各失败一轮再靠手动 PYTHONUTF8 重试（2026-11-19 复盘）。
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(BASE)
TRACE_DIR = os.path.join(PKG, 'observed', 'traces')
SUPER_DIR = os.path.join(PKG, 'knowledge', 'design', 'supervision')
LATEST = os.path.join(TRACE_DIR, '_latest.json')

# 各任务类型的覆盖率阈值
THRESHOLDS = {
    'T1': 0.80,   # 快车道：5 位专家（0.5a/0.5b/0.6/0.7/0.8）
    'T2': 0.70,
    'T3': 0.70,
    'T4': 0.70,
    'T5': 0.70,
}

# 主链路步骤 → 指定执行者（与 agents/references/subagent_dispatch.md 映射表一致）
# Step 0.5 = sg-ontology（鼎元）+ sg-semantic（铨度）并行；拆分后 0.5a=ontology、0.5b=semantic。
STEP_EXPERT = {
    '0.5a': 'sg-ontology', '0.5b': 'sg-semantic',
    '2': 'sg-semantic', '3': 'sg-semantic', '4': 'sg-development',
    '5': 'sg-governance', '6': 'sg-development', '7': 'sg-quality', '8': 'sg-insight',
}

# 步骤辅助专家（并行扇出的次级角色，不计入主责错派；归一覆盖率与产物衔接仍按主责考核）
STEP_AUX = {
    '8': {'sg-zhishu-dashboard-designer', 'sg-zhishu-report-composer'},
}

# Q1-Q5 别名自动映射（2026-11-03 · 方案2优化：避免参数硬报错→手动修正→重试的往返）
TASK_TYPE_ALIASES = {
    'Q1': 'T1', 'Q2': 'T2', 'Q3': 'T3', 'Q4': 'T4', 'Q5': 'T5',
}


def now():
    return datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')


def gen_trace_id():
    return 'TR-' + datetime.now().strftime('%Y%m%d-%H%M') + '-' + os.urandom(2).hex().upper()


def ensure_dirs():
    os.makedirs(TRACE_DIR, exist_ok=True)
    os.makedirs(SUPER_DIR, exist_ok=True)


def load(path):
    try:
        return json.load(open(path, encoding='utf-8'))
    except Exception:
        return None


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(obj, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)


def persist(path, obj):
    """混合落库：JSON 快照（兜底/调试）+ SQLite 权威台账。DB 失败不阻断 JSON 快照。"""
    save(path, obj)
    try:
        conn = trace_db.connect()
        trace_db.upsert_trace(conn, obj, now_ts=now())
        conn.commit()
        conn.close()
    except Exception as e:  # noqa: BLE001
        print(f'⚠️  SQLite 写入失败（JSON 快照已保留）: {e}')


def cmd_init(args):
    # 方案2：Q1-Q5 别名自动映射（2026-11-03）
    if args.task_type in TASK_TYPE_ALIASES:
        mapped = TASK_TYPE_ALIASES[args.task_type]
        print(f'📝 自动映射: {args.task_type} → {mapped}')
        args.task_type = mapped

    ensure_dirs()
    tid = args.trace_id or gen_trace_id()
    expected = [s.strip() for s in args.expected.split(',') if s.strip()]
    lane = getattr(args, 'lane', 'T2a')
    obj = {
        'trace_id': tid,
        'started': now(),
        'task_type': args.task_type,
        'lane': lane,
        'fast_lane': lane == 'fast',
        'expected_steps': expected,
        'dispatched': [],       # [{"step":"0.5a","owner":"sg-ontology","at":"..."}]
        'inline_steps': [],     # ["1","-2"]
        'violations': [],
        'finished': None,
        'coverage_rate': None,
        'verdict': None,
    }
    persist(os.path.join(TRACE_DIR, f'{tid}.json'), obj)
    save(LATEST, {'trace_id': tid})
    print(f'✅ trace 已初始化: {tid}')
    print(f'   类型={args.task_type}  lane={lane}  预期步骤={len(expected)} 个')
    print(f'   路径: observed/traces/{tid}.json')
    return 0


def _cur():
    """读取当前最新的 trace（SQLite 优先，缺失时回退 JSON 快照）。"""
    latest = load(LATEST)
    if not latest:
        return None, None
    tid = latest['trace_id']
    path = os.path.join(TRACE_DIR, f'{tid}.json')
    try:
        conn = trace_db.connect()
        obj = trace_db.load_trace(conn, tid)
        conn.close()
        if obj:
            return obj, path
    except Exception:
        obj = None
    return load(path), path


def cmd_mark(args):
    obj, path = _cur()
    if not obj:
        print('❌ 未找到活动 trace，请先执行 init')
        return 1
    if args.dispatched:
        entry = {
            'step': args.step,
            'owner': args.dispatched,
            'at': now(),
            'started_at': None,
            'finished': None,
            'finished_at': None,
            'backfill_at': None,
            'duration_s': None,
            'duration_pure_s': None,
            'status': 'started',
            'artifact': None,
        }
        obj['dispatched'].append(entry)
        print(f'✅ 已记录派发: Step {args.step} → {args.dispatched}')
    else:
        obj['inline_steps'].append(args.step)
        print(f'⚠️  已记录内联: Step {args.step}（非派发）')
    _recompute(obj)
    persist(path, obj)
    return 0


def _parse_ts(s):
    try:
        return datetime.strptime(s, '%Y-%m-%dT%H:%M:%S+08:00')
    except Exception:
        return None


def _epoch_ms(dt):
    return int(dt.timestamp() * 1000) if dt else None


def _iso_from_ms(ms):
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000).strftime('%Y-%m-%dT%H:%M:%S+08:00')


SESS_DIR = os.path.join(os.path.expanduser('~'), '.dsh', 'storages',
                        'session_projcache', 'sessions')


def _load_child_sessions():
    """扫描子代理会话缓存，返回 [{child_id, preset, created_ms, last_ms, response,
    settled, state, reason, error}]。

    终态判定走 subagent_watchdog（解析 projcache + 转录 zstd 的 turn/end）：
    completed / error / aborted / stalled / running。旧口径 settled 仅作为 completed
    的兼容别名保留；error/aborted 是终态，不再被永久计入 running。
    """
    out = []
    if not os.path.isdir(SESS_DIR):
        return out
    for fn in os.listdir(SESS_DIR):
        if not fn.endswith('.json') or fn.startswith('session-') or fn.startswith('_'):
            continue
        child_id = fn[:-5]
        try:
            info = wd.inspect_session(child_id)
            out.append({
                'child_id': child_id,
                'preset': info['preset'],
                'created_ms': info['created_ms'],
                'last_ms': info['last_ms'],
                'response': info['response'],
                'settled': info['state'] == 'completed',
                'state': info['state'],
                'reason': info['reason'],
                'error': info['error'],
                'error_history': info.get('error_history', []),
            })
        except Exception:
            continue
    return out


def _reap(obj, children=None, persist_after=True):
    """回收子代理步骤，回填纯执行时长、终态与可读错误快照。

    终态识别（2026-11-19 根治项 1/2）：
      - completed：正常收尾，status=done；
      - error：回合以错误终止（如 PI_AI_ERROR 流式异常），status=failed，落可读错误快照，
        记 needs_retry（重试预算 MAX_RETRIES，由 watchdog 常量对齐）；
      - aborted：被父会话 dispose / parent 终止，status=dropped；
      - stalled / running：未到终态，保留进行中；stalled 单列标记，避免被永久误判为在跑。

    返回 (reaped, running) 计数；失败/终止计入 reaped（已回收，不再空等）。
    """
    children = children if children is not None else _load_child_sessions()
    reaped, running = 0, 0
    now_ts = now()
    for e in obj.get('dispatched', []):
        owner = str(e.get('owner') or '')
        owner = owner if owner.startswith('sg-') else 'sg-' + owner
        started_epoch = _epoch_ms(_parse_ts(e.get('at')))
        cands = [c for c in children
                 if c['preset'] == owner and c['created_ms']
                 and (started_epoch is None or c['created_ms'] >= started_epoch - 60000)]
        if not cands:
            if not e.get('finished'):
                running += 1
            continue
        cands.sort(key=lambda c: c['created_ms'])
        child = cands[-1]  # 同步骤重试后取最新一轮会话

        # 历史台账补纯执行时长：已收尾但缺 started_at / duration_pure_s，只补时间字段，
        # 不覆盖 finished / backfill_at / 既有状态。
        if e.get('finished'):
            if e.get('duration_pure_s') is None and child['created_ms'] and child['last_ms']:
                e['started_at'] = e.get('started_at') or _iso_from_ms(child['created_ms'])
                e['finished_at'] = e.get('finished_at') or _iso_from_ms(child['last_ms'])
                e['duration_pure_s'] = max(0, round((child['last_ms'] - child['created_ms']) / 1000))
            continue

        state = child['state']
        if state == 'running' or state == 'unknown':
            running += 1
            continue
        if state == 'stalled':
            e['state'] = 'stalled'
            e['reason'] = child['reason']
            running += 1
            continue

        # 终态：completed / error / aborted 都回填收尾时间，不再空等
        e['started_at'] = _iso_from_ms(child['created_ms'])
        e['finished_at'] = _iso_from_ms(child['last_ms'])
        e['finished'] = now_ts
        e['backfill_at'] = now_ts
        if started_epoch and child['last_ms']:
            e['duration_s'] = max(0, round((child['last_ms'] - started_epoch) / 1000))
        if child['created_ms'] and child['last_ms']:
            e['duration_pure_s'] = max(0, round((child['last_ms'] - child['created_ms']) / 1000))
        e['state'] = state
        e['reason'] = child['reason']
        e['error'] = child['error']
        e['error_history'] = child.get('error_history', [])
        e['session_id'] = child['child_id']
        e.setdefault('retries', 0)

        if state == 'completed':
            if e.get('status') in (None, 'started'):
                e['status'] = 'done'
            if not e.get('artifact') and child['response']:
                e['artifact'] = child['response'][:300]
        elif state == 'error':
            e['status'] = 'failed'
            e['needs_retry'] = e['retries'] < wd.MAX_RETRIES
        elif state == 'aborted':
            e['status'] = 'dropped'
            e['needs_retry'] = e['retries'] < wd.MAX_RETRIES
        reaped += 1
    return reaped, running


def cmd_finish(args):
    """专家回执收尾：回填某一步的完成时间、耗时、状态与产物摘要。"""
    obj, path = _cur()
    if not obj:
        print('❌ 未找到活动 trace，请先执行 init')
        return 1
    entries = obj.get('dispatched', [])
    idx = None
    for i in range(len(entries) - 1, -1, -1):
        e = entries[i]
        if e.get('step') != args.step:
            continue
        if not args.owner or e.get('owner') == args.owner:
            idx = i
            break
    if idx is None:
        print(f'❌ dispatched 中未找到 Step {args.step}' + (f' / {args.owner}' if args.owner else ''))
        return 1
    e = entries[idx]
    finished = now()
    e['finished'] = finished
    e['finished_at'] = finished
    e['backfill_at'] = finished
    started = _parse_ts(e.get('at'))
    ended = _parse_ts(finished)
    if started and ended:
        e['duration_s'] = max(0, round((ended - started).total_seconds()))
    pure_start = _parse_ts(e.get('started_at'))
    if pure_start and ended:
        e['duration_pure_s'] = max(0, round((ended - pure_start).total_seconds()))
    e['status'] = args.status or 'done'
    if args.artifact:
        e['artifact'] = args.artifact.strip()[:300]
    _recompute(obj)
    persist(path, obj)
    dur = f'{e["duration_s"]}s' if e.get('duration_s') is not None else '—'
    print(f'✅ 已收尾: Step {e["step"]} → {e["owner"]}（{e["status"]}，耗时 {dur}）')
    return 0


def cmd_reap(args):
    """回收已收尾子代理：自动回填 finished/纯执行时长/产物，不依赖主理人手动 finish。"""
    if getattr(args, 'trace_id', None):
        path = os.path.join(TRACE_DIR, f'{args.trace_id}.json')
        obj = None
        try:
            conn = trace_db.connect()
            obj = trace_db.load_trace(conn, args.trace_id)
            conn.close()
        except Exception:
            obj = None
        if obj is None:
            obj = load(path)
    else:
        obj, path = _cur()
    if not obj:
        print('❌ 未找到活动 trace')
        return 1
    children = _load_child_sessions()
    reaped, running = _reap(obj, children=children)
    # 回填后整体重算覆盖率/裁定/违规，避免台账停留「0% / 全未派发」陈旧快照，
    # 同时按当前派发重建违规清单，清掉空台账首轮写入的残留未派发记录（2026-11-20 复盘）
    _recompute(obj)
    persist(path, obj)
    print(f'♻️  回执回收: 自动收尾 {reaped} 步，仍在执行 {running} 步')
    for e in obj['dispatched']:
        if e.get('finished'):
            pure = f'｜纯执行 {e.get("duration_pure_s")}s' if e.get('duration_pure_s') is not None else ''
            err = f'｜错误: {e.get("error")}' if e.get('error') else ''
            print(f'     - Step {e["step"]} → {e["owner"]} [{e.get("status")}] 墙钟 {e.get("duration_s")}s{pure}{err}')
        else:
            state = e.get('state') or '进行中'
            print(f'     - Step {e["step"]} → {e["owner"]} [{state}]')
    return 0


def _norm_owner(o):
    return str(o) if str(o).startswith('sg-') else 'sg-' + str(o)


def _compute_coverage(obj):
    """计算严格口径与专家归一覆盖率；同步骤多笔派发按「任一笔命中即命中」展开。

    返回 hit / absent / wrong / miss / coverage / hit_norm / coverage_norm。
    报告与回收器共用，避免回填后覆盖率仍是陈旧快照（2026-11-19 复盘）。
    """
    exp = obj.get('expected_steps') or []
    by_step = {}
    for d in obj.get('dispatched', []):
        by_step.setdefault(d.get('step'), []).append(d)

    hit, absent, wrong = [], [], []
    for s in exp:
        cands = by_step.get(s) or []
        exp_id = STEP_EXPERT.get(s)
        if not cands:
            absent.append(s)
            continue
        if exp_id and not any(
            _norm_owner(d.get('owner', '')) == exp_id
            or _norm_owner(d.get('owner', '')) in STEP_AUX.get(s, set())
            for d in cands
        ):
            wrong.append(s)
        else:
            hit.append(s)
    miss = absent + wrong
    coverage = len(hit) / len(exp) if exp else 0

    owner_set = {_norm_owner(d.get('owner', '')) for d in obj['dispatched'] if d.get('owner')}
    hit_norm = [s for s in exp if STEP_EXPERT.get(s) and STEP_EXPERT[s] in owner_set]
    coverage_norm = len(hit_norm) / len(exp) if exp else 0
    return {
        'hit': hit, 'absent': absent, 'wrong': wrong, 'miss': miss,
        'coverage': coverage, 'hit_norm': hit_norm, 'coverage_norm': coverage_norm,
    }


def _recompute(obj, extras=None):
    """按当前派发状态整体重算覆盖率、裁定与违规清单（report/reap/mark/finish 共用）。

    违规清单整体重建：旧快照里的「未派发/错派」残留随本次计算清除，不再累积
    （2026-11-20 复盘：空台账首轮 report 写入的 9 条未派发，在后续派发收尾后
    因 reap/finish/mark 不重建违规而一直残留，面板误报全量未派发）。

    extras：命令行显式传入的外部归因违规（仅 report 透传）。
    返回 _compute_coverage 的结果字典。
    """
    extras = extras or []
    cov = _compute_coverage(obj)
    coverage, coverage_norm = cov['coverage'], cov['coverage_norm']

    base_type = obj.get('task_type')
    if base_type in ('T2a', 'T2b'):
        base_type = 'T2'
    threshold = THRESHOLDS.get(base_type, 0.70)
    finished = bool(obj.get('finished'))

    if obj.get('fast_lane'):
        # 快车道：0 专家派发是设计使然，不判调度违规
        obj['coverage_rate'] = 1.0
        obj['coverage_rate_norm'] = 1.0
        obj['verdict'] = '通过（快车道）'
    elif not finished:
        # 进行中快照：尚未轮到的步骤属「待派发」，不提前记违规、不下调度违规裁定；
        # 只有收尾 report（finished 落库）才对真正缺漏定罪（2026-11-23 复盘：
        # 运行中链路被中途快照判「调度违规」，Step4~8 实为还没走到）。
        obj['coverage_rate'] = round(coverage, 3)
        obj['coverage_rate_norm'] = round(coverage_norm, 3)
        obj['verdict'] = '进行中'
    else:
        passed = coverage >= threshold
        obj['coverage_rate'] = round(coverage, 3)
        obj['coverage_rate_norm'] = round(coverage_norm, 3)
        obj['verdict'] = '通过' if passed else '调度违规'

    # 自动归因违规：未派发（内联/跳过）与错派（到场但专家不符）分开记录。
    # 进行中链路的缺失步骤只列入 pending_steps（待派发），不进违规清单；
    # 已到场但专家不符的错派是既成事实，照常记录。
    inline_set = set(obj.get('inline_steps') or [])
    auto_violations = []
    pending = []
    for s in cov['absent']:
        if not finished:
            pending.append(s)
            continue
        if s in inline_set:
            auto_violations.append('Step %s 应由指定专家派发，被主理人内联执行' % s)
        else:
            auto_violations.append('Step %s 未派发指定专家（跳过/缺失）' % s)
    obj['pending_steps'] = pending
    for d in obj.get('dispatched', []):
        step, owner = d.get('step'), d.get('owner')
        exp_id = STEP_EXPERT.get(step)
        if not exp_id or not owner:
            continue
        if _norm_owner(owner) != exp_id and _norm_owner(owner) not in STEP_AUX.get(step, set()):
            auto_violations.append('Step %s 错派：派给 %s，应为 %s' % (step, owner, exp_id))
    obj['violations'] = list(dict.fromkeys(list(extras) + auto_violations))
    return cov


def cmd_report(args):
    if getattr(args, 'trace_id', None):
        path = os.path.join(TRACE_DIR, f'{args.trace_id}.json')
        obj = None
        try:
            conn = trace_db.connect()
            obj = trace_db.load_trace(conn, args.trace_id)
            conn.close()
        except Exception:
            obj = None
        if obj is None:
            obj = load(path)
        if not obj:
            print(f'❌ 未找到台账: {args.trace_id}')
            return 1
    else:
        obj, path = _cur()
    if not obj:
        print('❌ 未找到活动 trace')
        return 1

    # 报告前先自动回收已收尾子代理，避免回执未回填导致墙钟耗时失真
    _reap(obj)

    # 补充违规（命令行显式传入的外部归因）
    extras = [v.strip() for v in args.violations.split(',') if v.strip()] if args.violations else []

    # 收尾落库必须先于重算：report 是终态定罪点，finished 置位后缺失步骤才计违规；
    # 进行中快照（mark/finish/reap）不设 finished，缺失步骤只标待派发（2026-11-23 复盘）。
    obj['finished'] = now()

    exp = obj['expected_steps']
    cov = _recompute(obj, extras=extras)
    hit, absent, wrong = cov['hit'], cov['absent'], cov['wrong']
    miss = cov['miss']
    coverage = cov['coverage']
    hit_norm, coverage_norm = cov['hit_norm'], cov['coverage_norm']
    # T2a/T2b 归并到 T2 阈值；快车道不参与专家覆盖率考核
    base_type = obj['task_type']
    if base_type in ('T2a', 'T2b'):
        base_type = 'T2'
    threshold = THRESHOLDS.get(base_type, 0.70)
    passed = str(obj['verdict']).startswith('通过')
    persist(path, obj)

    # 写 health.json（累积）
    hp = os.path.join(SUPER_DIR, 'health.json')
    health = load(hp) or {'_meta': {'owner': 'sg-supervisor', 'version': '1.0.0'},
                          'traces': [], 'expert_stats': {}}
    # D8 健壮性：health.json 可能被外部写入且不含 _meta，直接下标会 KeyError
    health.setdefault('_meta', {'owner': 'sg-supervisor', 'version': '1.0.0'})['updated'] = now()
    # 🔧 P0 修复（2026-11-06）：按 trace_id 去重 upsert，避免同一 trace 多次 report 导致
    # health.json 记录虚高（曾出现 26 条记录 / 17 个唯一 trace_id，使 GATE-0 连续违规计数失真）
    _rec = {
        'trace_id': obj['trace_id'],
        'date': obj['started'][:10],
        'task_type': obj['task_type'],
        'fast_lane': obj['fast_lane'],
        'expert_dispatches': len(obj['dispatched']),
        'coverage_rate': obj['coverage_rate'],
        'violations': len(obj['violations']),
        'verdict': obj['verdict'],
    }
    _traces = health.setdefault('traces', [])
    _idx = next((i for i, t in enumerate(_traces)
                 if isinstance(t, dict) and t.get('trace_id') == _rec['trace_id']), None)
    if _idx is None:
        _traces.append(_rec)
    else:
        _traces[_idx] = _rec  # 同 trace 覆盖，不追加
    save(hp, health)

    # 控制台报告
    print('=' * 62)
    print(f'调度覆盖率报告 · {obj["trace_id"]}')
    print('=' * 62)
    print(f'  任务类型: {obj["task_type"]}　fast_lane: {obj["fast_lane"]}')
    print(f'  预期步骤: {len(exp)} 个 → {", ".join(exp)}')
    print(f'  正确命中: {len(hit)} 个 → {", ".join(hit) if hit else "无"}')
    for e in obj['dispatched']:
        dur = f'{e["duration_s"]}s' if e.get('duration_s') is not None else '—'
        art = f'｜产物: {e["artifact"]}' if e.get('artifact') else ''
        print(f'     - Step {e["step"]} → {e["owner"]} [{e.get("status", "started")}] {dur}{art}')
    print(f'  未命中  : {len(miss)} 个 → {", ".join(miss) if miss else "无"}')
    print(f'  内联步骤: {", ".join(obj["inline_steps"]) if obj["inline_steps"] else "无"}')
    print('-' * 62)
    if obj.get('fast_lane'):
        print('  覆盖率  : 快车道豁免（不考核专家派发）')
    else:
        print(f'  覆盖率  : 严格口径 {coverage:.1%}　专家归一 {coverage_norm:.1%}　（阈值 {threshold:.0%}）')
        print(f'  归一命中: {", ".join(hit_norm) if hit_norm else "无"}')
    if obj['violations']:
        print(f'  违规项  : {len(obj["violations"])} 条')
        for v in obj['violations']:
            print(f'     - {v}')
    print('-' * 62)
    print(f'  裁定    : {"✅ 通过" if passed else "❌ 调度违规"}')
    print('=' * 62)
    if not passed:
        print('⚠️  交付文本顶部必须披露此违规，并说明原因。')
    return 0 if passed else 1


def cmd_watch(args):
    """看门狗：扫描子代理终态（completed/error/aborted/stalled），回写台账错误快照。"""
    obj, rows = wd.scan_trace(args.trace_id)
    print(f'🐕 终态扫描 · {obj["trace_id"]}')
    for r in rows:
        err = f'｜{r["error"]}' if r.get('error') else ''
        hist = f'｜历史回合: {"; ".join(r.get("error_history") or [])}' if r.get('error_history') else ''
        print(f'     - Step {r["step"]} → {r["owner"]} [{r["state"]}]{err}{hist}')
    for o in obj.get('orphan_sessions', []):
        print(f'     - 孤儿 {o["preset"]} [{o["state"]}] {o["error"]}')
    return 0


def cmd_degrade(args):
    """降级收尾：扫描已落盘中间产物，写 degrade manifest 并兜底复制图表 HTML。"""
    manifest = wd.degrade_finalize(args.trace_id, yes=True)
    s = manifest['summary']
    print(f'🗂️  降级收尾 · {manifest["trace_id"]}')
    print(f'     已完成 {s["completed"]} 步，异常/停滞 {s["error_or_stalled"]} 步，产物 {s["product_count"]} 份')
    if manifest['fallback_copies']:
        print('     兜底复制: ' + ', '.join(manifest['fallback_copies']))
    return 0


def cmd_health_check(args):
    """GATE-0: 检查累积违规状态，返回退出码指示是否需强制派发"""
    hp = os.path.join(SUPER_DIR, 'health.json')
    health = load(hp)
    if not health or not health.get('traces'):
        print('✅ 健康：无历史违规记录')
        print('   → 正常流程，进入 GATE-1')
        return 0

    traces = health['traces']
    recent = traces[-5:]  # 最近 5 条

    # 门禁语义 = 「末尾连续违规数」，不能以「窗口内存在历史违规」直接判违规。
    # 2026-11-03 修复：此前即使最后一条已『通过』（连续链已打断），仍会落到
    # else 分支返回 exit 3 并打印「连续 0 次违规」，属误报。
    consecutive = 0
    for t in reversed(recent):
        if t['verdict'] != '通过':
            consecutive += 1
        else:
            break

    if consecutive == 0:
        print('✅ 健康：最近一条已通过，连续违规链已打断')
        print('   → 正常流程，进入 GATE-1（窗口内历史违规仅作留痕，不阻断）')
        return 0

    violations = [t for t in recent if t['verdict'] != '通过']
    print(f'⚠️  检测到违规记录：{len(violations)}/{len(recent)} 条')
    for v in violations:
        print(f'   - {v["trace_id"]}: coverage={v["coverage_rate"]} verdict={v["verdict"]}')

    if consecutive == 1:
        print('\n🔶 退出码 1：上次任务调度违规')
        print('   → 禁止内联执行 SQL，必须走完整 delegate_expert 派发')
        return 1
    elif consecutive == 2:
        print('\n🟠 退出码 2：连续 2 次违规')
        print('   → 必须先完成一次补救 delegate_expert 派发（≥3 专家），再开始当前任务')
        return 2
    else:
        print(f'\n🔴 退出码 3：连续 {consecutive} 次违规')
        print('   → 强制降级：当前任务禁止使用 DeferExecuteTool(mcp__db2__*)，SQL 必须经 Agent 派发')
        return 3


def cmd_gate_check(args):
    """GATE-2: 检查治理审查是否完成"""
    gate = args.gate
    obj, path = _cur()
    if not obj:
        print('❌ 未找到活动 trace，请先执行 GATE-1 init')
        return 1

    if gate == 'governance':
        # 检查是否已派发 sg-governance
        gov_dispatched = any(
            d.get('owner', '') == 'sg-governance'
            for d in obj.get('dispatched', [])
        )
        if gov_dispatched:
            print('✅ 治理审查已派发：sg-governance 在 dispatched 列表中')
            return 0
        else:
            print('❌ 治理审查未派发')
            print('   → 必须先派发 sg-governance 或运行 gate-check --gate governance 得 exit 0')
            print('   → 在此之前禁止任何 DeferExecuteTool(mcp__db2__execute_sql) 调用')
            return 1

    elif gate == 'dispatch':
        # 检查是否有任何专家被派发（非空 dispatched 列表）
        dispatched = obj.get('dispatched', [])
        if dispatched:
            owners = [d.get('owner', '?') for d in dispatched]
            print(f'✅ 已派发 {len(dispatched)} 位专家：{", ".join(owners)}')
            return 0
        else:
            print('❌ 未派发任何专家')
            print('   → 当前任务类型要求先派发再取数，禁止内联执行')
            return 1

    else:
        print(f'❌ 未知门禁类型：{gate}')
        return 1


def main():
    ap = argparse.ArgumentParser(description='派发覆盖率记录器')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p1 = sub.add_parser('init', help='初始化 trace')
    p1.add_argument('--task-type', default='T2', choices=['T1', 'T2', 'T2a', 'T2b', 'T3', 'T4', 'T5', 'Q1', 'Q2', 'Q3', 'Q4', 'Q5'])
    p1.add_argument('--lane', default='T2a', choices=['fast', 'T2a', 'T2b', 'trend', 'root_cause', 'root-cause', 'full'])
    p1.add_argument('--expected', default='0.5a,0.5b,2,3,4,5,6,7,8')
    p1.add_argument('--trace-id', default=None)

    p2 = sub.add_parser('mark', help='记录一步')
    p2.add_argument('--step', required=True)
    p2.add_argument('--dispatched', default=None, help='派发给谁；省略则记为内联')

    p2f = sub.add_parser('finish', help='回填某专家步骤的完成时间/耗时/产物')
    p2f.add_argument('--step', required=True)
    p2f.add_argument('--owner', default=None, help='专家 ID；省略则按 step 匹配最近一笔')
    p2f.add_argument('--artifact', default=None, help='产物摘要（≤300 字）')
    p2f.add_argument('--status', default='done', choices=['done', 'failed', 'blocked', 'dropped'])

    p3 = sub.add_parser('report', help='输出覆盖率报告')
    p3.add_argument('--violations', default=None)
    p3.add_argument('--trace-id', default=None, help='指定台账；省略则读 _latest.json 指针')

    p3r = sub.add_parser('reap', help='自动回收已收尾子代理回执并回填台账')
    p3r.add_argument('--trace-id', default=None, help='指定台账；省略则读 _latest.json 指针')

    pw = sub.add_parser('watch', help='看门狗：扫描子代理终态并回写错误快照')
    pw.add_argument('--trace-id', default=None)

    pd = sub.add_parser('degrade', help='降级收尾：扫描已有产物并写降级清单')
    pd.add_argument('--trace-id', default=None)

    p4 = sub.add_parser('health-check', help='GATE-0：健康自检')
    p5 = sub.add_parser('gate-check', help='GATE-2：门禁检查')
    p5.add_argument('--gate', required=True, choices=['governance', 'dispatch'], help='检查类型')

    a = ap.parse_args()
    handlers = {
        'init': cmd_init, 'mark': cmd_mark, 'finish': cmd_finish, 'report': cmd_report,
        'reap': cmd_reap, 'watch': cmd_watch, 'degrade': cmd_degrade,
        'health-check': cmd_health_check, 'gate-check': cmd_gate_check,
    }
    return handlers[a.cmd](a)


if __name__ == '__main__':
    sys.exit(main())
