// index.js — 数仓智脑专家团 · 组合包宿主半
//
// 两件事，都只做一次或只读：
//   1. 团队根供给：把包内 skills/、agents/、team/tools、team/scripts、panel/roster.json
//      铺到 <团队根>（默认 $DSH_HOME/dwb-team），版本变化才重铺；不碰用户数据目录
//      （observed/ knowledge/ panel/overrides/ 一律不覆盖）。
//   2. 面板路由：把团队名册 / 概览 / 路由 / 链路折成同源 GET /dwb-team/api/*。
//
// 不连 DB2、不连 MCP、不做判定。

import fs from 'node:fs';
import fsp from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { registerRoutes } from './routes.js';
import { createMcpControl, registerMcpRoutes } from './mcp.js';

export const name = 'dwb-team';
// tools 用于主理人护栏（restrict mcp__*）；mcpManager 用于 MCP 一键开关。
// 两者都用 ctx.get() 可选取用，故 inject 只声明必需的服务，避免 profile 缺包时激活失败。
export const inject = ['webServer', 'connection'];

const PKG_DIR = path.dirname(fileURLToPath(import.meta.url));

function pkgVersion() {
  try {
    return JSON.parse(fs.readFileSync(path.join(PKG_DIR, 'package.json'), 'utf8')).version || '0';
  } catch (_) {
    return '0';
  }
}

export function resolveTeamRoot(config) {
  const custom = config && typeof config.teamRoot === 'string' ? config.teamRoot.trim() : '';
  if (custom) return custom;
  const home = process.env.DSH_HOME || path.join(os.homedir(), '.dsh');
  return path.join(home, 'dwb-team');
}

// 包内 → 团队根 的受管映射；只这些会被重铺，其余用户数据不动。
const OWNED = [
  ['skills', 'skills'],
  ['agents', 'agents'],
  ['team/tools', 'tools'],
  ['team/scripts', 'scripts'],
  ['panel/roster.json', 'panel/roster.json'],
];

async function copyFile(src, dst, stamp) {
  await fsp.mkdir(path.dirname(dst), { recursive: true });
  await fsp.copyFile(src, dst);
  try { await fsp.utimes(dst, stamp, stamp); } catch (_) {}
}

async function copyTree(src, dst, stamp) {
  const entries = await fsp.readdir(src, { withFileTypes: true });
  for (const e of entries) {
    const s = path.join(src, e.name);
    const d = path.join(dst, e.name);
    if (e.isDirectory()) {
      if (e.name === '__pycache__') continue;
      await copyTree(s, d, stamp);
    } else if (e.isFile()) {
      if (e.name.endsWith('.pyc')) continue;
      await copyFile(s, d, stamp);
    }
  }
}

async function provision(root) {
  const version = pkgVersion();
  const markerPath = path.join(root, '.dwb-version');
  let current = '';
  try { current = (await fsp.readFile(markerPath, 'utf8')).trim(); } catch (_) {}
  const stamp = new Date();
  if (current === version) return { root, version, provisioned: false };

  let copied = 0;
  for (const [from, to] of OWNED) {
    const src = path.join(PKG_DIR, from);
    if (!fs.existsSync(src)) continue;
    const dst = path.join(root, to);
    const stat = await fsp.stat(src);
    if (stat.isDirectory()) {
      await copyTree(src, dst, stamp);
      copied += 1;
    } else {
      await copyFile(src, dst, stamp);
      copied += 1;
    }
  }
  for (const dir of ['observed', 'knowledge', 'panel/overrides', 'logs', 'traces']) {
    await fsp.mkdir(path.join(root, dir), { recursive: true });
  }
  await fsp.writeFile(markerPath, version + '\n', 'utf8');
  return { root, version, provisioned: true, items: copied };
}

export function apply(ctx, config) {
  const cfg = config || {};
  const root = resolveTeamRoot(cfg);
  let disposeRoutes = null;
  let disposeMcpRoutes = null;

  // ---- MCP 托管：状态持久化 + 运行时注册（点开关即时生效）----
  const mcp = createMcpControl({
    root,
    getManager: function () {
      try { return ctx.get('mcpManager'); } catch (_) { return null; }
    },
    log: function (msg) { try { console.log(msg); } catch (e) { void e; } },
  });

  // 主理人护栏：只有主理人挂了 delegate_expert；在其 scope 里禁掉全部 mcp__* 全局工具。
  // 失败只记日志——绝不能因为护栏让 agent 创建失败。
  function guardLead(agent) {
    try {
      // 插件未声明 inject:['tools'] 时读取 ctx.tools 会抛
      // "cannot get property ... without inject"，必须走 ctx.get()
      let tools = null;
      try { tools = ctx.get('tools'); } catch (_) { tools = null; }
      if (!agent || !agent.ctx || !agent.ctx.tools || !tools) return;
      const defs = tools.definitions(agent) || [];
      const names = defs.map(function (d) { return d.name; });
      if (names.indexOf('delegate_expert') < 0) return;
      const mcpNames = names.filter(function (n) { return n.indexOf('mcp__') === 0; });
      if (!mcpNames.length) return;
      const lift = agent.ctx.tools.restrict({ deny: mcpNames });
      if (typeof agent.ctx.effect === 'function') {
        agent.ctx.effect(function () { return lift; }, 'dwb-team: 主理人屏蔽 mcp__*');
      }
      try { console.log('[dwb-team] 主理人已屏蔽 ' + mcpNames.length + ' 个 MCP 工具'); } catch (_) {}
    } catch (e) {
      try { console.log('[dwb-team] 主理人 MCP 护栏跳过：' + (e && e.message)); } catch (_) {}
    }
  }

  if (cfg.guardLead !== false) {
    try { ctx.on('agent/created', function (payload) { guardLead(payload && payload.agent); }); } catch (_) {}
  }

  // 供给失败不拖垮面板：路由仍然挂载，状态经 /api/root 暴露。
  const ready = provision(root).then(
    (r) => { ctx.__dwbProvision = r; return r; },
    (e) => {
      const failed = { root, provisioned: false, error: String((e && e.message) || e) };
      ctx.__dwbProvision = failed;
      try { console.error('[dwb-team] 团队根供给失败', e); } catch (_) {}
      return failed;
    },
  );

  try {
    const webServer = ctx.webServer;
    const connection = ctx.connection;
    let agentPresets = null;
    try { agentPresets = ctx.get('agentPresets'); } catch (_) { agentPresets = null; }
    if (webServer && typeof webServer.register === 'function') {
      disposeRoutes = registerRoutes(webServer, connection, Object.assign({ teamRoot: root }, cfg), {
        agentPresets,
        packageDir: PKG_DIR,
        provision: () => (ctx.__dwbProvision || { root }),
        whenReady: ready,
      });
      ctx.effect(function () { return disposeRoutes; }, 'dwb-team: routes');

      // MCP 开关路由（同前缀、同鉴权门）
      const connGate = function (request, response) {
        try {
          if (!connection || typeof connection.requestRejection !== 'function') return false;
          const rejection = connection.requestRejection(request);
          if (rejection === undefined) return false;
          const body = JSON.stringify({
            ok: false,
            error: rejection === 401 ? '需要登录后再操作' : '请求来源不可信',
          });
          response.writeHead(rejection, {
            'content-type': 'application/json; charset=utf-8',
            'content-length': Buffer.byteLength(body),
          });
          response.end(body);
          return true;
        } catch (_) {
          return false;
        }
      };
      disposeMcpRoutes = registerMcpRoutes({
        webServer,
        connection,
        prefix: '/dwb-team/api',
        control: mcp,
        gate: connGate,
      });
      ctx.effect(function () { return disposeMcpRoutes; }, 'dwb-team: mcp routes');

      // 团队根就绪后按持久化状态恢复 MCP
      ready.then(function () {
        return mcp.restore();
      }).catch(function (e) {
        try { console.log('[dwb-team] MCP 恢复失败：' + (e && e.message)); } catch (_) {}
      });
    } else {
      console.error('[dwb-team] webServer 服务不可用，未挂载面板路由');
    }
  } catch (error) {
    try { console.error('[dwb-team] 路由注册失败', error); } catch (_) {}
  }

  ctx.effect(function () {
    return function () {
      if (typeof disposeRoutes === 'function') disposeRoutes();
      if (typeof disposeMcpRoutes === 'function') disposeMcpRoutes();
      try { mcp.disposeAll(); } catch (_) {}
    };
  }, 'dwb-team: dispose');

  return { name: name };
}
