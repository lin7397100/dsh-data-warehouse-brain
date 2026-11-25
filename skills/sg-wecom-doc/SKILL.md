---
name: sg-wecom-doc
description: "三钢数仓智脑：企微文档（私有化智能表格）全流程操作统一接口。集成文档创建、读取、编辑、删除、权限管理、内容检索等全部 wedoc 开放 API 能力，固化 wecom_smartsheet_sync 等脚本的调用逻辑、字段/类型坑点与标准操作流程，使企微文档操作经单一可复用接口完成。"
version: 1.0.0
author: SanSteel Data Warehouse Brain
tags: [sangang, wecom, smartsheet, document-automation, enterprise-wechat]
owner: sg-wecom-doc
---

# sg-wecom-doc · 企微文档全流程操作统一接口

## 定位

**本技能是数仓智脑专家团面向企业微信（企微）文档的唯一自动化操作出口。** 文档 / 子表 / 字段 / 记录 / 权限 / 检索的全生命周期，全部经 `wedoc` 开放 API 完成，不依赖任何人工界面点击。

```
上游(编排器/洞察/开发/元数据) ──▶ sg-wecom-doc(翰枢) ──▶ wedoc 开放 API ──▶ 企微智能表格
       给: 目标文档 + 操作意图 + 数据/结构           (私有化 wecom.fjsg.com.cn)
                                                  ▲
                          回读校验 + 交付文档链接 ──┘
```

**职责边界**：本技能**只搬运、不生产**数据——数值与口径由数仓成员（DB2 MCP / 既有 JSON）提供；本技能负责把它落成可靠、可回读的企微智能表格，并沉淀踩坑经验为可复用规范。所有调用统一走 `api()` 封装，禁止绕过。

---

## 〇、企微环境配置（corpid / corpsecret / 端点）

本角色绑定**三钢闽光企微私有化部署**，凭证与端点已在核心库 `wecom_smartsheet_sync.py` 固化，调用前无需重复配置：

| 配置项 | 值 / 解析方式 |
|---|---|
| **corpid** | 从企微智能表格 `数仓智脑凭据管理` 读取 |
| **corpsecret** | ① 优先读环境变量 `WECOM_CORPSECRET`；② 回退复用随包分发的 `scripts/wecom_smartsheet.py` 中已有 `CORPSECRET`（已确认该文件随专家团分发，可自动解析，无需手填）；③ 两者皆无则运行时报错提示设置环境变量。**明文 secret 禁止写入插件/记忆文件** |
| **API 域名 BASE** | `https://wecom.fjsg.com.cn`（公有云改 `https://qyapi.weixin.qq.com`，脚本顶部可切） |
| **SSL** | 私有化自签证书 → `VERIFY_SSL=False`（受信环境可改 True） |
| **token 缓存** | 进程内 + 文件 `.wecom_token.json` 双缓存，提前 5 分钟过期自动刷新 |
| **默认目标文档** | docid `s3_AMAA4RTkAAA0q7TKZxkTZ668rLE5Y_a`（《钢铁料耗·炼钢成本 指标血缘与本体建模》）；访问基址 `https://wecomdoc.fjsg.com.cn/smartsheet/s3_AMAA4RTkAAA0q7TKZxkTZ668rLE5Y_a?scode=AMAA4RTkAAA72uXFV1AMAA4RTkAAA`，子表锚点拼 `&sheetid=<sheet_id>` |

> 切换企业/环境：改 `BASE` + 设对应 `WECOM_CORPSECRET` 即可；`corpid` 如需变更在 `wecom_smartsheet_sync.py` 顶部 `CORPID` 修改。

---

## 一、能力范围（全功能清单）

| # | 能力域 | 具体操作 | 底层接口 |
|---|---|---|---|
| 1 | **创建** | 新建智能表格文档 | `wedoc/create_doc`（doc_type=3文档/4表格/**10智能表格**/11智能文档） |
| 2 | **读取** | 列出子表、读字段、分页读记录 | `get_sheet` / `get_fields` / `get_records` |
| 3 | **编辑** | 增子表、改子表名、增字段、改字段名、写入/回填记录 | `add_sheet` / `update_sheet` / `add_fields` / `update_fields` / `add_records` / `update_records` |
| 4 | **删除** | 删子表、删字段（含默认列） | `delete_sheet` / `delete_fields` |
| 5 | **权限** | 授权成员、查询规则 | `wedoc/mod_doc_member` / `wedoc/doc_get_auth` |
| 6 | **检索** | 按列/关键词过滤内容、内容盘点 | `iter_records` + 列过滤（无独立搜索 API，靠读记录实现） |
| 7 | **工程** | 链接字段构造、默认列清理、子表锚点链接 | `FIELD_TYPE_URL` / `remove_default_column` / `SHEET_URL_TPL` |

---

## 二、统一操作接口（调用逻辑封装）

### 2.1 鉴权与重试（`api(path, body)`）

- **Token 缓存**：`get_token` 进程内 + 文件（`.wecom_token.json`）双缓存，提前 5 分钟过期；遇 `40001/42001/41001` 自动强制刷新重试。
- **限流退避**：`45009/45033/-1` 指数退避 `min(2^n,30)s` + 随机抖动，最多 `MAX_RETRY=5` 次。
- **不重试**：`301002`（无权限）/ `40058`/`41004`（参数错）直接抛出 `WecomError`，打印 errcode/path 便于定位。
- **统一出口**：所有接口 URL = `{BASE}/cgi-bin/{path}?access_token=。.`，`BASE` 私有化 `https://wecom.fjsg.com.cn`（公有云改 `https://qyapi.weixin.qq.com`）。

### 2.2 接口一览（全部相对 `{BASE}/cgi-bin/`）

| 用途 | Method | Endpoint | 关键入参 | 关键返回 |
|---|---|---|---|---|
| 取 token | GET | `gettoken` | corpid, corpsecret | access_token, expires_in |
| 新建文档 | POST | `wedoc/create_doc` | doc_type, doc_name, (spaceid,fatherid), admin_users | url, docid |
| 列出子表 | POST | `wedoc/smartsheet/get_sheet` | docid, need_all_type_sheet | sheet_list[].sheet_id/title/type |
| 新增子表 | POST | `wedoc/smartsheet/add_sheet` | docid, properties{title,index} | properties.sheet_id |
| 改子表名 | POST | `wedoc/smartsheet/update_sheet` | docid, properties{sheet_id,title} | — |
| 删子表 | POST | `wedoc/smartsheet/delete_sheet` | docid, sheet_id | — |
| 查字段 | POST | `wedoc/smartsheet/get_fields` | docid, sheet_id, offset, limit | **fields / field_list**（两者兼容） |
| 增字段 | POST | `wedoc/smartsheet/add_fields` | docid, sheet_id, fields[{field_title,field_type,property_url?}] | field_list |
| 改字段名 | POST | `wedoc/smartsheet/update_fields` | docid, sheet_id, fields[{field_id,field_title,field_type}] | — |
| 删字段 | POST | `wedoc/smartsheet/delete_fields` | docid, sheet_id, field_ids[] | — |
| 写记录 | POST | `wedoc/smartsheet/add_records` | docid, sheet_id, key_type, records[].values | records[] |
| 改记录 | POST | `wedoc/smartsheet/update_records` | docid, sheet_id, records[{record_id,values}] | — |
| 读记录 | POST | `wedoc/smartsheet/get_records` | docid, sheet_id, offset, limit | records[] |
| 文档权限 | POST | `wedoc/mod_doc_member` | docid, update_file_member_list[{type:1,auth,userid}] | — |
| 查权限 | POST | `wedoc/doc_get_auth` | docid | 查看规则/通知范围 |

### 2.3 单元格值构造（严格匹配企微 CellValue 规范）

```python
T(s)   # 文本 → [{"type":"text","text":str(s)}]
U(t,l) # 链接 → [{"type":"url","text":t,"link":l}]   # FIELD_TYPE_URL，仅展示第一个
N(x)   # 数字 → float(x)
```
`add_records` 统一用 `key_type="CELL_VALUE_KEY_TYPE_FIELD_TITLE"`（按列标题写，可读且不依赖 field_id）。

---

## 三、字段与类型工程（8 条硬约束 · 经实测）

> 以下为团队在私有化部署反复踩雷验证过的真值，新操作必须先遵守。

1. **字段标题禁下划线**：含 `_` 的标题（`FACTORY_DIV`/`ZB_CODE` 等）被 `add_fields` 以 `2022030 invalid title` 拒建 → 建字段前 `san(t)=t.replace("_","")`。
2. **NUMBER 字段静默丢值**：经 API 写入的数值会丢 → 所有数值以**文本字段**承载（`T()`）。
3. **FIELD_TYPE_URL 可经 API 创建**：`property_url` 为**必填**且须 `{"type":"LINK_TYPE_PURE_TEXT"}`；传空 `{}` 或不传 → `2022019 invalid url field`。（曾误判"平台不支持"，已推翻。）链接单元格结构：`[{"type":"url","text":。,"link":。}]`。
4. **get_fields 返回顶层 `fields`**（非公有云的 `field_list`）→ 读取须兼容两者。
5. **删默认列须 `field_ids:[真实id]`**：新建子表自带「智能表列」（`field_id=fabcde`）；删它必须在 add_fields 真实字段**之后**（保证非唯一列）才真生效；用 `field_titles` 返回 errcode=0 却删不掉（假阳性）。
6. **update_fields 只能改名、不能改类型**：改名必须带完整 `field_type`（只传 field_title → `2022010`）；改 type 为 URL 仍失败（`2022010`）。
7. **写入范式**：先建空壳行（`add_records` 传 `[{}]` 拿 record_id）→ `update_records` 按 id 回填。直接 `add_records` 带值会产出空行。
8. **字段上限**：单表 150 列（`FIELD_BATCH=20` 分批建）；记录单批 `BATCH_SIZE=100`（单表上限 10 万行）。

### 8.1 文本链接列 → 真链接字段的转换路径（已验证）

`convert_links.py` 实现：新建 URL 列(临时名) → 按 record_id 搬 URL 数据 → 校验行数一致 → 删旧 TEXT 列 → `update_fields` 改名（带 field_type）。因 `update_fields` 不能改类型，必须"新建+搬迁+删除旧列"三步。

---

## 四、标准操作流程（SOP）

### SOP-A · 新建智能表格并落地一份报表

```bash
cd <skill>/scripts
export WECOM_CORPSECRET=<secret>          # 或脚本自动复用本机已有值
python wecom_smartsheet_sync.py            # 新建文档 + 21 子表 + 字段 + 记录 + 权限
python wecom_smartsheet_sync.py --dry-run  # 先干跑自检（不写接口）
python wecom_smartsheet_sync.py --docid <ID>   # 复用已有文档增量同步
python wecom_smartsheet_sync.py --limit 5      # 每表只写 5 行先验证
```

### SOP-B · 回填已有文档（删重建 + 空壳回填 + 清默认列）

```bash
export WECOM_DOCID=s3_AMAA4RTkAAA0q7TKZxkTZ668rLE5Y_a   # 默认即此；换文档覆盖
python fill_wecom_tables.py
```
流程：① 删重建 21 张目标子表 → ② build_all 生成结构+跳转链接 → ③ 后处理（标题去下划线/链接列用 URL 字段其余文本）→ ④ 建字段→空壳→按 id 回填→读回校验 → ⑤ 汇总一致率。

### SOP-C · 把文本链接列升级为「链接」字段

```bash
python convert_links.py     # 16 张表批量迁移，544 行 0 失败（S01/S20/S14 已是 URL 跳过）
```

### SOP-D · 权限管理

- 授权：成员写入 `MEMBER_USERS` + `MEMBER_AUTH`（1只读/2读写/7管理员）→ `grant_members(docid)` 调 `mod_doc_member`。
- 前置：自建应用须有「文档」权限且被加入文档「可调用应用」列表，否则 `301002`。

### SOP-E · 读取 / 内容检索 / 盘点

```python
import wecom_smartsheet_sync as S
sheets = S.list_sheets(docid)
flds   = S.get_fields(docid, sheet_id)          # 兼容 fields/field_list
for rec in S.iter_records(docid, sheet_id):     # 分页游标
    。.                                          # 按列过滤即为"检索"
```

### SOP-F · 通用单次调用（自测凭据 / 任意接口）

```python
import wecom_smartsheet_sync as S
S.api("wedoc/smartsheet/get_sheet", {"docid": DOCID, "need_all_type_sheet": True})
```

---

## 五、脚本资产（scripts/）

| 文件 | 角色 | 说明 |
|---|---|---|
| `wecom_smartsheet_sync.py` | **核心库（统一接口）** | `api/get_token`/`create_doc`/`list_sheets`/`add_sheet`/`rename_sheet`/`delete_sheet`/`get_fields`(兼容)/`ensure_fields`(URL 自动补 property_url)/`add_records`/`update_records`/`iter_records`/`grant_members`/`remove_default_column`；`T/U/N` 单元格构造；`SHEETS`/`F_DRILL` 结构定义；`build_all`/`self_check` 报表样例。零第三方依赖（仅 urllib+ssl）。 |
| `fill_wecom_tables.py` | 回填操作脚本 | 删重建 21 表 → build_all → 去下划线/链接字段化 → 空壳+id 回填 → 清默认列 → 读回校验。`WECOM_DOCID` 可覆盖。 |
| `convert_links.py` | 链接字段转换 | 批量把 TEXT 链接列转真 `FIELD_TYPE_URL`（新建+搬迁+删旧+改名）。`WECOM_DOCID` 可覆盖。 |
| `README_企微文档落地方案.md` | 设计文档 | 接口清单、字段类型枚举、单元格规范、异常表、使用方式（本技能的事实来源之一）。 |
| `report_data.json` | 样例数据 | `build_all` 的输入样例（DB2 抽取结果），用于端到端跑通。 |

**环境变量**：`WECOM_CORPSECRET`（必填，应用 secret）/`WECOM_DOCID`（选填，目标文档 docid）。

---

## 六、已知限制

1. **私有化环境**：默认 `BASE=https://wecom.fjsg.com.cn`，自签证书 `VERIFY_SSL=False`（受信环境可改 True）；公有云改 `qyapi.weixin.qq.com` 即可。
2. **charts 类 API 全不可用**（`-5001`）：图表视图/仪表盘各版本开放度不一，脚本只落 100% 明细数据，图表可在企微端基于子表插入或后续接 `smartsheet/charts/*`。
3. **`update_fields` 不能改类型**：要改字段类型只能"新建+搬迁+删除旧列"。
4. **`get_fields` 读 field_type 偶发不一致**（同列有时报 TEXT 有时 URL）：以单元格实际 URL 为准，不影响点击跳转。
5. **损坏子表**：文档中可能存在 `get_records` 报 `sub sheet not found` 的损坏子表（如早期「仪表盘1」），删除前需人工确认，避免误删数据。
6. **权限前置**：应用须被加入文档「可调用应用」列表，否则任何写接口返回 `301002`。

## 统一入口（合并说明）
本技能为统一入口，已吸收相关子能力（旧目录保留为兼容别名）。
