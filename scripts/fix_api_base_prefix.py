# -*- coding: utf-8 -*-
"""修复面板在「子路径部署」下的 API 前缀（幂等）

问题：DSH 可以用 --public-url https://host/dsh/ 挂在子路径。此时页面 URL 是
/dsh/，但面板把 API 写成绝对根路径 '/dwb-team/api'，浏览器就去请求
https://host/dwb-team/api/...（少了 /dsh/），反代无匹配 → 回落 index.html
→ JSON.parse 失败 → 前端显示「响应不是 JSON」。

修法：用 document.baseURI 解析成相对路径，自动带上部署前缀。

用法：python scripts/fix_api_base_prefix.py [--check]
"""
import io
import os
import sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT = os.path.join(PKG, "client.js")

OLD = "    var API_BASE = '/dwb-team/api';"

NEW = """    // 子路径部署（--public-url https://host/dsh/）时，API 必须跟着页面前缀走，
    // 否则请求会打到站点根、被反代回落成 HTML，前端 JSON.parse 失败。
    var API_BASE = (function () {
      try {
        var base = document.baseURI || (location.origin + '/');
        var u = new URL('dwb-team/api', base);
        return u.pathname.replace(/\\/+$/, '');
      } catch (e) {
        return '/dwb-team/api';
      }
    })();"""


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:  # noqa
            pass
    check = "--check" in sys.argv
    text = io.open(CLIENT, encoding="utf-8").read()
    if NEW.strip() in text:
        print("已就位（API_BASE 已支持子路径）")
        return 0
    if OLD not in text:
        print("FAIL: 找不到 API_BASE 原始定义")
        return 2
    if check:
        print("未修复：API_BASE 仍是绝对根路径")
        return 1
    io.open(CLIENT, "w", encoding="utf-8").write(text.replace(OLD, NEW, 1))
    print("API_BASE 已改为随页面前缀解析")
    return 0


if __name__ == "__main__":
    sys.exit(main())
