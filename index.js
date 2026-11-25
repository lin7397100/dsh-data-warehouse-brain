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

export const name = 'dwb-team';
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
    } else {
      console.error('[dwb-team] webServer 服务不可用，未挂载面板路由');
    }
  } catch (error) {
    try { console.error('[dwb-team] 路由注册失败', error); } catch (_) {}
  }

  ctx.effect(function () {
    return function () { if (typeof disposeRoutes === 'function') disposeRoutes(); };
  }, 'dwb-team: dispose');

  return { name: name };
}
