import sys, os, yaml

class _Loader(yaml.SafeLoader):
    pass
def _js_constructor(loader, node):
    return loader.construct_scalar(node)
_Loader.add_constructor("tag:yaml.org,2002:js", _js_constructor)
_Loader.add_multi_constructor("tag:yaml.org,2002:js:", _js_constructor)

root = r"$env:DSH_HOME\dwb-team"
yml_path = r"$env:DSH_HOME\profiles\desktop\cordis.patch.yml"

with open(yml_path, encoding="utf-8") as f:
    doc = yaml.load(f, Loader=_Loader)

# 收集所有 preset 定义
presets = []
def walk(node):
    if isinstance(node, dict):
        if node.get("name") == "@deepseek-ai/dsh-agent-preset" and isinstance(node.get("config"), dict):
            presets.append(node["config"])
        for v in node.values():
            walk(v)
    elif isinstance(node, list):
        for v in node:
            walk(v)
walk(doc)

print("presets parsed:", len(presets))

BUNDLED = set("""dsh-agent-preset dsh-persona dsh-time-context dsh-bash-sandbox dsh-pwsh-sandbox
dsh-tool-bash dsh-tool-pwsh dsh-tool-fs dsh-tool-fs-search dsh-tool-skill dsh-skill-filesystem
dsh-mcp-client dsh-agent-instructions dsh-tool-jobs dsh-tool-todo dsh-tool-web dsh-tool-present
dsh-compaction-basic dsh-command-compact dsh-compaction-tool-result-pruner dsh-tool-ask-user
dsh-tool-schedule dsh-tool-subagent-control dsh-tool-subagent""".split())

def check_rows(rows, at="", problems=None):
    if problems is None: problems = []
    if not isinstance(rows, list):
        problems.append(f"{at}: composition 不是列表")
        return problems
    for i, row in enumerate(rows):
        label = f"{at} row {i+1}"
        if not isinstance(row, dict):
            problems.append(f"{label}: 不是映射行"); continue
        name = row.get("name")
        if not isinstance(name, str) or not name:
            problems.append(f"{label}: 缺少 name 字符串")
        elif name != "cordis:group":
            pkg = name.split("/", 1)[1] if name.startswith("@deepseek-ai/") else name
            if pkg not in BUNDLED:
                problems.append(f"{label}: 未知插件包 {name}")
        if row.get("group") is True:
            check_rows(row.get("config"), label, problems)
    return problems

fast = next((p for p in presets if p.get("id") == "dwb-fast-ask"), None)
if not fast:
    print("!! fast-ask preset 未在 patch.yml 中找到")
    sys.exit(1)

probs = check_rows(fast.get("plugins"), "fast-ask")
print("fast-ask plugin rows:", len(fast.get("plugins") or []))
if probs:
    print("PROBLEMS:")
    for p in probs: print("  -", p)
else:
    print("fast-ask 行结构校验通过")

# 列出 fast 插件 id 与包
for row in fast["plugins"]:
    print("  *", row.get("id"), "->", row.get("name"))
