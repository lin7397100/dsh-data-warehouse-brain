# 鉴权与凭据填报手册（内网部署）

> 本专家团跑在**内网**：EPLAT 5S 元数据、DB2、企微（智能表格/群机器人）、帆软报表都在内网或私有化环境。
> 这份文档把**每一个要填的凭据**列清楚：变量名、用途、从哪拿、怎么验证。
> 照着填进 `$DSH_HOME/.env` 即可；也可以把本文件整份发给 DSH / WorkBuddy，让它按第 3 节的"一句话"自动填报。

---

## 0. 三条铁律（先读）

1. **凭据只进 `.env` 或进程环境变量**。不要写进 `skills/`、`agents/`、`cordis.patch.yml` 的明文、Git 仓库、聊天窗口。
2. **随包代码里不得出现明文 secret**。若发现，用 `python scripts/scrub_secrets.py` 清理并**立刻轮换**该凭据。
3. **泄露即轮换**：凭据一旦出现在公开仓库/公开 npm 包/对话记录里，视为已泄露——换掉它，而不是删掉那行代码就算完（历史与镜像仍有副本）。

---

## 1. 凭据总表

| # | 变量 | 用途 | 必需 | 影响的技能/专家 | 从哪拿 |
|---|---|---|---|---|---|
| 1 | `EPLAT_CLIENT_ID_CB01` | 日成本域过程日志 API | 用成本域报表时必需 | `sg-cbprod-procedure-analyzer` | 内网「数仓凭据管理」智能表格（默认 `sgdw-cb01`） |
| 2 | `EPLAT_CLIENT_SECRET_CB01` | 同上，密钥 | 同上 | 同上 | 同上 |
| 3 | `EPLAT_CLIENT_ID_CS01` | 管控抽数 ETL 日志 API | 用生产域抽数分析时必需 | `sg-gzprod-etl-analyzer`、`tools/freshness_gate.py` | 凭据表（默认 `sgdw-cs01`） |
| 4 | `EPLAT_CLIENT_SECRET_CS01` | 同上，密钥 | 同上 | 同上 | 同上 |
| 5 | `EPLAT_CLIENT_ID_GZ01` | 早会 PPT 报表接口 | 用早会报表时必需 | `sg-morning-ppt-report` | 凭据表（默认 `sgdw-gz01`） |
| 6 | `EPLAT_CLIENT_SECRET_GZ01` | 同上，密钥 | 同上 | 同上 | 同上 |
| 7 | `WECOM_TOKEN_CLIENT_ID` | 每日点检 token 应用（发 token 给报表/ETL 接口） | 用报表投递时必需 | `sg-report-delivery`、`wecom_sender.py` | 凭据表（默认 `sgoc-oc01`） |
| 8 | `WECOM_TOKEN_CLIENT_SECRET` | 同上，密钥 | 同上 | 同上 | 同上 |
| 9 | `WECOM_CORPID` | 企微企业 ID | 用智能表格/企微 API 时必需 | `sg-wecom-doc` | 企微管理后台 → 我的企业 |
| 10 | `WECOM_CORPSECRET` | 自建应用 secret | 同上 | `sg-wecom-doc`、智能表格同步脚本 | 企微管理后台 → 应用管理 → 自建应用 |
| 11 | `WECOM_DOCID` | 目标智能表格 docid | 选填 | `sg-wecom-doc` | 表格链接里的 `docid` 参数 |
| 12 | `SGDW_LIGHTCODE_TOKEN` | 5sApi DB2 REST 桥接（无 DB2 MCP 时的降级通道） | 无 MCP 时必需 | `sg-db2-rest`、`sg-db2-executor` | 浏览器登录 5sApi 后，从 Cookie `lightcodegtw-token` 复制 |
| 13 | `SGDW_USER_ID` | 同上，调用方用户 ID | 同上 | 同上 | 5sApi 用户信息 / 工号 |
| 14 | `SGDW_CLIENT_ID` | 同上，客户端标识 | 同上 | 同上 | 默认 `sgdw-sc01`，按环境改 |
| 15 | `SG_EPLAT_MCP_URL` | EPLAT Oracle 只读 MCP 端点 | 用 EPLAT 设计态时必需 | `sg-metadata` 等 7 个专家 | 运维给的 MCP 地址（默认 `http://10.18.136.38:8770/mcp`） |
| 16 | `SG_WEKNORA_MCP_URL` | WeKnora 知识库 MCP | 用知识检索时必需 | 全团 | 默认 `http://10.233.2.32:9080/mcp` |
| 17 | `SG_WEKNORA_TOKEN` | 同上，Bearer 令牌 | 同上 | 同上 | WeKnora 控制台 |
| 18 | `DWB_INTERNAL_MCP` | 内网 MCP 总开关（`1`=启用） | 必需（否则全部 MCP 关闭） | 全团 | 本地设定 |
| 19 | `FINEREPORT_URL` | 帆软报表服务地址（管制/生产/ERP 报表） | 用报表导出时必需 | `sg-gzprod-report` | 运维给的地址（默认 `http://172.16.100.25:8080/webroot/decision/view/report`） |
| 20 | `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` | 本体图谱（可选） | 用图谱时 | `sg-ontology-modeler` | 图数据库运维 |
| 21 | `MILVUS_HOST` / `MILVUS_PORT` | 语义向量库（可选） | 用语义建模时 | `sg-semantic-modeler` | 向量库运维 |
| 22 | `DSH_PYTHON` | 指定 Python 解释器（可选） | 选填 | 面板回写、团队脚本 | 本地路径 |

> 表中**默认值**是团队常用值；换了环境按实际填。
> 第 1–8 项是本次安全整改的重点：它们原本硬编码在技能脚本里，现已改为读环境变量。

---

## 2. 填在哪里

### 2.1 主位置：`$DSH_HOME/.env`（推荐）

```
Windows:  C:\Users\<你>\.dsh\.env
Linux:    ~/.dsh/.env
```

DSH 启动时把这里的键注入进程环境，所有技能脚本、MCP 客户端、面板宿主半都能读到。

权限要求：Linux 上 `chmod 600`；Windows 上仅当前用户可读。

### 2.2 引用方式

| 位置 | 写法 |
|---|---|
| 技能 Python 脚本 | `os.getenv("EPLAT_CLIENT_SECRET_CB01", "")` |
| preset / patch 配置 | `!!js process.env.SG_EPLAT_MCP_URL ?? 'http://…'` |
| 面板宿主半 | `process.env.DSH_HOME`、`process.env.FINEREPORT_URL` |

### 2.3 绝对不要

- 写进 `skills/**/*.py`、`agents/*.md`、`cordis.patch.yml` 的明文
- 提交到 Git（`.gitignore` 已排除 `.env`）
- 贴进对话/工单/群聊（要传就传 `.env.example`）

---

## 3. 一键填报（把这份文档发给 DSH / WorkBuddy）

### 3.1 一句话模板

```
按附件《鉴权与凭据填报手册》帮我配置数仓智脑专家团的内网凭据：
1) 把下面这些值写入 $DSH_HOME/.env（已有键覆盖、其它键保留，先备份）；
2) 写完执行 python scripts/write_env.py --status 与校验命令，把缺项和失败项列给我；
3) 任何值都不要写进仓库文件、不要回显明文（只显示前 4 位）。

EPLAT_CLIENT_SECRET_CB01=<值>
EPLAT_CLIENT_SECRET_CS01=<值>
EPLAT_CLIENT_SECRET_GZ01=<值>
WECOM_TOKEN_CLIENT_SECRET=<值>
WECOM_CORPSECRET=<值>
SGDW_LIGHTCODE_TOKEN=<值>
SGDW_USER_ID=<值>
SG_WEKNORA_TOKEN=<值>
```

（把 `EPLAT_CLIENT_ID_*`、`SG_*_MCP_URL`、`FINEREPORT_URL` 等非密钥项一并列上也可以。）

### 3.2 命令行等价写法

```bash
python scripts/write_env.py \
  --set EPLAT_CLIENT_SECRET_CB01=xxxx \
  --set EPLAT_CLIENT_SECRET_CS01=xxxx \
  --set EPLAT_CLIENT_SECRET_GZ01=xxxx \
  --set WECOM_TOKEN_CLIENT_SECRET=xxxx \
  --set WECOM_CORPSECRET=xxxx \
  --set SGDW_LIGHTCODE_TOKEN=xxxx \
  --set SGDW_USER_ID=230012 \
  --set SG_WEKNORA_TOKEN=xxxx \
  --set DWB_INTERNAL_MCP=1

python scripts/write_env.py --status     # 看哪些已配、哪些缺
```

脚本行为：备份为 `.env.bak-<时间戳>` → 合并写入（不动其它键）→ Linux 下 `chmod 600` → 打印脱敏状态。

---

## 4. 自助校验

```bash
# 1) 变量是否齐（不打印明文）
python scripts/write_env.py --status

# 2) EPLAT MCP 通不通
curl -sS -X POST "$SG_EPLAT_MCP_URL" -H 'Content-Type: application/json' \
     -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":,"clientInfo":{"name":"probe","version":"0"}}}' | head -c 200

# 3) 企微 gettoken（会返回 access_token，注意别贴出来）
curl -sk "https://wecom.fjsg.com.cn/cgi-bin/gettoken?corpid=$WECOM_CORPID&corpsecret=$WECOM_CORPSECRET" | head -c 120

# 4) 5sApi REST 桥接（只读探活）
curl -sS -H "Cookie: lightcodegtw-token=$SGDW_LIGHTCODE_TOKEN" \
     -H 'Content-Type: application/x-www-form-urlencoded' \
     -d "sql=SELECT 1 AS X FROM SYSIBM.SYSDUMMY1&clientId=$SGDW_CLIENT_ID&userId=$SGDW_USER_ID&limit=1" \
     "<5sApi 网关地址>"
```

期望：MCP 返回 `serverInfo`；企微返回 `access_token`；5sApi 返回 `1`。

---

## 5. MCP 开关（最容易踩）

组合包默认**关闭全部内网 MCP**（避免公网用户每次会话都连超时）。启用：

```bash
# .env
DWB_INTERNAL_MCP=1
# 想整体关停任一时刻
SG_MCP=off
```

启用后这些条目才会连：`mcp-weknora`、`mcp-db2`、`mcp-wecom-group`、`mcp-wecom-user`。
`mcp-eplat` 走 `SG_EPLAT_MCP_URL`，同样受 `SG_MCP=off` 约束。

---

## 6. 泄露处置流程（照做即可）

1. **冻结**：在凭据所属系统（5sApi 凭据表 / 企微后台 / WeKnora）把该 secret **作废或重置**。
2. **替换**：新值写进 `$DSH_HOME/.env`；不要回到代码里。
3. **清理代码**：`python scripts/scrub_secrets.py --check` 应退出 0；否则跑一次清理并提交。
4. **下架历史副本**（能删则删，删不掉就靠第 1 步兜底）：
   - npm：`npm unpublish <包>@<版本>`（72 小时内；需 2FA，token 无法执行此操作）
   - GitHub：`git filter-repo` 重写历史后强推（团队协作时慎用）；旧提交仍可能被 fork
   - 镜像：npmmirror 等第三方镜像可能保留缓存，**只能靠轮换**
5. **复盘**：把该凭据加入"禁止入仓"清单（见第 0 节），并在 `scripts/scrub_secrets.py` 的 `ROUTES` 里补一条路由。

---

## 7. 联调清单（配完按顺序点一遍）

| # | 动作 | 期望 |
|---|---|---|
| 1 | 重启 DSH | 新会话能选到「冶衡 Axis」 |
| 2 | 左侧栏「数仓专家团」 | 24 个专家、头像、职责都在 |
| 3 | 让 `sg-metadata` 跑 `oracle_ping` | `connected=true`，`write_privileges_held=[]` |
| 4 | 让 `sg-wecom-doc` 读一张智能表格 | 返回表头与首行；无 `errcode` |
| 5 | 让 `sg-gzprod-etl-analyzer` 拉一天 ETL 日志 | 返回记录条数 > 0 |
| 6 | 让 `sg-report-delivery` 发一条测试消息到指定群 | 群内收到消息 |
| 7 | 跑 `python tools/verify_eplat_templates.py` | OK=18 ERR=0 |

---

## 8. 相关文件

| 文件 | 用途 |
|---|---|
| `.env.example` | 全部变量的空白模板（复制成 `$DSH_HOME/.env` 再填） |
| `scripts/write_env.py` | 一键写入/查看状态（备份 + 合并 + 脱敏显示） |
| `scripts/scrub_secrets.py` | 扫描并清除代码里的明文凭据（`--check` 可作 CI 门禁） |
| `docs/INSTALL-INTRANET.md` | 内网安装与镜像源配置 |
