#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""物化 SQL 快车道加载守卫（D4 防护）。

用途：在按 ZB_CODE 读取 materialized_sql/<ZB_CODE>.sql 时做加载断言，
拒绝「只有注释头 + 常量 0」的空壳文件，避免静默返回伪零值。
不改写、不编造任何业务口径 SQL；空壳仍需业务侧补齐真实口径。

用法：
    from materialized_sql_guard import load_guarded
    sql = load_guarded(path)          # 不合规抛 MaterializedSqlGuardError
"""
import re


class MaterializedSqlGuardError(ValueError):
    pass


def load_guarded(path, encoding="utf-8"):
    with open(path, encoding=encoding, errors="replace") as f:
        raw = f.read()
    body = "\n".join(
        line for line in raw.splitlines()
        if line.strip() and not line.strip().startswith("--")
    ).strip()
    if not body:
        raise MaterializedSqlGuardError("EMPTY_SQL: 物化 SQL 无有效正文: %s" % path)
    if not re.match(r"^(SELECT|WITH)\b", body, re.I):
        raise MaterializedSqlGuardError(
            "NON_READONLY_HEAD: 物化 SQL 非 SELECT/WITH 起手，拒绝加载（防止伪零值）: %s" % path
        )
    return body


def is_blocked(path, encoding="utf-8"):
    """供构建/巡检脚本调用：返回 (是否拦截, 原因)。"""
    try:
        load_guarded(path, encoding)
        return False, ""
    except MaterializedSqlGuardError as e:
        return True, str(e).split(":")[0]
