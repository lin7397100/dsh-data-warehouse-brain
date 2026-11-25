// routes.js — 数仓智脑专家团面板 · 同源只读/覆盖层 API（host 半）
//
// 台账数据以 SQLite（observed/dwb_team.db）为权威存储，JSON 快照兜底/调试：
//   observed/dwb_team.db                        traces / trace_steps / violations / routes
//   observed/traces/*.json                      台账 JSON 快照（DB 缺失时回退）
//   observed/routes/*.json                      路由 JSON 快照（DB 缺失时回退）
// 其余静态数据仍来自 TeamRoot 下的本地文件，宿主不解析 YAML、不直连 DB2 / MCP：
//   panel/roster.json                          名册（tools/gen_roster.py 生成）
//   panel/overrides/<id>.json                  覆盖层备注（v1 只写备注，不改 patch）
//   knowledge/design/supervision/health.json   历史任务与专家派发统计（聚合快照）
//
// 失败一律回 200 + {ok:false,error}，不在宿主侧抛 500，避免面板空白。

import fs from 'node:fs/promises';
import fssync from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);

const PREFIX = '/dwb-team/api';
const MAX_BODY_BYTES = 256 * 1024;
const ID_RE = /^[A-Za-z0-9_-]{1,48}$/;

// 主链步骤 → 指定执行者（与 scripts/trace_log.py STEP_EXPERT 一致）
const STEP_EXPERT = {
  '0.5a': 'sg-ontology', '0.5b': 'sg-semantic',
  '2': 'sg-semantic', '3': 'sg-semantic', '4': 'sg-development',
  '5': 'sg-governance', '6': 'sg-development', '7': 'sg-quality', '8': 'sg-insight',
};

function normOwner(o) {
  const s = String(o || '');
  return s.startsWith('sg-') ? s : `sg-${s}`;
}

// 专家归属归一折算：step 号错位/合并多步只记一笔时，按「指定专家是否到场」再算一版覆盖率。
function normCoverage(expected, dispatched) {
  if (!expected || !expected.length) return null;
  const owners = new Set((dispatched || []).map((d) => normOwner(d.owner)).filter(Boolean));
  const hit = expected.filter((s) => STEP_EXPERT[s] && owners.has(STEP_EXPERT[s]));
  return +(hit.length / expected.length).toFixed(3);
}

// B 档白名单：仅 MCP 插件的三个标量可回写；其余（persona/结构/表达式/工具开关）只读。
const EDITABLE_KEYS = {
  serverName: 'string',
  toolCallTimeoutMs: 'number',
  url: 'url',
};

const PKG_DIR = path.dirname(fileURLToPath(import.meta.url));

function defaultTeamRoot() {
  const home = process.env.DSH_HOME || path.join(os.homedir(), '.dsh');
  return path.join(home, 'dwb-team');
}

function resolveRoot(config) {
  return (config && typeof config.teamRoot === 'string' && config.teamRoot.trim())
    ? config.teamRoot.trim()
    : defaultTeamRoot();
}

function resolvePatchPath(config) {
  if (config && typeof config.patchPath === 'string' && config.patchPath.trim()) {
    return config.patchPath.trim();
  }
  // 组合包自带 patch：写回只改包自己的声明，不碰用户 profile
  return path.join(PKG_DIR, 'cordis.patch.yml');
}

function resolvePython() {
  const candidates = [
    process.env.DSH_PYTHON,
    path.join(process.env.DSH_INSTALL_DIR || '', '..', 'runtime', 'primary-runtime',
      'dependencies', 'python', 'python.exe'),
    'python',
    'python3',
  ].filter(Boolean);
  for (const c of candidates) {
    try { if (fssync.existsSync(c)) return c; } catch (_) {}
  }
  return 'python';
}

function findPluginNode(tree, pluginId) {
  for (const n of (tree || [])) {
    if (n.id === pluginId) return n;
    if (n.group) {
      const child = (n.children || []).find((x) => x.id === pluginId);
      if (child) return child;
    }
  }
  return null;
}

function statFile(p) {
  try {
    const st = fssync.statSync(p);
    return { exists: true, size: st.size, mtimeMs: st.mtimeMs };
  } catch (_) {
    return { exists: false, size: 0, mtimeMs: 0 };
  }
}

async function readJsonSafe(filePath) {
  try {
    const text = await fs.readFile(filePath, 'utf8');
    return { ok: true, data: JSON.parse(text) };
  } catch (error) {
    return { ok: false, error: String((error && error.message) || error) };
  }
}

function listJson(dir) {
  return fs.readdir(dir, { withFileTypes: true })
    .then((entries) => entries.filter((e) => e.isFile() && e.name.toLowerCase().endsWith('.json')))
    .then((entries) => entries.map((e) => e.name))
    .catch(() => []);
}

async function readLatest(dir, limit) {
  const names = await listJson(dir);
  const full = names.map((n) => path.join(dir, n));
  const stats = await Promise.all(full.map((p) => fs.stat(p).catch(() => null)));
  const pairs = full.map((p, i) => ({ p, mtime: stats[i] ? stats[i].mtimeMs : 0 }))
    .filter((x) => x.mtime > 0)
    .sort((a, b) => b.mtime - a.mtime)
    .slice(0, limit);
  const out = [];
  for (const x of pairs) {
    const r = await readJsonSafe(x.p);
    if (r.ok) out.push(r.data);
  }
  return out;
}

async function readAll(dir) {
  const names = await listJson(dir);
  const out = [];
  for (const n of names) {
    const r = await readJsonSafe(path.join(dir, n));
    if (r.ok) out.push(r.data);
  }
  return out;
}

// 步骤号自然排序：0.5a < 0.5b < 2 < 3 …
function stepCmp(a, b) {
  const pa = String(a.step || '').split(/[.-]/);
  const pb = String(b.step || '').split(/[.-]/);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const x = pa[i] || '', y = pb[i] || '';
    const nx = Number(x), ny = Number(y);
    if (Number.isFinite(nx) && Number.isFinite(ny)) {
      if (nx !== ny) return nx - ny;
    } else if (x !== y) {
      return x < y ? -1 : 1;
    }
  }
  return 0;
}

// —— SQLite 台账只读层（DB 权威；缺失/异常时回退 JSON 快照）——
let _db = null;
let _dbTried = false;
let _DatabaseSync = null;
let _sqliteChecked = false;

function getSqlite() {
  if (_sqliteChecked) return _DatabaseSync;
  _sqliteChecked = true;
  try { _DatabaseSync = require('node:sqlite').DatabaseSync; }
  catch (error) { _DatabaseSync = null; console.error('[dwb-team-panel] node:sqlite 不可用，回退 JSON', error); }
  return _DatabaseSync;
}

function openDb(dbPath) {
  if (_db) return _db;
  if (_dbTried) return null;
  _dbTried = true;
  const DatabaseSync = getSqlite();
  if (!DatabaseSync) return null;
  try {
    if (!fssync.existsSync(dbPath)) return null;
    _db = new DatabaseSync(dbPath, { readOnly: true });
    return _db;
  } catch (error) {
    console.error('[dwb-team-panel] 打开台账库失败', error);
    return null;
  }
}

function parseJsonArr(s) {
  try { return s ? JSON.parse(s) : []; } catch (_) { return []; }
}

function parseJsonObj(s) {
  try { return s ? JSON.parse(s) : null; } catch (_) { return null; }
}

function dbChains(db) {
  const traceRows = db.prepare('SELECT * FROM traces').all();
  const routeRows = db.prepare('SELECT * FROM routes').all();
  const byRoute = {}, byTrace = {};
  routeRows.forEach((r) => { if (r && r.trace_id) byRoute[r.trace_id] = r; });
  traceRows.forEach((t) => { if (t && t.trace_id) byTrace[t.trace_id] = t; });
  const ids = Array.from(new Set([...Object.keys(byRoute), ...Object.keys(byTrace)]));
  const chains = ids.map((id) => {
    const r = byRoute[id] || null;
    const tr = byTrace[id] || null;
    const dispatched = tr
      ? db.prepare('SELECT step, owner, at, started_at, finished, finished_at, backfill_at, duration_s, duration_pure_s, status, artifact, state, reason, error, retries FROM trace_steps WHERE trace_id=?').all(id)
      : [];
    dispatched.sort(stepCmp);
    const violations = tr
      ? db.prepare('SELECT message FROM violations WHERE trace_id=? ORDER BY id').all(id).map((x) => x.message)
      : [];
    const started = (tr && tr.started) || (r && r.at) || null;
    const finished = (tr && tr.finished) || null;
    let duration_s = null;
    if (started && finished) {
      const d = (new Date(finished) - new Date(started)) / 1000;
      if (Number.isFinite(d)) duration_s = Math.round(d);
    }
    const jev = parseJsonObj(r && r.jev);
    return {
      trace_id: id,
      at: started, started, finished, duration_s,
      text: (r && r.text) || (tr && tr.text) || null,
      lane: (tr && tr.lane) || (r && r.lane) || null,
      task_type: (tr && tr.task_type) || (r && r.task_type) || null,
      fast_lane: tr ? !!tr.fast_lane : !!(r && r.fast_lane),
      source: (r && r.source) || null,
      agreement: (r && r.agreement) || null,
      jev,
      reasons: parseJsonArr(r && r.reasons),
      expected_steps: parseJsonArr(tr && tr.expected_steps),
      dispatched,
      inline_steps: parseJsonArr(tr && tr.inline_steps),
      violations,
      coverage_rate: tr ? tr.coverage_rate : null,
      coverage_rate_norm: tr ? (tr.coverage_rate_norm ?? normCoverage(parseJsonArr(tr && tr.expected_steps), dispatched)) : null,
      verdict: tr ? tr.verdict : null,
      degraded_at: tr ? tr.degraded_at : null,
      degrade_manifest: tr ? tr.degrade_manifest : null,
      orphan_sessions: parseJsonArr(tr && tr.orphan_sessions),
      has_trace: !!tr,
    };
  });
  chains.sort((a, b) => String(b.at || '').localeCompare(String(a.at || '')));
  return chains;
}

function dbRecentRoutes(db, limit) {
  const rows = db.prepare('SELECT * FROM routes ORDER BY at DESC LIMIT ?').all(limit);
  return rows.map((r) => ({
    trace_id: r.trace_id, at: r.at, lane: r.lane, task_type: r.task_type,
    source: r.source, agreement: r.agreement,
    confidence: r.confidence, text: r.text, reasons: parseJsonArr(r.reasons),
  }));
}

function sendJson(response, status, payload) {
  if (response.headersSent) { try { response.end(); } catch (_) {} return; }
  response.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
  });
  response.end(JSON.stringify(payload));
}

async function readJsonBody(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > MAX_BODY_BYTES) throw new Error('请求体过大（上限 256 KiB）');
    chunks.push(chunk);
  }
  const text = Buffer.concat(chunks).toString('utf8').trim();
  if (!text) return {};
  return JSON.parse(text);
}

function gate(connection, request, response) {
  if (!connection || typeof connection.requestRejection !== 'function') return false;
  let rejection;
  try { rejection = connection.requestRejection(request); } catch (_) { rejection = 403; }
  if (rejection === undefined) return false;
  sendJson(response, rejection, { ok: false, error: rejection === 401 ? '需要登录后再操作' : '请求来源不可信' });
  return true;
}

export function registerRoutes(webServer, connection, config, services) {
  if (!webServer || typeof webServer.register !== 'function') {
    throw new Error('webServer 服务不可用');
  }
  const root = resolveRoot(config);
  const disposers = [];
  const registry = (services && services.agentPresets) || null;

  const rosterPath = path.join(root, 'panel', 'roster.json');
  const overrideDir = path.join(root, 'panel', 'overrides');
  const healthPath = path.join(root, 'knowledge', 'design', 'supervision', 'health.json');
  const routesDir = path.join(root, 'observed', 'routes');
  const tracesDir = path.join(root, 'observed', 'traces');
  const dbPath = path.join(root, 'observed', 'dwb_team.db');
  const avatarDir = path.join(path.dirname(fileURLToPath(import.meta.url)), 'assets', 'avatars');

  async function loadRoster() {
    const r = await readJsonSafe(rosterPath);
    if (!r.ok) return { agents: [], meta: {} };
    return r.data;
  }

  function route(routePath, methods, handle) {
    const full = PREFIX + routePath;
    const handler = async function (request, response) {
      if (gate(connection, request, response)) return;
      const method = String(request.method || 'GET').toUpperCase();
      if (methods.indexOf(method) < 0) {
        sendJson(response, 405, { ok: false, error: '不支持的请求方法：' + method });
        return;
      }
      try {
        const body = (method === 'GET' || method === 'HEAD') ? {} : await readJsonBody(request);
        const result = await handle({
          method, body,
          url: new URL('http://local' + (request.url || '/')),
          request, response,
        });
        sendJson(response, 200, result);
      } catch (error) {
        sendJson(response, 400, { ok: false, error: String((error && error.message) || error) });
      }
    };
    const dispose = webServer.register({ kind: 'exact', path: full, handler });
    disposers.push(dispose);
    return dispose;
  }

  // 名册
  route('/roster', ['GET'], async () => {
    const roster = await loadRoster();
    // 列表只回摘要；完整配置树经 /agent 单取，避免把 380KB 人设全量推给浏览器
    const agents = (roster.agents || []).map(function (a) {
      var lean = Object.assign({}, a);
      delete lean.config_tree;
      return lean;
    });
    const leanRoster = Object.assign({}, roster, { agents });
    const overrides = await listJson(overrideDir).then((ns) => ns.map((n) => n.replace(/\.json$/, '')));
    return { ok: true, root, roster: leanRoster, overrides };
  });

  // 团队根 / 供给状态：专家排障与面板展示都用得到
  route('/root', ['GET'], async () => {
    const s = services || {};
    let prov = null;
    try {
      prov = s.provision ? await s.provision() : null;
    } catch (error) {
      prov = { error: String((error && error.message) || error) };
    }
    return {
      ok: true,
      root,
      packageDir: s.packageDir || PKG_DIR,
      patchPath: resolvePatchPath(config),
      rosterExists: fssync.existsSync(rosterPath),
      provision: prov,
    };
  });

  // 专家头像缩略图（96x96 PNG）；缺头像的 preset 回退 team.png
  route('/avatar', ['GET'], async (ctx) => {
    const id = String(ctx.url.searchParams.get('id') || '');
    if (!ID_RE.test(id)) {
      sendJson(ctx.response, 400, { ok: false, error: '非法头像标识' });
      return { _done: true };
    }
    let file = path.join(avatarDir, id + '.png');
    if (!fssync.existsSync(file)) file = path.join(avatarDir, 'team.png');
    if (!fssync.existsSync(file)) {
      sendJson(ctx.response, 404, { ok: false, error: '头像缺失' });
      return { _done: true };
    }
    const buf = await fs.readFile(file);
    ctx.response.writeHead(200, {
      'content-type': 'image/png',
      'cache-control': 'public, max-age=86400',
      'content-length': buf.length,
    });
    ctx.response.end(buf);
    return { _done: true };
  });

  // 运行时注册表诊断：读宿主 agentPresets 服务，返回每个 preset 的 broken 原因（加载失败行/报错）
  route('/registry', ['GET'], async () => {
    if (!registry || typeof registry.list !== 'function') {
      return { ok: false, error: 'agentPresets 注册表服务不可用（未注入或作用域不可见）', presets: [] };
    }
    const presets = await registry.list();
    return { ok: true, presets: presets || [] };
  });

  // 单专家详情（名册 + 覆盖层）；id 走 query，避免 exact 路由不支持路径参数
  route('/agent', ['GET'], async (ctx) => {
    const id = String(ctx.url.searchParams.get('id') || '');
    if (!ID_RE.test(id)) throw new Error('非法专家 id');
    const roster = await loadRoster();
    const agent = (roster.agents || []).find((a) => a.id === id) || null;
    const ov = await readJsonSafe(path.join(overrideDir, id + '.json'));
    return { ok: true, agent, override: ov.ok ? ov.data : null };
  });

  // 运行概览：健康台账 + 最近路由 + 最近 trace
  route('/overview', ['GET'], async () => {
    const health = await readJsonSafe(healthPath);
    const db = openDb(dbPath);
    let routes = null;
    if (db) {
      try { routes = dbRecentRoutes(db, 8); } catch (error) { routes = null; }
    }
    if (!routes) routes = await readLatest(routesDir, 8);
    const traces = await readLatest(tracesDir, 10);

    const h = health.ok ? health.data : null;
    const healthTraces = (h && h.traces) || [];
    const recent = healthTraces.slice(-10).reverse();
    const latencies = recent.map((t) => Number(t.latency_s)).filter((n) => Number.isFinite(n));
    const coverage = recent.map((t) => Number(t.coverage_rate)).filter((n) => Number.isFinite(n));
    const summary = {
      total_traces: healthTraces.length,
      recent_n: recent.length,
      avg_latency_s: latencies.length ? +(latencies.reduce((a, b) => a + b, 0) / latencies.length).toFixed(1) : null,
      avg_coverage: coverage.length ? +(coverage.reduce((a, b) => a + b, 0) / coverage.length).toFixed(3) : null,
      over_target: recent.filter((t) => t.over_target).length,
      alerts: (h && h.alerts) || [],
      aggregate: (h && h.aggregate) || null,
      expert_stats: (h && h.expert_stats) || {},
    };

    const home = os.homedir();
    const bridges = {
      superagent: {
        stateDir: path.join(home, '.dsh', 'state', 'superagent'),
        db: statFile(path.join(home, '.dsh', 'state', 'superagent', 'orchestrator.sqlite')),
        note: 'prototype 持久化工单库；运行时子会话派发以 health.json 为准'
      },
      dag: {
        dataDir: path.join(home, '.dsh', 'super-router'),
        orders: statFile(path.join(home, '.dsh', 'super-router', 'orders.json')),
        note: '旧 super-router DAG 落盘目录；未接入时为空'
      },
      jev: {
        url: process.env.JEV_URL || 'http://10.233.2.32:11434/v1/systemone',
        model: process.env.JEV_MODEL || 'tev1:4b-32k'
      }
    };

    return {
      ok: true,
      root,
      sources: {
        roster: fssync.existsSync(rosterPath),
        health: health.ok,
        routes_dir: fssync.existsSync(routesDir),
        traces_dir: fssync.existsSync(tracesDir),
        db: fssync.existsSync(dbPath),
      },
      bridges,
      summary,
      recent_traces: recent,
      recent_routes: routes.map((r) => ({
        trace_id: r.trace_id, at: r.at, lane: r.lane, task_type: r.task_type,
        source: r.source, agreement: r.agreement,
        confidence: r.confidence != null ? r.confidence : (r.jev && r.jev.confidence),
        text: r.text, reasons: r.reasons,
      })),
      recent_traces_files: traces,
    };
  });

  // 调度链路看板：按 trace_id（每次会话请求）分组，关联路由判定 + 派发台账
  route('/chains', ['GET'], async () => {
    const db = openDb(dbPath);
    if (db) {
      try {
        const chains = dbChains(db);
        if (chains.length) return { ok: true, chains };
      } catch (error) {
        console.error('[dwb-team-panel] 台账库读取失败，回退 JSON', error);
      }
    }
    const [routeList, traceList] = await Promise.all([readAll(routesDir), readAll(tracesDir)]);
    const byRoute = {}, byTrace = {};
    routeList.forEach((r) => { if (r && r.trace_id) byRoute[r.trace_id] = r; });
    traceList.forEach((x) => { if (x && x.trace_id) byTrace[x.trace_id] = x; });
    const ids = Array.from(new Set([...Object.keys(byRoute), ...Object.keys(byTrace)]));
    const chains = ids.map((id) => {
      const r = byRoute[id] || null;
      const tr = byTrace[id] || null;
      const dispatched = ((tr && tr.dispatched) || []).slice().sort(stepCmp);
      const started = (tr && tr.started) || (r && r.at) || null;
      const finished = (tr && tr.finished) || null;
      let duration_s = null;
      if (started && finished) {
        const d = (new Date(finished) - new Date(started)) / 1000;
        if (Number.isFinite(d)) duration_s = Math.round(d);
      }
      return {
        trace_id: id,
        at: started,
        started, finished, duration_s,
        text: (r && r.text) || null,
        lane: (tr && tr.lane) || (r && r.lane) || null,
        task_type: (tr && tr.task_type) || (r && r.task_type) || null,
        fast_lane: tr ? !!tr.fast_lane : !!(r && r.fast_lane),
        source: (r && r.source) || null,
        agreement: (r && r.agreement) || null,
        jev: (r && r.jev) || null,
        reasons: (r && r.reasons) || [],
        expected_steps: (tr && tr.expected_steps) || [],
        dispatched,
        inline_steps: (tr && tr.inline_steps) || [],
        violations: (tr && tr.violations) || [],
        coverage_rate: tr ? tr.coverage_rate : null,
        coverage_rate_norm: tr ? (tr.coverage_rate_norm ?? normCoverage((tr && tr.expected_steps) || [], dispatched)) : null,
        verdict: (tr && tr.verdict) || null,
        has_trace: !!tr,
      };
    });
    chains.sort((a, b) => String(b.at || '').localeCompare(String(a.at || '')));
    return { ok: true, chains };
  });

  // 覆盖层写回（v1：仅备注/展示名覆盖，不回写 patch YAML）
  route('/override', ['POST'], async (ctx) => {
    const body = ctx.body || {};
    const id = String(body.id || '');
    if (!ID_RE.test(id)) throw new Error('非法专家 id');
    const roster = await loadRoster();
    if (!(roster.agents || []).some((a) => a.id === id)) throw new Error('名册中不存在该专家：' + id);

    const override = {
      id,
      saved_at: new Date().toISOString(),
      note: typeof body.note === 'string' ? body.note.slice(0, 2000) : '',
      display_name: typeof body.display_name === 'string' ? body.display_name.slice(0, 80) : '',
    };
    await fs.mkdir(overrideDir, { recursive: true });
    await fs.writeFile(path.join(overrideDir, id + '.json'), JSON.stringify(override, null, 2), 'utf8');
    return { ok: true, override };
  });

  // B 档 · 配置草案：把白名单标量的拟改值存到覆盖层（pending_config），不触碰 patch。
  route('/config-draft', ['POST'], async (ctx) => {
    const body = ctx.body || {};
    const id = String(body.id || '');
    if (!ID_RE.test(id)) throw new Error('非法专家 id');
    const roster = await loadRoster();
    const agent = (roster.agents || []).find((a) => a.id === id);
    if (!agent) throw new Error('名册中不存在该专家：' + id);

    const draft = (body.pending_config && typeof body.pending_config === 'object') ? body.pending_config : {};
    const cleaned = {};
    for (const [plugin, kv] of Object.entries(draft)) {
      if (!ID_RE.test(plugin) || !String(plugin).startsWith('mcp-')) continue;
      const node = findPluginNode(agent.config_tree, plugin);
      if (!node) continue;
      cleaned[plugin] = {};
      for (const [key, value] of Object.entries(kv || {})) {
        if (!EDITABLE_KEYS[key]) continue;
        cleaned[plugin][key] = String(value == null ? '' : value).slice(0, 300);
      }
      if (!Object.keys(cleaned[plugin]).length) delete cleaned[plugin];
    }

    const prev = await readJsonSafe(path.join(overrideDir, id + '.json'));
    const override = Object.assign({}, prev.ok ? prev.data : {}, {
      id,
      saved_at: new Date().toISOString(),
      pending_config: cleaned,
    });
    await fs.mkdir(overrideDir, { recursive: true });
    await fs.writeFile(path.join(overrideDir, id + '.json'), JSON.stringify(override, null, 2), 'utf8');
    return { ok: true, override };
  });

  // B 档 · 应用单条白名单标量到 live patch：备份 → 行级替换 → 容错解析校验 → 失败回滚。
  // 仅 MCP 插件的 serverName / toolCallTimeoutMs / url 兜底地址；改完需重启 DSH 生效。
  route('/config-apply', ['POST'], async (ctx) => {
    const body = ctx.body || {};
    const id = String(body.id || '');
    const plugin = String(body.plugin || '');
    const key = String(body.key || '');
    const value = String(body.value == null ? '' : body.value);
    if (!ID_RE.test(id)) throw new Error('非法专家 id');
    if (!ID_RE.test(plugin)) throw new Error('非法插件 id');
    if (!String(plugin).startsWith('mcp-')) throw new Error('B 档仅允许修改 MCP 插件标量');
    if (!EDITABLE_KEYS[key]) throw new Error('白名单外的键：' + key);
    if (value.length > 300) throw new Error('值过长');

    const roster = await loadRoster();
    const agent = (roster.agents || []).find((a) => a.id === id);
    if (!agent) throw new Error('名册中不存在该专家：' + id);
    const node = findPluginNode(agent.config_tree, plugin);
    if (!node) throw new Error('插件不在该专家配置中：' + plugin);

    const patchPath = resolvePatchPath(config);
    const script = path.join(root, 'tools', 'patch_write_config.py');
    if (!fssync.existsSync(script)) throw new Error('回写脚本缺失：' + script);
    if (!fssync.existsSync(patchPath)) throw new Error('live patch 不存在：' + patchPath);

    const py = resolvePython();
    const res = spawnSync(py, [
      script, '--patch', patchPath, '--preset', id, '--plugin', plugin,
      '--key', key, '--value', value,
    ], { encoding: 'utf8', timeout: 30000 });

    const out = (res.stdout || '').trim();
    let parsed = { ok: false, error: '脚本无输出', stderr: (res.stderr || '').trim() };
    try { parsed = JSON.parse(out); } catch (_) { parsed = { ok: false, error: '脚本输出无法解析: ' + (out || (res.stderr || '').trim()) }; }
    if (res.status && res.status !== 0 && parsed.ok !== true) parsed.ok = false;
    parsed.patch_path = patchPath;
    return parsed;
  });

  return function disposeRoutes() {
    for (const dispose of disposers) { try { if (typeof dispose === 'function') dispose(); } catch (_) {} }
  };
}
