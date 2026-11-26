# -*- coding: utf-8 -*-
"""给面板客服端 fetchJson 加可诊断的失败信息（幂等）

原来非 JSON 只回一句"响应不是 JSON"，用户无从下手。改成区分两种情况：
  - 返回 HTML  → 反代把 /dwb-team/api 回落到了前端页面 → 要配 location /dwb-team/
  - 404 空体   → host 半没注册路由 → 插件未启用 / 未重启
"""
import io
import os
import sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT = os.path.join(PKG, "client.js")

OLD = """    async function fetchJson(path, options) {
      var resp = await fetch(API_BASE + path, options || {});
      var data = await resp.json().catch(function () { return { ok: false, error: '\u54cd\u5e94\u4e0d\u662f JSON' }; });
      return data;
    }"""

NEW = """    async function fetchJson(path, options) {
      var resp = await fetch(API_BASE + path, options || {});
      var text = '';
      try { text = await resp.text(); } catch (e) { text = ''; }
      var data = null;
      try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
      if (data) return data;
      var isHtml = /^\\s*<(!doctype|html)/i.test(text || '');
      var msg = '\u9762\u677f\u540e\u7aef\u672a\u5c31\u7eea\uff08HTTP ' + resp.status + '\uff09';
      msg += isHtml
        ? '\uff1a\u4ee3\u7406\u628a /dwb-team/api \u56de\u843d\u5230\u4e86\u524d\u7aef\u9875\u9762\uff0c\u9700\u4e3a /dwb-team/ \u914d\u7f6e\u8f6c\u53d1'
        : '\uff1ahost \u534a\u6ca1\u6709\u6ce8\u518c /dwb-team/api/*\uff0c\u8bf7\u786e\u8ba4\u63d2\u4ef6\u5df2\u542f\u7528\u5e76\u91cd\u542f DSH';
      return { ok: false, error: msg, _notJson: true, _status: resp.status, _html: isHtml };
    }"""


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:  # noqa
            pass
    text = io.open(CLIENT, encoding="utf-8").read()
    if NEW.strip() in text:
        print("已就位（无需改动）")
        return 0
    if OLD not in text:
        print("FAIL: 找不到 fetchJson 原实现")
        return 2
    io.open(CLIENT, "w", encoding="utf-8").write(text.replace(OLD, NEW, 1))
    print("fetchJson 已改为可诊断提示")
    return 0


if __name__ == "__main__":
    sys.exit(main())
