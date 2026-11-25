/* dwb-team-panel — 浏览器半（经典脚本，经 window.__ModuleLoader__.load 加载）。
 *
 * 侧边栏「数仓专家团」入口 + 主面板：名册 / 运行概览 / 路由记录。
 * 数据全部走同源 GET /dwb-team/api/*；不直连 DB2 / MCP。
 */
window.__ModuleLoader__.load({
  id: '@sansteel/dsh-data-warehouse-brain',
  factory(require) {
    'use strict';
    var module = { exports: {} };
    var exports = module.exports;
    Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' });

    var NS = 'dwbTeam';
    var API_BASE = '/dwb-team/api';
    var PANEL_ID = 'dwb-team-brain';

    var React = (function () {
      try { return require('react'); } catch (e1) {
        try { return require('React'); } catch (e2) { return null; }
      }
    })();
    if (!React) { console.error('[dwb-team-panel] react 不可用'); return module.exports; }
    var h = React.createElement;
    var useState = React.useState;
    var useEffect = React.useEffect;
    var useCallback = React.useCallback;

    function avatarUrl(id) {
      return API_BASE + '/avatar?id=' + encodeURIComponent(id || '');
    }
    function Avatar(props) {
      var size = props.size || 20;
      return h('img', {
        src: avatarUrl(props.id),
        width: size, height: size,
        alt: '',
        style: {
          borderRadius: '50%', objectFit: 'cover', flex: 'none',
          background: 'var(--dsw-alias-fill-tsp-secondary,#eeeeee)',
        },
        onError: function (e) { if (e && e.target) e.target.style.visibility = 'hidden'; },
      });
    }

    var DICT = {
      zh: {
        nav: '数仓专家团', title: '数仓智脑专家团', refresh: '刷新',
        tabRoster: '专家名册', tabOverview: '运行概览', tabRoutes: '路由记录', tabChains: '调度链路',
        groupLead: '主理人', groupExpert: '专家', groupFast: '快车道',
        desc: '职责描述', prefixLen: '人设字数', plugins: '挂接插件',
        tools: '内置工具', mcp: 'MCP 接口', mcpEndpoint: '服务端',
        skills: '专属技能', sharedSkill: '共享',
        note: '面板备注（覆盖层）', save: '保存备注', saved: '已保存', editName: '展示名覆盖',
        agents: '专家数', recentTasks: '近期任务', avgLatency: '平均耗时(s)',
        avgCoverage: '平均覆盖率', overTarget: '超 SLA', empty: '暂无数据',
        loadFailed: '数据加载失败', lane: '车道', source: '判定来源', confidence: '置信度',
        agreement: '一致性', taskType: '任务类型', verdict: '结论', violations: '违规',
        invocations: '调用', failures: '失败', status: '状态',
        broken: '加载失败', brokenReason: '失败原因', registryNote: '运行时诊断来自宿主注册表',
        readonly: '绑定以 patch 声明为准，面板暂不回写插件/MCP 开关',
        cfg: '配置详情', persona: '人设前缀', instructions: '指令限制',
        toolGroup: '工具隔离组', compactionGroup: '上下文压缩组',
        builtin: '内置工具与技能', mcpGroup: 'MCP 接口',
        isolate: '隔离策略', disabledExpr: '禁用条件', exprTag: '环境变量表达式',
        viewPrefix: '展开人设全文', cfgNote: '配置以 patch 声明为准，核心不提供运行时热覆盖：标量项（MCP 地址/超时/开关）经备份后回写 patch、重启生效；人设长文本与 DSL 结构请在 persona 文件中维护。',
        fieldServer: '服务名', fieldUrl: '兜底地址', fieldTimeout: '超时(ms)',
        saveDraft: '存为草案', applyPatch: '写入 patch', draftSaved: '草案已保存（未生效）',
        applied: '已写入 patch', applyFail: '写入失败', noChange: '没有待应用的改动',
        restartHint: '需完全退出 DSH（含托盘）重启后生效', applyMsg: '回写结果',
        chainTitle: '调度链路（台账）', chainEmpty: '暂无台账，任务启动后由 GATE-0 自动登记',
        chainBoard: '调度链路看板', chainRequest: '会话请求', chainSteps: '派发序列',
        chainInline: '内联步骤', chainExpected: '预期步骤', chainDuration: '耗时',
        chainRouteOnly: '仅有路由判定，尚无台账', chainNoTrace: '任务结束 report 后生成台账',
        chainStep: 'Step', chainOwner: '专家', chainReasons: '判定理由', chainViolations: '违规',
        chainMissing: '缺失/未派发（应到）',
        chainPending: '待派发（进行中）',
        chainCoverage: '覆盖率', chainCoverageNorm: '归一', chainStatus: '状态', chainArtifact: '产物', chainExpertTime: '专家耗时',
        stStarted: '进行中', stDone: '完成', stFailed: '失败', stBlocked: '阻塞', stDropped: '丢弃'
      },
      en: {
        nav: 'DWB Team', title: 'Data Warehouse Brain Team', refresh: 'Refresh',
        tabRoster: 'Roster', tabOverview: 'Overview', tabRoutes: 'Routes', tabChains: 'Dispatch chain',
        groupLead: 'Lead', groupExpert: 'Expert', groupFast: 'Fast lane',
        desc: 'Description', prefixLen: 'Persona chars', plugins: 'Plugins',
        tools: 'Built-in tools', mcp: 'MCP endpoints', mcpEndpoint: 'Server',
        skills: 'Skills', sharedSkill: 'shared',
        note: 'Panel note (override)', save: 'Save note', saved: 'Saved', editName: 'Display name override',
        agents: 'Agents', recentTasks: 'Recent tasks', avgLatency: 'Avg latency (s)',
        avgCoverage: 'Avg coverage', overTarget: 'Over SLA', empty: 'No data',
        loadFailed: 'Failed to load', lane: 'Lane', source: 'Source', confidence: 'Confidence',
        agreement: 'Agreement', taskType: 'Task type', verdict: 'Verdict', violations: 'Violations',
        invocations: 'Calls', failures: 'Failures', status: 'Status',
        broken: 'Failed to load', brokenReason: 'Reason', registryNote: 'Runtime diagnostic from host registry',
        readonly: 'Binding is declared in patch; panel does not write back plugin/MCP toggles',
        cfg: 'Configuration', persona: 'Persona prefix', instructions: 'Instruction limits',
        toolGroup: 'Tool isolation group', compactionGroup: 'Compaction group',
        builtin: 'Built-in tools & skills', mcpGroup: 'MCP endpoints',
        isolate: 'Isolation', disabledExpr: 'Disabled when', exprTag: 'Env expression',
        viewPrefix: 'Expand full persona', cfgNote: 'Config comes from patch; core has no runtime hot-overlay. Scalars (MCP URL/timeout/toggle) are written back to patch with a backup and take effect after restart; persona long text and DSL are maintained in the persona file.',
        fieldServer: 'Server name', fieldUrl: 'Fallback URL', fieldTimeout: 'Timeout (ms)',
        saveDraft: 'Save draft', applyPatch: 'Write to patch', draftSaved: 'Draft saved (not active)',
        applied: 'Written to patch', applyFail: 'Apply failed', noChange: 'No pending change',
        restartHint: 'Fully restart DSH (incl. tray) to take effect', applyMsg: 'Result',
        chainTitle: 'Dispatch chain (ledger)', chainEmpty: 'No ledger yet; GATE-0 registers it at task start',
        chainBoard: 'Dispatch chain board', chainRequest: 'Session request', chainSteps: 'Dispatch sequence',
        chainInline: 'Inline steps', chainExpected: 'Expected steps', chainDuration: 'Duration',
        chainRouteOnly: 'Route decision only, no ledger yet', chainNoTrace: 'Ledger is written after report',
        chainStep: 'Step', chainOwner: 'Expert', chainReasons: 'Reasons', chainViolations: 'Violations',
        chainMissing: 'Missing (expected)',
        chainPending: 'Pending (in flight)',
        chainCoverage: 'Coverage', chainCoverageNorm: 'norm', chainStatus: 'Status', chainArtifact: 'Artifact', chainExpertTime: 'Expert time',
        stStarted: 'running', stDone: 'done', stFailed: 'failed', stBlocked: 'blocked', stDropped: 'dropped'
      }
    };

    var STYLE_ID = 'dwb-team-brain/styles';
    var STYLE_CSS = [
      '.dwb-root{display:flex;flex-direction:column;height:100%;background:var(--dsw-alias-bg-base,#fff);color:var(--dsw-alias-label-primary,#1a1a1a);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}',
      '.dwb-header{display:flex;align-items:center;justify-content:space-between;padding:14px 20px;border-bottom:1px solid var(--dsw-alias-border-l1,#e5e5e5);background:var(--dsw-alias-bg-layer-1,#f7f7f8);flex-shrink:0}',
      '.dwb-header h2{margin:0;font-size:17px;font-weight:600}',
      '.dwb-btn{background:var(--dsw-alias-bg-layer-2,#ececef);border:1px solid var(--dsw-alias-border-l1,#e5e5e5);color:var(--dsw-alias-label-primary,#1a1a1a);padding:5px 12px;border-radius:6px;cursor:pointer;font-size:12px;font-weight:500}',
      '.dwb-btn:hover{opacity:.85}.dwb-btn:disabled{opacity:.5;cursor:not-allowed}',
      '.dwb-tabs{display:flex;gap:4px;padding:0 20px;border-bottom:1px solid var(--dsw-alias-border-l1,#e5e5e5);background:var(--dsw-alias-bg-layer-1,#f7f7f8);flex-shrink:0}',
      '.dwb-tab{padding:10px 14px;font-size:13px;color:var(--dsw-alias-label-secondary,#666);cursor:pointer;border-bottom:2px solid transparent}',
      '.dwb-tab.active{color:var(--dsw-alias-brand-primary,#2563eb);border-bottom-color:var(--dsw-alias-brand-primary,#2563eb);font-weight:600}',
      '.dwb-body{display:flex;flex:1;overflow:hidden}',
      '.dwb-list{width:230px;min-width:180px;border-right:1px solid var(--dsw-alias-border-l1,#e5e5e5);background:var(--dsw-alias-bg-layer-1,#f7f7f8);overflow-y:auto;flex-shrink:0}',
      '.dwb-list-group{padding:8px 12px 4px;font-size:11px;color:var(--dsw-alias-label-secondary,#888);letter-spacing:.04em}',
      '.dwb-item{padding:9px 14px;cursor:pointer;font-size:12.5px;border-left:3px solid transparent;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:flex;align-items:center;gap:2px}',
      '.dwb-item:hover{background:var(--dsw-alias-bg-layer-2,#ececef)}',
      '.dwb-item.active{background:var(--dsw-alias-bg-layer-2,#ececef);color:var(--dsw-alias-brand-primary,#2563eb);border-left-color:var(--dsw-alias-brand-primary,#2563eb);font-weight:600}',
      '.dwb-content{flex:1;overflow-y:auto;padding:16px 20px}',
      '.dwb-cards{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:16px}',
      '.dwb-card{border:1px solid var(--dsw-alias-border-l1,#e5e5e5);border-radius:10px;padding:12px 16px;min-width:130px;background:var(--dsw-alias-bg-layer-1,#f7f7f8)}',
      '.dwb-card .v{font-size:22px;font-weight:700}.dwb-card .k{font-size:11px;color:var(--dsw-alias-label-secondary,#888);margin-top:4px}',
      '.dwb-row{display:flex;gap:10px;padding:10px 0;border-bottom:1px solid var(--dsw-alias-border-l1,#eee);font-size:12.5px}',
      '.dwb-row:last-child{border-bottom:none}',
      '.dwb-label{min-width:96px;color:var(--dsw-alias-label-secondary,#888)}',
      '.dwb-chip{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:var(--dsw-alias-bg-layer-2,#ececef)}',
      '.dwb-textarea{width:100%;min-height:80px;border:1px solid var(--dsw-alias-border-l1,#e5e5e5);border-radius:8px;background:var(--dsw-alias-bg-base,#fff);color:var(--dsw-alias-label-primary,#1a1a1a);padding:8px 10px;font-size:12.5px;resize:vertical;font-family:inherit}',
      '.dwb-table{width:100%;border-collapse:collapse;font-size:12.5px}',
      '.dwb-table th,.dwb-table td{padding:8px 10px;border-bottom:1px solid var(--dsw-alias-border-l1,#eee);text-align:left;vertical-align:top}',
      '.dwb-table th{color:var(--dsw-alias-label-secondary,#888);font-weight:500;font-size:11.5px}',
      '.dwb-empty{display:flex;align-items:center;justify-content:center;height:100%;color:var(--dsw-alias-label-secondary,#888);font-size:13px;padding:20px}',
      '.dwb-err{padding:14px;color:var(--dsw-alias-state-error-primary,#d92d20);font-size:12.5px}',
      '.dwb-scroll{overflow-y:auto}',
      '.dwb-cfg{margin-top:14px;border-top:1px solid var(--dsw-alias-border-l1,#e5e5e5);padding-top:12px}',
      '.dwb-cfg-sec{margin-bottom:14px}',
      '.dwb-cfg-sec-title{font-size:12px;font-weight:600;margin-bottom:6px;opacity:.8}',
      '.dwb-cfg-group{border:1px solid var(--dsw-alias-border-l1,#e5e5e5);border-radius:8px;padding:8px 10px;margin:6px 0;background:var(--dsw-alias-bg-layer-1,#f7f7f8)}',
      '.dwb-cfg-leaf{padding:6px 0}',
      '.dwb-cfg-head{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:4px}',
      '.dwb-cfg-pkg{font-size:10.5px;color:var(--dsw-alias-label-secondary,#888)}',
      '.dwb-cfg-kv{display:flex;gap:8px;font-size:12px;margin:3px 0}',
      '.dwb-cfg-k{min-width:110px;color:var(--dsw-alias-label-secondary,#888)}',
      '.dwb-cfg-v{flex:1;word-break:break-all}',
      '.dwb-mono{font-family:ui-monospace,Consolas,monospace;font-size:11.5px}',
      '.dwb-cfg-empty{color:var(--dsw-alias-label-secondary,#888);font-size:11.5px}',
      '.dwb-cfg pre{white-space:pre-wrap;word-break:break-word;font-size:11.5px;background:var(--dsw-alias-bg-layer-1,#f7f7f8);border:1px solid var(--dsw-alias-border-l1,#e5e5e5);border-radius:8px;padding:10px;max-height:320px;overflow:auto}'
    ].join('\n');

    function injectStyles() {
      if (typeof document === 'undefined') return function () {};
      if (document.getElementById(STYLE_ID)) return function () {};
      var style = document.createElement('style');
      style.id = STYLE_ID;
      style.textContent = STYLE_CSS;
      document.head.appendChild(style);
      return function () { try { style.remove(); } catch (_) {} };
    }

    function makeTranslator(bound) {
      return function (key) {
        if (bound && typeof bound === 'function') {
          var v = bound(key);
          if (v && v !== key) return v;
        }
        var dict = DICT.zh[key];
        return dict != null ? dict : key;
      };
    }

    async function fetchJson(path, options) {
      var resp = await fetch(API_BASE + path, options || {});
      var data = await resp.json().catch(function () { return { ok: false, error: '响应不是 JSON' }; });
      return data;
    }

    function IconComp() {
      return h('svg', { viewBox: '0 0 24 24', width: 20, height: 20, fill: 'currentColor', 'aria-hidden': true, style: { display: 'block' } },
        h('path', { d: 'M12 12a3.5 3.5 0 1 0-3.5-3.5A3.5 3.5 0 0 0 12 12Zm-7 8a2.5 2.5 0 0 1 5 0v1h-5Zm14 0v1h-5v-1a2.5 2.5 0 0 1 5 0ZM12 14.5c-3.3 0-7 1.6-7 4V20h14v-1.5c0-2.4-3.7-4-7-4Z', opacity: '0.9' }));
    }

    // 主链路步骤 → 指定执行者（与 subagent_dispatch.md 映射表一致）
    var STEP_EXPERT = {
      '0.5a': 'sg-ontology', '0.5b': 'sg-semantic',
      '2': 'sg-semantic', '3': 'sg-semantic', '4': 'sg-development',
      '5': 'sg-governance', '6': 'sg-development', '7': 'sg-quality', '8': 'sg-insight'
    };

    function buildNameMap(agents) {
      var m = {};
      (agents || []).forEach(function (a) { if (a && a.id) m[a.id] = a.name || a.id; });
      return m;
    }

    function shortName(full) {
      if (!full) return full;
      var seg = String(full).split(' · ')[0];
      return seg.trim() || full;
    }

    // 派发台账里的 owner 可能是缺 sg- 前缀的短 slug，按名册补全并解析中文花名
    function resolveOwner(owner, nameMap) {
      if (!owner) return { id: owner, name: null };
      var id = owner;
      if (!nameMap[id] && String(id).indexOf('sg-') !== 0) {
        var alt = 'sg-' + id;
        if (nameMap[alt]) id = alt;
      }
      var nm = nameMap[id];
      return { id: id, name: nm ? shortName(nm) : null };
    }

    function Panel(props) {
      var t = (props && typeof props.t === 'function') ? props.t : makeTranslator(null);
      Object.assign(t, DICT.zh);
      var [roster, setRoster] = useState({ agents: [], meta: {} });
      var [overview, setOverview] = useState(null);
      var [chains, setChains] = useState([]);
      var [registry, setRegistry] = useState({ ok: false, presets: [] });
      var [tab, setTab] = useState('roster');
      var [activeId, setActiveId] = useState(null);
      var [agentDetail, setAgentDetail] = useState(null);
      var [note, setNote] = useState('');
      var [displayName, setDisplayName] = useState('');
      var [saved, setSaved] = useState(false);
      var [edits, setEdits] = useState({});
      var [applyMsg, setApplyMsg] = useState(null);
      var [loading, setLoading] = useState(true);
      var [error, setError] = useState('');

      var loadAll = useCallback(async function () {
        setLoading(true); setError('');
        try {
          var r = await fetchJson('/roster');
          if (r.ok) {
            setRoster(r.roster || { agents: [], meta: {} });
            var agents = (r.roster && r.roster.agents) || [];
            if (!activeId && agents.length) setActiveId(agents[0].id);
          } else { setError(r.error || t.loadFailed); }
          var o = await fetchJson('/overview');
          if (o.ok) setOverview(o); else if (!o.ok) setError(o.error || t.loadFailed);
          var g = await fetchJson('/registry');
          if (g.ok) setRegistry({ ok: true, presets: g.presets || [] }); else setRegistry({ ok: false, presets: [] });
          var c = await fetchJson('/chains');
          if (c.ok) setChains(c.chains || []); else setChains([]);
        } catch (e) { setError(String(e && e.message || e)); }
        setLoading(false);
      }, [activeId, t]);

      useEffect(function () { loadAll(); }, [loadAll]);

      useEffect(function () {
        if (!activeId) return;
        fetchJson('/agent?id=' + encodeURIComponent(activeId)).then(function (d) {
          if (d.ok) {
            setAgentDetail(d.agent);
            var ov = d.override || {};
            setNote(ov.note || '');
            setDisplayName(ov.display_name || '');
            var pending = ov.pending_config || {};
            var flat = {};
            Object.keys(pending).forEach(function (plugin) {
              Object.keys(pending[plugin] || {}).forEach(function (key) {
                flat[plugin + '/' + key] = pending[plugin][key];
              });
            });
            setEdits(flat);
            setApplyMsg(null);
            setSaved(false);
          }
        });
      }, [activeId]);

      var saveOverride = useCallback(async function () {
        if (!activeId) return;
        var r = await fetchJson('/override', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ id: activeId, note: note, display_name: displayName })
        });
        if (r.ok) setSaved(true); else setError(r.error || t.loadFailed);
      }, [activeId, note, displayName, t]);

      var EDITABLE_MCP_KEYS = ['serverName', 'url', 'toolCallTimeoutMs'];

      function editKey(plugin, key) { return plugin + '/' + key; }
      function currentVal(plugin, key, fallback) {
        var v = edits[editKey(plugin, key)];
        return v != null ? v : (fallback == null ? '' : String(fallback));
      }
      function setEdit(plugin, key, value) {
        setEdits(function (prev) { var n = Object.assign({}, prev); n[editKey(plugin, key)] = value; return n; });
        setApplyMsg(null);
      }

      var saveDraft = useCallback(async function (plugin) {
        var payload = {};
        EDITABLE_MCP_KEYS.forEach(function (key) {
          var v = edits[editKey(plugin, key)];
          if (v != null && v !== '') payload[key] = v;
        });
        var r = await fetchJson('/config-draft', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ id: activeId, pending_config: { [plugin]: payload } })
        });
        if (r.ok) setApplyMsg({ ok: true, text: t.draftSaved }); else setApplyMsg({ ok: false, text: r.error || t.loadFailed });
      }, [activeId, edits, t]);

      var applyPlugin = useCallback(async function (plugin) {
        var results = [];
        for (var i = 0; i < EDITABLE_MCP_KEYS.length; i++) {
          var key = EDITABLE_MCP_KEYS[i];
          var v = edits[editKey(plugin, key)];
          if (v == null || v === '') continue;
          var r = await fetchJson('/config-apply', {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ id: activeId, plugin: plugin, key: key, value: v })
          });
          results.push({ key: key, ok: r.ok, msg: r.error || '' });
        }
        var bad = results.filter(function (x) { return !x.ok; });
        if (bad.length) {
          setApplyMsg({ ok: false, text: t.applyFail + ': ' + bad.map(function (x) { return x.key + ' ' + x.msg; }).join('; ') });
        } else if (results.length) {
          setApplyMsg({ ok: true, text: t.applied + '。' + t.restartHint });
        } else {
          setApplyMsg({ ok: false, text: t.noChange });
        }
      }, [activeId, edits, t]);

      var agents = roster.agents || [];
      var brokenMap = {};
      (registry.presets || []).forEach(function (p) { if (p && p.broken) brokenMap[p.id] = p.broken; });
      var groups = [
        { key: 'lead', label: t.groupLead },
        { key: 'expert', label: t.groupExpert },
        { key: 'fast', label: t.groupFast }
      ];

      function renderList() {
        return groups.map(function (g) {
          var list = agents.filter(function (a) { return a.group === g.key; });
          if (!list.length) return null;
          return h('div', null,
            h('div', { className: 'dwb-list-group' }, g.label + ' · ' + list.length),
            list.map(function (a) {
              var broken = brokenMap[a.id];
              return h('div', {
                key: a.id,
                className: 'dwb-item' + (activeId === a.id ? ' active' : ''),
                onClick: function () { setActiveId(a.id); setSaved(false); }
              },
                h(Avatar, { id: a.id, size: 20 }),
                h('span', { style: { marginRight: 6, marginLeft: 6 } }, a.name || a.id),
                broken && h('span', { className: 'dwb-chip', style: { color: 'var(--dsw-alias-state-error-primary,#d92d20)', background: 'var(--dsw-alias-state-error-bg,#fef3f2)' } }, t.broken));
            })
          );
        });
      }

      function renderScalar(v) {
        if (v == null) return '—';
        if (typeof v === 'object') return h('span', { className: 'dwb-mono' }, JSON.stringify(v));
        var s = String(v);
        if (/process\.env|\?\?/.test(s)) {
          return h('span', null,
            h('span', { className: 'dwb-chip', style: { marginRight: 6 } }, t.exprTag),
            h('span', { className: 'dwb-mono' }, s));
        }
        return h('span', { className: 'dwb-mono' }, s);
      }

      function renderConfigObject(cfg) {
        var keys = Object.keys(cfg || {});
        if (!keys.length) return h('div', { className: 'dwb-cfg-empty' }, '—');
        return h('div', null, keys.map(function (k) {
          return h('div', { className: 'dwb-cfg-kv', key: k },
            h('span', { className: 'dwb-cfg-k' }, k),
            h('span', { className: 'dwb-cfg-v' }, renderScalar(cfg[k])));
        }));
      }

      function renderNode(n, depth) {
        if (!n) return null;
        var head = h('div', { className: 'dwb-cfg-head' },
          h('span', { className: 'dwb-chip' }, n.id || n.package),
          n.package && h('span', { className: 'dwb-cfg-pkg' }, n.package),
          n.disabled_expr && h('span', { className: 'dwb-chip', style: { color: '#b54708', background: '#fffaeb' } }, t.disabledExpr + ' ' + n.disabled_expr));
        if (n.group) {
          var iso = n.isolate && Object.keys(n.isolate).length
            ? h('div', { className: 'dwb-cfg-kv' }, h('span', { className: 'dwb-cfg-k' }, t.isolate),
              h('span', { className: 'dwb-mono' }, JSON.stringify(n.isolate)))
            : null;
          return h('div', { className: 'dwb-cfg-group', style: depth ? { marginLeft: 10 } : {} },
            head, iso,
            (n.children || []).map(function (c, i) { return renderNode(c, depth + 1); }));
        }
        return h('div', { className: 'dwb-cfg-leaf', style: depth ? { marginLeft: 10 } : {} }, head, renderConfigObject(n.config));
      }

      function renderConfigSection(title, nodes) {
        if (!nodes || !nodes.length) return null;
        return h('div', { className: 'dwb-cfg-sec' },
          h('div', { className: 'dwb-cfg-sec-title' }, title),
          nodes.map(function (n, i) { return renderNode(n, 0); }));
      }

      function renderMcpCard(node, summary) {
        var cfg = node.config || {};
        var urlFallback = (summary && summary.url) || '';
        function field(key, label, type) {
          var fallback = key === 'url' ? urlFallback : cfg[key];
          return h('div', { className: 'dwb-cfg-kv', key: key },
            h('span', { className: 'dwb-cfg-k' }, label),
            h('input', {
              className: 'dwb-textarea', style: { minHeight: 34 }, type: type || 'text',
              value: currentVal(node.id, key, fallback),
              onChange: function (e) { setEdit(node.id, key, e.target.value); }
            }));
        }
        var head = h('div', { className: 'dwb-cfg-head' },
          h('span', { className: 'dwb-chip' }, node.id || node.package),
          node.package && h('span', { className: 'dwb-cfg-pkg' }, node.package),
          node.disabled_expr && h('span', { className: 'dwb-chip', style: { color: '#b54708', background: '#fffaeb' } }, t.disabledExpr + ' ' + node.disabled_expr));
        return h('div', { className: 'dwb-cfg-group' }, head,
          field('serverName', t.fieldServer, 'text'),
          field('url', t.fieldUrl, 'text'),
          field('toolCallTimeoutMs', t.fieldTimeout, 'number'),
          h('div', { style: { display: 'flex', gap: 8, marginTop: 8, alignItems: 'center' } },
            h('button', { className: 'dwb-btn', onClick: function () { saveDraft(node.id); } }, t.saveDraft),
            h('button', { className: 'dwb-btn', onClick: function () { applyPlugin(node.id); } }, t.applyPatch)));
      }

      function renderConfigTree(tree, mcpByPlugin) {
        if (!tree || !tree.length) return h('div', { className: 'dwb-empty' }, t.empty);
        var personaNode = tree.find(function (n) { return n.id === 'persona'; });
        var instr = tree.find(function (n) { return n.id === 'agent-instructions'; });
        var groups = tree.filter(function (n) { return n.group; });
        var mcps = tree.filter(function (n) { return n.id && String(n.id).indexOf('mcp-') === 0; });
        var builtin = tree.filter(function (n) {
          return !n.group && n.id !== 'persona' && n.id !== 'agent-instructions' && String(n.id).indexOf('mcp-') !== 0;
        });
        var parts = [];
        if (personaNode) {
          var prefix = (personaNode.config && personaNode.config.prefix) || '';
          parts.push(h('div', { className: 'dwb-cfg-sec' },
            h('div', { className: 'dwb-cfg-sec-title' }, t.persona + ' · ' + prefix.length + ' 字'),
            h('details', null,
              h('summary', { style: { cursor: 'pointer', fontSize: 12 } }, t.viewPrefix),
              h('pre', null, prefix || '—'))));
        }
        if (instr) parts.push(renderConfigSection(t.instructions, [instr]));
        groups.forEach(function (g) {
          var title = g.id === 'compaction' ? t.compactionGroup : (g.id === 'shell' ? t.toolGroup : g.id);
          parts.push(renderConfigSection(title, [g]));
        });
        if (mcps.length) {
          parts.push(h('div', { className: 'dwb-cfg-sec' },
            h('div', { className: 'dwb-cfg-sec-title' }, t.mcpGroup),
            mcps.map(function (n) { return renderMcpCard(n, (mcpByPlugin || {})[n.id]); })));
        }
        if (builtin.length) parts.push(renderConfigSection(t.builtin, builtin));
        return h('div', { className: 'dwb-cfg' },
          h('div', { className: 'dwb-cfg-sec-title' }, t.cfg),
          parts,
          applyMsg && h('div', {
            style: { marginTop: 10, fontSize: 12, color: applyMsg.ok ? 'var(--dsw-alias-brand-primary,#2563eb)' : 'var(--dsw-alias-state-error-primary,#d92d20)' }
          }, t.applyMsg + '：' + applyMsg.text),
          h('div', { style: { fontSize: 11, color: 'var(--dsw-alias-label-secondary,#888)', marginTop: 10 } }, t.cfgNote));
      }

      function renderDetail() {
        var a = agentDetail;
        if (!a) return h('div', { className: 'dwb-empty' }, t.empty);
        var stats = (overview && overview.summary && overview.summary.expert_stats && overview.summary.expert_stats[a.id]) || null;
        var broken = brokenMap[a.id];
        var mcpList = a.mcp || [];
        var toolPlugins = (a.plugins || []).filter(function (p) { return String(p).indexOf('mcp-') !== 0; });
        return h('div', null,
          h('div', { style: { display: 'flex', alignItems: 'center', gap: 10, margin: '0 0 4px' } },
            h(Avatar, { id: a.id, size: 32 }),
            h('h2', { style: { margin: 0, fontSize: 16 } }, displayName || a.name)),
          h('div', { style: { fontSize: 12, color: 'var(--dsw-alias-label-secondary,#888)' } }, a.id),
          broken && h('div', { className: 'dwb-row' }, h('div', { className: 'dwb-label' }, t.brokenReason),
            h('div', { style: { flex: 1, color: 'var(--dsw-alias-state-error-primary,#d92d20)', whiteSpace: 'pre-wrap', fontSize: 12 } }, broken)),
          h('div', { className: 'dwb-row' }, h('div', { className: 'dwb-label' }, t.desc), h('div', null, a.description || '—')),
          h('div', { className: 'dwb-row' }, h('div', { className: 'dwb-label' }, t.prefixLen), h('div', null, String(a.prefix_len != null ? a.prefix_len : '—'))),
          h('div', { className: 'dwb-row' }, h('div', { className: 'dwb-label' }, t.tools),
            h('div', null, toolPlugins.map(function (p) { return h('span', { key: p, className: 'dwb-chip', style: { marginRight: 6 } }, p); }))),
          (a.skills && a.skills.length) ? h('div', { className: 'dwb-row' }, h('div', { className: 'dwb-label' }, t.skills),
            h('div', { style: { flex: 1 } }, a.skills.map(function (s) {
              return h('div', { key: s.id, style: { marginBottom: 6 } },
                h('span', { className: 'dwb-chip', style: { marginRight: 6 } }, s.id),
                s.shared && h('span', { style: { fontSize: 11, color: 'var(--dsw-alias-label-secondary,#888)', marginRight: 6 } }, '(' + t.sharedSkill + ')'),
                h('span', { style: { fontSize: 11, color: 'var(--dsw-alias-label-secondary,#888)' } }, s.description || ''));
            }))) : null,
          h('div', { className: 'dwb-row' }, h('div', { className: 'dwb-label' }, t.mcp),
            h('div', { style: { flex: 1 } },
              mcpList.length ? mcpList.map(function (m) {
                return h('div', { key: m.id || m.server_name, style: { marginBottom: 6 } },
                  h('span', { className: 'dwb-chip', style: { marginRight: 6 } }, m.server_name || m.id),
                  h('span', { style: { fontSize: 11, color: 'var(--dsw-alias-label-secondary,#888)' } }, m.url || '—' + (m.transport ? ' · ' + m.transport : '')));
              }) : h('span', { style: { color: 'var(--dsw-alias-label-secondary,#888)', fontSize: 12 } }, '—'))),
          h('div', { style: { fontSize: 11, color: 'var(--dsw-alias-label-secondary,#888)', margin: '2px 0 10px 96px' } }, t.readonly),
          renderConfigTree(a.config_tree, Object.fromEntries((a.mcp || []).map(function (m) { return [m.id, m]; }))),
          stats && h('div', { className: 'dwb-row' }, h('div', { className: 'dwb-label' }, t.status),
            h('div', null, t.invocations + ' ' + (stats.invocations || 0) + ' · ' + t.failures + ' ' + (stats.failures || 0) + (stats.status ? ' · ' + stats.status : ''))),
          h('div', { className: 'dwb-row' }, h('div', { className: 'dwb-label' }, t.editName),
            h('input', { className: 'dwb-textarea', style: { minHeight: 34 }, value: displayName, onChange: function (e) { setDisplayName(e.target.value); setSaved(false); } })),
          h('div', { className: 'dwb-row' }, h('div', { className: 'dwb-label' }, t.note),
            h('div', { style: { flex: 1 } },
              h('textarea', { className: 'dwb-textarea', value: note, onChange: function (e) { setNote(e.target.value); setSaved(false); } }),
              h('div', { style: { marginTop: 8, display: 'flex', gap: 8, alignItems: 'center' } },
                h('button', { className: 'dwb-btn', onClick: saveOverride }, t.save),
                saved && h('span', { style: { color: 'var(--dsw-alias-brand-primary,#2563eb)', fontSize: 12 } }, t.saved))))
        );
      }

      function renderOverview() {
        if (!overview) return h('div', { className: 'dwb-empty' }, t.empty);
        var s = overview.summary || {};
        var cards = [
          { k: t.agents, v: (roster.meta && roster.meta.count) || agents.length },
          { k: t.recentTasks, v: s.recent_n != null ? s.recent_n : '—' },
          { k: t.avgLatency, v: s.avg_latency_s != null ? s.avg_latency_s : '—' },
          { k: t.avgCoverage, v: s.avg_coverage != null ? s.avg_coverage : '—' },
          { k: t.overTarget, v: s.over_target != null ? s.over_target : '—' }
        ];
        var traces = overview.recent_traces || [];
        var chainFiles = overview.recent_traces_files || [];
        var bridges = overview.bridges || {};
        function bridgeRow(label, info, note) {
          return h('div', { className: 'dwb-row' },
            h('div', { className: 'dwb-label' }, label),
            h('div', { style: { flex: 1 } },
              h('div', null, info),
              note && h('div', { style: { fontSize: 11, opacity: 0.6, marginTop: 2 } }, note)));
        }
        var bridgeBlock = h('div', { style: { marginTop: 14, marginBottom: 14 } },
          h('div', { style: { fontSize: 12, fontWeight: 600, marginBottom: 6, opacity: 0.8 } }, '接入桥接'),
          bridgeRow('superagent', bridges.superagent && bridges.superagent.db
            ? (bridges.superagent.db.exists ? 'sqlite ' + bridges.superagent.db.size + ' B' : '持久化库未建') : '—',
            bridges.superagent && bridges.superagent.note),
          bridgeRow('DAG', bridges.dag && bridges.dag.orders
            ? (bridges.dag.orders.exists ? 'orders.json ' + bridges.dag.orders.size + ' B' : '无落盘工单') : '—',
            bridges.dag && bridges.dag.note),
          bridgeRow('jev', bridges.jev ? (bridges.jev.model || '—') : '—', bridges.jev && bridges.jev.url));
        return h('div', null,
          h('div', { className: 'dwb-cards' }, cards.map(function (c, i) {
            return h('div', { key: i, className: 'dwb-card' }, h('div', { className: 'v' }, c.v), h('div', { className: 'k' }, c.k));
          })),
          bridgeBlock,
          traces.length ? h('table', { className: 'dwb-table' },
            h('thead', null, h('tr', null,
              h('th', null, 'trace_id'), h('th', null, t.taskType), h('th', null, t.lane),
              h('th', null, t.avgLatency), h('th', null, t.avgCoverage), h('th', null, t.verdict))),
            h('tbody', null, traces.map(function (tr) {
              return h('tr', { key: tr.trace_id },
                h('td', null, tr.trace_id), h('td', null, tr.task_type || '—'),
                h('td', null, tr.fast_lane ? 'fast' : 'full'),
                h('td', null, tr.latency_s != null ? tr.latency_s : '—'),
                h('td', null, tr.coverage_rate != null ? tr.coverage_rate : '—'),
                h('td', null, tr.verdict || '—'));
            }))) : h('div', { className: 'dwb-empty' }, t.empty),
          h('div', { style: { marginTop: 14 } },
            h('div', { style: { fontSize: 12, fontWeight: 600, marginBottom: 6, opacity: 0.8 } }, t.chainTitle),
            chainFiles.length ? chainFiles.map(function (tr) {
              var chain = (tr.dispatched || []).map(function (d) { return 'Step ' + d.step + ' → ' + d.owner; });
              var inline = (tr.inline_steps || []).map(function (s) { return '内联 ' + s; });
              var items = chain.concat(inline);
              return h('div', { className: 'dwb-row', key: tr.trace_id },
                h('div', { style: { flex: 1 } },
                  h('div', { style: { fontWeight: 600, marginBottom: 4 } }, tr.trace_id),
                  h('div', { style: { display: 'flex', gap: 6, flexWrap: 'wrap' } },
                    items.length ? items.map(function (x, i) { return h('span', { className: 'dwb-chip', key: i }, x); })
                      : h('span', { className: 'dwb-chip' }, '—'))),
                h('div', { style: { fontSize: 11, minWidth: 110, textAlign: 'right' } }, tr.verdict || '—'));
            }) : h('div', { className: 'dwb-empty' }, t.chainEmpty))
        );
      }

      function renderChainStep(d, k, nameMap) {
        var dur = d.duration_s != null ? d.duration_s + 's' : '—';
        if (d.duration_pure_s != null) {
          dur = (d.duration_s != null ? d.duration_s + 's' : '—') + ' / 纯执行 ' + d.duration_pure_s + 's';
        }
        var status = d.status || 'started';
        var statusLabel = t['st' + status.charAt(0).toUpperCase() + status.slice(1)] || status;
        var statusColor = status === 'done' ? '#12b76a'
          : (status === 'failed' || status === 'blocked' || status === 'dropped') ? '#d92d20' : '#888';
        var owner = resolveOwner(d.owner, nameMap);
        var ownerLabel = owner.name ? (owner.name + ' · ' + d.owner) : (d.owner || '—');
        var stateChip = (d.state && d.state !== 'completed')
          ? h('span', { className: 'dwb-chip', style: { color: '#d92d20' } }, d.state) : null;
        var top = h('div', { style: { display: 'flex', gap: 8, alignItems: 'center', margin: '4px 0' } },
          h('span', { className: 'dwb-chip' }, t.chainStep + ' ' + d.step),
          h(Avatar, { id: d.owner, size: 18 }),
          h('span', { className: 'dwb-mono', style: { flex: 1 } }, ownerLabel),
          h('span', { className: 'dwb-chip', style: { color: statusColor } }, statusLabel),
          stateChip,
          h('span', { className: 'dwb-chip' }, t.chainDuration + ' ' + dur),
          h('span', { style: { fontSize: 11, opacity: 0.6 } }, d.at || ''));
        var art = d.artifact
          ? h('div', { style: { fontSize: 11, opacity: 0.7, margin: '0 0 4px 8px' } },
              t.chainArtifact + '：' + d.artifact)
          : null;
        var errLine = d.error
          ? h('div', { style: { fontSize: 11, color: '#d92d20', margin: '0 0 4px 8px' } }, '错误：' + d.error)
          : null;
        return h('div', { key: k }, top, art, errLine);
      }

      function renderChain(c, agents) {
        var dispatched = c.dispatched || [];
        var inline = c.inline_steps || [];
        var expected = c.expected_steps || [];
        var reasons = c.reasons || [];
        var violations = c.violations || [];
        var jev = c.jev || null;
        var nameMap = buildNameMap(agents);
        var doneSteps = dispatched.map(function (d) { return d.step; });
        var missing = expected.filter(function (s) { return doneSteps.indexOf(s) < 0; });
        var cov = c.coverage_rate != null ? Math.round(Number(c.coverage_rate) * 100) + '%' : '—';
        var covNorm = c.coverage_rate_norm != null ? Math.round(Number(c.coverage_rate_norm) * 100) + '%' : null;
        var busy = dispatched.reduce(function (s, d) { return s + (Number(d.duration_s) || 0); }, 0);
        var inFlight = !c.finished;
        var verdictStyle;
        if (c.verdict && c.verdict.indexOf('通过') === 0) {
          verdictStyle = { color: 'var(--dsw-alias-state-success-primary,#12b76a)' };
        } else if (c.verdict === '进行中' || c.verdict === 'running' || inFlight) {
          // 进行中快照：尚未轮到的步骤属待派发，不标红定罪（2026-11-23 复盘）
          verdictStyle = { color: 'var(--dsw-alias-state-warning-primary,#ff7d00)' };
        } else {
          verdictStyle = { color: 'var(--dsw-alias-state-error-primary,#d92d20)' };
        }

        var headChips = [
          h('span', { className: 'dwb-chip' }, t.lane + ' ' + (c.lane || '—')),
          h('span', { className: 'dwb-chip' }, t.taskType + ' ' + (c.task_type || '—')),
          c.source && h('span', { className: 'dwb-chip' }, t.source + ' ' + c.source),
          h('span', { className: 'dwb-chip' }, t.chainCoverage + ' ' + cov + (covNorm ? `（${t.chainCoverageNorm || '归一'} ${covNorm}）` : '')),
          c.duration_s != null && h('span', { className: 'dwb-chip' }, t.chainDuration + ' ' + c.duration_s + 's'),
          busy > 0 && h('span', { className: 'dwb-chip' }, t.chainExpertTime + ' ' + busy + 's'),
          jev && jev.confidence != null && h('span', { className: 'dwb-chip' }, t.confidence + ' ' + jev.confidence),
          c.verdict && h('span', { className: 'dwb-chip', style: verdictStyle }, c.verdict),
        ].filter(Boolean);

        return h('div', {
          key: c.trace_id,
          style: { border: '1px solid var(--dsw-alias-border,#e5e6eb)', borderRadius: 10, padding: 12, marginBottom: 12 }
        },
          h('div', { style: { display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 6 } },
            h('div', { style: { fontWeight: 600 } }, c.text || c.trace_id),
            h('div', { style: { fontSize: 11, opacity: 0.6, minWidth: 150, textAlign: 'right' } }, c.at || '')),
          h('div', { style: { display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 } }, headChips),
          reasons.length ? h('div', { style: { fontSize: 11, opacity: 0.7, marginBottom: 8 } },
            h('div', { style: { fontWeight: 600, marginBottom: 2 } }, t.chainReasons),
            reasons.map(function (r, i) { return h('div', { key: i }, '· ' + r); })) : null,

          c.has_trace
            ? h('div', null,
                h('div', { style: { fontSize: 12, fontWeight: 600, margin: '6px 0 4px', opacity: 0.8 } }, t.chainSteps + '（' + dispatched.length + '）'),
                dispatched.length ? dispatched.map(function (d, i) { return renderChainStep(d, i, nameMap); }) : h('div', { className: 'dwb-empty' }, '—'),
                inline.length ? h('div', { style: { marginTop: 6 } },
                  h('span', { style: { fontSize: 12, fontWeight: 600, marginRight: 6, opacity: 0.8 } }, t.chainInline),
                  inline.map(function (s, i) { return h('span', { className: 'dwb-chip', key: i, style: { marginRight: 6 } }, s); })) : null,
                missing.length ? h('div', { style: { marginTop: 6 } },
                  h('span', { style: { fontSize: 12, fontWeight: 600, marginRight: 6, color: inFlight ? '#86909c' : '#d92d20' } }, inFlight ? t.chainPending : t.chainMissing),
                  missing.map(function (s, i) {
                    var expId = STEP_EXPERT[s];
                    var exp = expId ? resolveOwner(expId, nameMap) : null;
                    var who = exp && exp.name ? (exp.name + ' · ' + expId) : (expId || '—');
                    return h('span', { className: 'dwb-chip', key: i, style: { marginRight: 6, color: inFlight ? '#86909c' : '#d92d20' } },
                      t.chainStep + ' ' + s + ' → ' + who);
                  })) : null,
                expected.length ? h('div', { style: { marginTop: 6, fontSize: 11, opacity: 0.6 } }, t.chainExpected + '：' + expected.join(', ')) : null,
                violations.length ? h('div', { style: { marginTop: 6 } },
                  h('span', { style: { fontSize: 12, fontWeight: 600, marginRight: 6, color: '#d92d20' } }, t.chainViolations),
                  violations.map(function (v, i) { return h('span', { className: 'dwb-chip', key: i, style: { marginRight: 6, color: '#d92d20' } }, v); })) : null)
            : h('div', { className: 'dwb-empty', style: { marginTop: 6 } }, t.chainRouteOnly + '；' + t.chainNoTrace)
        );
      }

      function renderChains() {
        if (!chains || !chains.length) return h('div', { className: 'dwb-empty' }, t.empty);
        return h('div', null, h('div', { style: { fontSize: 12, fontWeight: 600, marginBottom: 8, opacity: 0.8 } },
          t.chainBoard + ' · ' + chains.length),
          chains.map(function (c) { return renderChain(c, agents); }));
      }

      function renderRoutes() {
        var routes = (overview && overview.recent_routes) || [];
        if (!routes.length) return h('div', { className: 'dwb-empty' }, t.empty);
        return h('div', null, routes.map(function (r, i) {
          return h('div', { key: i, className: 'dwb-row' },
            h('div', { style: { flex: 1 } },
              h('div', { style: { fontWeight: 600, marginBottom: 4 } }, r.text || r.trace_id),
              h('div', { style: { display: 'flex', gap: 8, flexWrap: 'wrap' } },
                h('span', { className: 'dwb-chip' }, t.lane + ' ' + (r.lane || '—')),
                h('span', { className: 'dwb-chip' }, t.source + ' ' + (r.source || '—')),
                h('span', { className: 'dwb-chip' }, t.taskType + ' ' + (r.task_type || '—')),
                r.confidence != null && h('span', { className: 'dwb-chip' }, t.confidence + ' ' + r.confidence),
                r.agreement && h('span', { className: 'dwb-chip' }, t.agreement + ' ' + r.agreement))),
            h('div', { style: { fontSize: 11, color: 'var(--dsw-alias-label-secondary,#888)', minWidth: 130, textAlign: 'right' } }, r.at || ''));
        }));
      }

      return h('div', { className: 'dwb-root' },
        h('div', { className: 'dwb-header' },
          h('h2', null, t.title),
          h('button', { className: 'dwb-btn', onClick: loadAll, disabled: loading }, t.refresh)),
        h('div', { className: 'dwb-tabs' },
          h('div', { className: 'dwb-tab' + (tab === 'roster' ? ' active' : ''), onClick: function () { setTab('roster'); } }, t.tabRoster),
          h('div', { className: 'dwb-tab' + (tab === 'overview' ? ' active' : ''), onClick: function () { setTab('overview'); } }, t.tabOverview),
          h('div', { className: 'dwb-tab' + (tab === 'routes' ? ' active' : ''), onClick: function () { setTab('routes'); } }, t.tabRoutes),
          h('div', { className: 'dwb-tab' + (tab === 'chains' ? ' active' : ''), onClick: function () { setTab('chains'); } }, t.tabChains)),
        error && h('div', { className: 'dwb-err' }, error),
        h('div', { className: 'dwb-body' },
          tab === 'roster' && h('div', { className: 'dwb-list' }, renderList()),
          h('div', { className: 'dwb-content' },
            tab === 'roster' ? renderDetail() : tab === 'overview' ? renderOverview() : tab === 'chains' ? renderChains() : renderRoutes()))
      );
    }

    function getLocaleService(ctx) {
      try {
        if (ctx && ctx.locale) return ctx.locale;
        if (ctx && typeof ctx.get === 'function') { var s = ctx.get('locale'); if (s) return s; }
      } catch (_) { return null; }
      return null;
    }

    function apply(ctx) {
      var removeStyles = injectStyles();
      var locale = getLocaleService(ctx);
      var bound = null;
      if (locale && typeof locale.register === 'function') {
        try { ctx.effect ? ctx.effect(function () { locale.register(NS, { zh: DICT.zh, en: DICT.en }); }, 'dwb-team-panel: dictionaries') : locale.register(NS, { zh: DICT.zh, en: DICT.en }); } catch (_) {}
      }
      if (locale && typeof locale.bind === 'function') {
        try { bound = locale.bind(NS); } catch (_) { bound = null; }
      }
      var t = makeTranslator(bound);
      var slots = ctx && ctx.slots;
      if (slots && typeof slots.inject === 'function' && typeof slots.register === 'function') {
        try {
          slots.inject('main', function () {
            slots.register({ name: 'main', key: PANEL_ID, locale: NS, inject: function () { return {}; } },
              function (props) { return h(Panel, Object.assign({}, props, { t: t })); });
          });
          slots.inject('sidebar.panellist', function () {
            slots.register({ name: 'sidebar.panellist', id: PANEL_ID, order: 26, label: function () { return t('nav'); }, locale: NS }, IconComp);
          });
        } catch (error) { console.error('[dwb-team-panel] 槽位注册失败', error); }
      }
      return function () { removeStyles(); };
    }

    exports.inject = ['slots', 'locale'];
    exports.apply = apply;
    return module.exports;
  }
});
