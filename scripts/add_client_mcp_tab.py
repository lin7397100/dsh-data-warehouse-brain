# -*- coding: utf-8 -*-
"""给面板客户端加「MCP 连接」页签（幂等）

在 client.js（经典脚本）里插入：
  - 字典：tabMcp 与按钮/状态文案（zh/en）
  - 状态：mcp 列表、busy、probe 提示
  - 数据：loadAll 里追加 /mcp
  - 交互：toggleMcp / testMcp
  - 视图：renderMcp()
  - 页签按钮与渲染分支

用法：python scripts/add_client_mcp_tab.py [--check]
"""
import io
import os
import sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT = os.path.join(PKG, "client.js")

ZH_ANCHOR = "tabChains: '调度链路',"
ZH_ADD = """tabChains: '调度链路', tabMcp: 'MCP 连接',
        mcpEnable: '启用', mcpDisable: '停用', mcpTest: '测试连接', mcpTools: '工具',
        mcpNeedToken: '需在 .env 配置 SG_WEKNORA_TOKEN', mcpProbing: '测试中…',
        mcpState: { connected: '已连接', disabled: '未启用', connecting: '连接中',
          reconnecting: '重连中', failed: '失败', closed: '已断开',
          'waiting-credentials': '缺少令牌', unavailable: '不可用' },"""

EN_ANCHOR = "tabChains: 'Dispatch chain',"
EN_ADD = """tabChains: 'Dispatch chain', tabMcp: 'MCP',
        mcpEnable: 'Enable', mcpDisable: 'Disable', mcpTest: 'Test', mcpTools: 'tools',
        mcpNeedToken: 'Set SG_WEKNORA_TOKEN in .env', mcpProbing: 'Testing…',
        mcpState: { connected: 'Connected', disabled: 'Disabled', connecting: 'Connecting',
          reconnecting: 'Reconnecting', failed: 'Failed', closed: 'Closed',
          'waiting-credentials': 'Missing token', unavailable: 'Unavailable' },"""

STATE_ANCHOR = "var [error, setError] = useState('');"
STATE_ADD = """var [error, setError] = useState('');
      var [mcp, setMcp] = useState(null);
      var [mcpBusy, setMcpBusy] = useState('');
      var [probeMsg, setProbeMsg] = useState('');"""

LOAD_ANCHOR = """          var c = await fetchJson('/chains');
          if (c.ok) setChains(c.chains || []); else setChains([]);"""
LOAD_ADD = LOAD_ANCHOR + """
          var m = await fetchJson('/mcp');
          if (m.ok) setMcp(m.servers || []); else setMcp(null);"""

HANDLERS_ANCHOR = "      useEffect(function () { loadAll(); }, [loadAll]);"
HANDLERS_ADD = """      var postJson = async function (path, payload) {
        var r = await fetch(API_BASE + path, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify(payload),
        });
        try { return await r.json(); } catch (e) { return { ok: false, error: String(e) }; }
      };

      var toggleMcp = useCallback(async function (name, on) {
        setMcpBusy(name); setProbeMsg('');
        try {
          var r = await postJson('/mcp/toggle', { name: name, on: on });
          if (r.ok) {
            var m = await fetchJson('/mcp');
            if (m.ok) setMcp(m.servers || []);
          } else { setError(r.error || t.loadFailed); }
        } finally { setMcpBusy(''); }
      }, [t]);

      var testMcp = useCallback(async function (name) {
        setMcpBusy(name); setProbeMsg(t.mcpProbing);
        try {
          var r = await postJson('/mcp/probe', { name: name });
          if (r.ok) {
            var p = r.probe || {};
            var head = (p.ok ? '✅ ' : '❌ ') + name + ' · ' +
              (p.ok ? (p.toolNames ? p.toolNames.length : 0) + ' ' + t.mcpTools : (p.stage || '') + ' ' + (p.message || ''));
            setProbeMsg(head + ' · ' + (p.durationMs != null ? p.durationMs + 'ms' : ''));
          } else { setProbeMsg('❌ ' + (r.error || t.loadFailed)); }
        } finally { setMcpBusy(''); }
      }, [t]);

""" + HANDLERS_ANCHOR

VIEW_ANCHOR = "      return h('div', { className: 'dwb-root' },"
VIEW_ADD = """      function renderMcp() {
        if (!mcp) return h('div', { className: 'dwb-empty' }, t.empty);
        var tone = function (st) {
          if (st === 'connected') return '#22c55e';
          if (st === 'failed') return '#ef4444';
          if (st === 'connecting' || st === 'reconnecting') return '#f59e0b';
          return '#9ca3af';
        };
        return h('div', null,
          probeMsg && h('div', { className: 'dwb-chip', style: { marginBottom: 8 } }, probeMsg),
          mcp.map(function (s) {
            var st = (s.status && s.status.state) || 'disabled';
            var label = (t.mcpState && t.mcpState[st]) || st;
            return h('div', { key: s.name, className: 'dwb-row' },
              h('div', { style: { flex: 1 } },
                h('div', { style: { fontWeight: 600, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 6 } },
                  h('span', { style: { width: 8, height: 8, borderRadius: 4, background: tone(st), display: 'inline-block' } }),
                  s.label,
                  h('span', { className: 'dwb-chip' }, label + (s.toolCount ? ' · ' + s.toolCount + ' ' + t.mcpTools : ''))),
                h('div', { style: { fontSize: 11, color: 'var(--dsw-alias-label-secondary,#888)' } }, s.url),
                h('div', { style: { fontSize: 11, opacity: 0.75 } }, s.purpose),
                s.needsToken && h('div', { className: 'dwb-chip', style: { marginTop: 4 } }, t.mcpNeedToken)),
              h('div', { style: { display: 'flex', gap: 8 } },
                h('button', {
                  className: 'dwb-btn', disabled: mcpBusy === s.name,
                  onClick: function () { toggleMcp(s.name, !s.enabled); },
                }, s.enabled ? t.mcpDisable : t.mcpEnable),
                h('button', {
                  className: 'dwb-btn', disabled: mcpBusy === s.name,
                  onClick: function () { testMcp(s.name); },
                }, t.mcpTest)));
          }));
      }

""" + VIEW_ANCHOR

TABBAR_ANCHOR = """          h('div', { className: 'dwb-tab' + (tab === 'chains' ? ' active' : ''), onClick: function () { setTab('chains'); } }, t.tabChains)),"""
TABBAR_ADD = """          h('div', { className: 'dwb-tab' + (tab === 'chains' ? ' active' : ''), onClick: function () { setTab('chains'); } }, t.tabChains),
          h('div', { className: 'dwb-tab' + (tab === 'mcp' ? ' active' : ''), onClick: function () { setTab('mcp'); } }, t.tabMcp)),"""

BRANCH_ANCHOR = "tab === 'roster' ? renderDetail() : tab === 'overview' ? renderOverview() : tab === 'chains' ? renderChains() : renderRoutes()"
BRANCH_ADD = "tab === 'roster' ? renderDetail() : tab === 'overview' ? renderOverview() : tab === 'chains' ? renderChains() : tab === 'mcp' ? renderMcp() : renderRoutes()"


def patch(text, anchor, addition, label, check):
    if addition.strip() in text or (label == 'branch' and BRANCH_ADD in text):
        return text, False
    if anchor not in text:
        raise SystemExit("FAIL: 找不到锚点 %s" % label)
    return text.replace(anchor, addition, 1), True


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:  # noqa
            pass
    check = "--check" in sys.argv
    text = io.open(CLIENT, encoding="utf-8").read()
    steps = [
        ("zh", ZH_ANCHOR, ZH_ADD),
        ("en", EN_ANCHOR, EN_ADD),
        ("state", STATE_ANCHOR, STATE_ADD),
        ("load", LOAD_ANCHOR, LOAD_ADD),
        ("handlers", HANDLERS_ANCHOR, HANDLERS_ADD),
        ("view", VIEW_ANCHOR, VIEW_ADD),
        ("tabbar", TABBAR_ANCHOR, TABBAR_ADD),
        ("branch", BRANCH_ANCHOR, BRANCH_ADD),
    ]
    done = []
    for label, anchor, addition in steps:
        if addition.strip() and addition.strip() in text:
            continue
        if label == "branch" and BRANCH_ADD in text:
            continue
        if anchor not in text:
            print("FAIL: 锚点缺失 %s" % label)
            return 2
        text = text.replace(anchor, addition, 1)
        done.append(label)
    if not done:
        print("已就位（无需改动）")
        return 0
    print("插入：" + ", ".join(done))
    if check:
        print("--check：未写盘")
        return 0
    io.open(CLIENT, "w", encoding="utf-8").write(text)
    print("client.js 已更新")
    return 0


if __name__ == "__main__":
    sys.exit(main())
