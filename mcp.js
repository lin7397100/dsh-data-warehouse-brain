// mcp.js —— 数仓智脑专家团 · MCP 托管与一键开关（Host 半）
//
// 为什么需要：preset 里的 mcp-client 行由 `disabled: !!js` 环境变量门控，
// 只在预设首次激活时求值一次，用户改不了也点不动。
// 本模块改用 dsh-mcp-manager 的运行时注册口子：
//   ctx.mcpManager.register(name, entry) → 返回幂等 disposer
//   dispose() 即刻断开并注销该服务器的全部工具（不重启、不占上下文）
// 开关状态持久化为 <团队根>/mcp-state.json，重启后按状态自动恢复。

import fsp from 'node:fs/promises';
import fs from 'node:fs';
import path from 'node:path';

// 四台内网 MCP：端点与超时与原先 preset 内的 mcp-client 行完全一致
export function serverCatalog(env) {
  const e = env || process.env;
  const bearer = (v) => (v ? { Authorization: 'Bearer ' + v } : undefined);
  return {
    weknora: {
      label: '知识库 WeKnora',
      purpose: '指标口径 / 表结构 / 过程源码检索（全团可用）',
      transport: 'streamable-http',
      url: e.SG_WEKNORA_MCP_URL || 'http://10.233.2.32:9080/mcp',
      headers: bearer(e.SG_WEKNORA_TOKEN),
      toolCallTimeoutMs: 60000,
      needsToken: !e.SG_WEKNORA_TOKEN,
    },
    db2: {
      label: '数仓 DB2',
      purpose: '取数主通道：execute_sql / list_tables / describe_table',
      transport: 'streamable-http',
      url: e.SG_DB2_MCP_URL || 'http://10.18.136.38:8765/mcp',
      toolCallTimeoutMs: 60000,
      needsToken: false,
    },
    eplat: {
      label: 'EPLAT 设计态',
      purpose: '5S 元数据：术语 / 四级指标 / 血缘 / 质量 / 安全 / API（只读 Oracle）',
      transport: 'streamable-http',
      url: e.SG_EPLAT_MCP_URL || 'http://10.18.136.38:8770/mcp',
      toolCallTimeoutMs: 120000,
      needsToken: false,
    },
    'wecom-group': {
      label: '企微群投递',
      purpose: '报表/报告发送到群聊',
      transport: 'streamable-http',
      url: e.SG_WECOM_GROUP_MCP_URL || 'http://10.18.136.38:8766/mcp',
      toolCallTimeoutMs: 60000,
      needsToken: false,
    },
    'wecom-user': {
      label: '企微个人投递',
      purpose: '报表/报告发送到个人',
      transport: 'streamable-http',
      url: e.SG_WECOM_USER_MCP_URL || 'http://10.18.136.38:8767/mcp',
      toolCallTimeoutMs: 60000,
      needsToken: false,
    },
  };
}

const STATE_FILE = 'mcp-state.json';

async function readState(root) {
  try {
    const txt = await fsp.readFile(path.join(root, STATE_FILE), 'utf8');
    const doc = JSON.parse(txt);
    return doc && typeof doc === 'object' ? doc : dict();
  } catch (_) {
    return dict();
  }
}

function dict() {
  return Object.create(null);
}

async function writeState(root, state) {
  await fsp.mkdir(root, { recursive: true });
  const target = path.join(root, STATE_FILE);
  const tmp = target + '.tmp';
  await fsp.writeFile(tmp, JSON.stringify(state, null, 2) + '\n', 'utf8');
  await fsp.rename(tmp, target);
}

/**
 * 创建 MCP 控制器：负责状态持久化、注册/注销、状态查询。
 * manager 为 null（profile 未挂载 dsh-mcp-manager）时只读、不可切换。
 */
export function createMcpControl({ root, getManager, log }) {
  const say = log || (() => {});
  const catalog = serverCatalog(process.env);
  const disposers = dict();
  let state = dict();

  function manager() {
    try {
      const m = typeof getManager === 'function' ? getManager() : getManager;
      return m && typeof m.register === 'function' ? m : null;
    } catch (_) {
      return null;
    }
  }

  function entryOf(name) {
    const c = catalog[name];
    if (!c) return null;
    const entry = { transport: c.transport, url: c.url, toolCallTimeoutMs: c.toolCallTimeoutMs };
    if (c.headers) entry.headers = c.headers;
    return entry;
  }

  function enable(name) {
    const m = manager();
    if (!m) throw new Error('当前 profile 未挂载 MCP 管理器（需要 dsh-web-app 的 mcp 行）');
    if (disposers[name]) return;
    const entry = entryOf(name);
    if (!entry) throw new Error('未知服务器：' + name);
    const dispose = m.register(name, entry);
    disposers[name] = typeof dispose === 'function' ? dispose : () => {};
    say('[dwb-team] MCP 已启用：' + name);
  }

  function disable(name) {
    const d = disposers[name];
    if (!d) return;
    delete disposers[name];
    try { d(); } catch (e) { say('[dwb-team] MCP 注销失败 ' + name + ': ' + (e && e.message)); }
    say('[dwb-team] MCP 已停用：' + name);
  }

  async function setEnabled(name, on) {
    if (!catalog[name]) throw new Error('未知服务器：' + name);
    if (on) enable(name); else disable(name);
    state[name] = !!on;
    await writeState(root, state);
    return view(name);
  }

  function statusOf(name) {
    const m = manager();
    if (!m || typeof m.list !== 'function') return { state: 'unavailable' };
    try {
      const rows = m.list() || [];
      const row = rows.find((r) => r && r.name === name);
      return row ? row.status : { state: 'disabled' };
    } catch (_) {
      return { state: 'unavailable' };
    }
  }

  function view(name) {
    const c = catalog[name];
    const st = statusOf(name);
    return {
      name,
      label: c.label,
      purpose: c.purpose,
      url: c.url,
      enabled: !!state[name],
      status: st,
      toolCount: st && st.state === 'connected' ? st.toolCount : 0,
      needsToken: !!c.needsToken,
    };
  }

  function list() {
    return Object.keys(catalog).map(view);
  }

  async function probe(name) {
    const m = manager();
    if (!m || typeof m.probe !== 'function') throw new Error('MCP 管理器不支持探活');
    const options = { timeoutMs: 20000, maxToolNames: 200 };
    return m.probe(name, options);
  }

  async function restart(name) {
    const m = manager();
    if (!m || typeof m.restart !== 'function') throw new Error('MCP 管理器不支持重建');
    await m.restart(name);
    return view(name);
  }

  async function restore() {
    state = await readState(root);
    if (!manager()) {
      say('[dwb-team] 未检测到 mcpManager，MCP 开关仅记录状态不生效');
      return { restored: [], skipped: Object.keys(state).filter((k) => state[k]) };
    }
    const restored = [];
    const skipped = [];
    for (const name of Object.keys(catalog)) {
      if (!state[name]) continue;
      try {
        enable(name);
        restored.push(name);
      } catch (e) {
        skipped.push(name);
        say('[dwb-team] 恢复 MCP 失败 ' + name + ': ' + (e && e.message));
      }
    }
    return { restored, skipped };
  }

  function disposeAll() {
    for (const name of Object.keys(disposers)) disable(name);
  }

  return { catalog, list, setEnabled, probe, restart, restore, disposeAll, view, stateOf: () => state };
}

/** 注册 /dwb-team/api/mcp* 路由（与主面板同一前缀与鉴权门）。 */
export function registerMcpRoutes({ webServer, connection, prefix, control, gate }) {
  const PREFIX = prefix || '/dwb-team/api';
  const disposers = [];

  function sendJson(res, status, payload) {
    const body = JSON.stringify(payload);
    res.writeHead(status, {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
      'content-length': Buffer.byteLength(body),
    });
    res.end(body);
  }

  function route(routePath, methods, handle) {
    const handler = async function (request, response) {
      if (gate && gate(request, response)) return;
      const method = String(request.method || 'GET').toUpperCase();
      if (methods.indexOf(method) < 0) {
        sendJson(response, 405, { ok: false, error: '不支持的请求方法：' + method });
        return;
      }
      try {
        let body = dict();
        if (method !== 'GET') {
          const chunks = [];
          for await (const chunk of request) chunks.push(chunk);
          const text = Buffer.concat(chunks).toString('utf8').trim();
          body = text ? JSON.parse(text) : dict();
        }
        const result = await handle({ method, body, url: new URL('http://local' + (request.url || '/')) });
        sendJson(response, 200, Object.assign({ ok: true }, result));
      } catch (error) {
        sendJson(response, 400, { ok: false, error: String((error && error.message) || error) });
      }
    };
    disposers.push(webServer.register({ kind: 'exact', path: PREFIX + routePath, handler }));
  }

  route('/mcp', ['GET'], async () => ({ servers: control.list() }));

  route('/mcp/toggle', ['POST'], async (ctx) => {
    const name = String(ctx.body.name || '');
    const on = !!ctx.body.on;
    const server = await control.setEnabled(name, on);
    return { server };
  });

  route('/mcp/probe', ['POST'], async (ctx) => {
    const name = String(ctx.body.name || '');
    const result = await control.probe(name);
    return { name, probe: result };
  });

  route('/mcp/restart', ['POST'], async (ctx) => {
    const name = String(ctx.body.name || '');
    return { server: await control.restart(name) };
  });

  return function dispose() {
    for (const d of disposers) {
      try { if (typeof d === 'function') d(); } catch (_) {}
    }
  };
}
