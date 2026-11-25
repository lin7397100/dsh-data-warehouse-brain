# 钢铁料耗×成本跨域比对报告 → 企业微信文档（wedoc）落地方案

> 目标：把 `钢铁料耗成本跨域比对_全厂横向比对_可视化报告_20260922.html`
> 的全部信息与功能，**纯通过企微开放 API** 在企微智能表格中完整重建。
> 交付物：`wecom_smartsheet_sync.py`（可执行脚本）+ `report_data.json`（源数据）+ 本文档。

---

## 0. 缺失项与假设（先说清楚）

| 类别 | 状态 | 说明 |
|---|---|---|
| `CORPID` | 从智能表格读取 | 私有化部署凭据 |
| `CORPSECRET` | 自动解析 | 优先读环境变量 `WECOM_CORPSECRET`，否则复用随包分发的 `scripts/wecom_smartsheet.py` 中已有值；两者都无才需手填 |
| API 域名 | 已适配私有化 | `https://wecom.fjsg.com.cn`（非公版 `qyapi.weixin.qq.com`），脚本顶部 `BASE` 可切 |
| SSL | 已处理 | 私有化自签证书 → `VERIFY_SSL=False`（受信环境可改 True） |
| 依赖 | **零第三方依赖** | 仅标准库 `urllib`+`ssl`，无需 `pip install` |
| `SPACE_ID` / `FATHER_ID` | 可选 | 留空则创建到应用默认位置；填写需两者同时给 |
| `ADMIN_USERS` / `MEMBER_USERS` | 可选 | 授权用 userid 列表 |
| 应用权限 | **假设已具备** | 自建应用需有「文档」权限，且被加入文档的「可调用应用」列表，否则返回 301002 无权限 |
| 子表锚点 URL | 用 `create_doc` 返回的 url 作基址 | 模板 `SHEET_URL_TPL = "{base_url}?tab={sheet_id}"`；若锚点参数不同改这一行。复用旧文档时兜底用 `DOC_URL_FALLBACK_TPL` |
| ECharts 图表 | 转为明细数据 | 企微「图表视图/仪表盘」各版本开放度不一，脚本先落地 100% 明细数据；图表可在企微端基于子表插入，或后续接 `smartsheet/charts/*` |
| 下钻链接类型 | 用 `FIELD_TYPE_URL` | 官方 add_fields 枚举未含「关联」，故用超链接字段 + 独立子表实现下钻（符合你的要求） |

---

## 1. 来源信息结构与功能点清单（待实现 → 已实现）

### 1.1 信息结构（字段 / 层级 / 数据关系）

| 结构 | 内容 | 落地子表 |
|---|---|---|
| 时间维度 | 2024-01 ~ 2026-09，共 33 期 | `01/02/03/12` 的「月份」列 |
| 工厂维度 | 本部(11+12/1A)、一炼钢(11)、二炼钢(12)、罗源(14)、泉州(13) | `07_工厂维度字典` + 各表 `FACTORY_DIV` 列 |
| 指标域① | 钢铁料耗 kg/t = 钢铁料消耗 ÷ 钢产量（比率不可加） | `01_趋势明细_钢铁料耗` |
| 指标域② | 炼钢成本 元/吨（成本中心 LGYS 分项） | `02_趋势明细_炼钢成本` |
| 衍生计算 | 同比（i-12）、环比（i-1） | `03_同比环比` |
| 血缘链路 | ODS → DWD 临时表 → DWS → ADS → 存储过程 | `04_血缘链路_按工厂`、`05_指标血缘矩阵_13列` |
| DWD 临时表 | TP003_TMP1_1 / 2_1 / 2 / 3 / 40 / 48 | `09_DWD临时表_*`（按工厂隔离） |
| ODS 原始层 | 8 列样本，按 FACTORY_PROD 过滤 | `10_ODS原始明细_*` |
| DWS 逐日 | 202609 全量 21 天 × 3 指标 | `08_DWS逐日明细_202609` |
| 指标体系 | IND_REG 7 条 + IND_REG_COST 2 条 | `06_指标体系注册` |

### 1.2 功能点清单

| # | 功能 | 实现方式 | 状态 |
|---|---|---|---|
| 1 | 创建文档 | `wedoc/create_doc` (doc_type=10 智能表格) | ✅ |
| 2 | 编辑/写入记录 | `wedoc/smartsheet/add_records`（分批） | ✅ |
| 3 | 查询/回读校验 | `smartsheet/get_records`（分页） | ✅ |
| 4 | 同步（增量/重跑） | `--docid` 复用已有文档 + `ensure_fields` 幂等建字段 | ✅ |
| 5 | 权限管理 | `wedoc/mod_doc_member`（1只读/2读写/7管理员） | ✅ |
| 6 | **下钻（超链接）** | `FIELD_TYPE_URL` + 独立子表 + `11_下钻链接索引` | ✅ |
| 7 | 空间/目录 | `create_doc` 的 `spaceid`+`fatherid` | ✅ |
| 8 | 子表增删改名 | `add_sheet` / `update_sheet` / `delete_sheet` | ✅ |
| 9 | 字段管理 | `get_fields` / `add_fields`（幂等去重，上限150列） | ✅ |
| 10 | 图表视图 | 视版本接 `smartsheet/charts/*` | ⚠️ 预留 |

---

## 2. 鉴权与接口说明

### 2.1 access_token

```
GET https://wecom.fjsg.com.cn/cgi-bin/gettoken?corpid=ID&corpsecret=SECRET
→ { "errcode":0, "errmsg":"ok", "access_token":"。.", "expires_in":7200 }
```
（公有云把域名换成 `https://qyapi.weixin.qq.com`，路径与参数完全一致）

- 每个应用独立 secret，token 需**分应用缓存**，不要每次调用都重新获取。
- 脚本做了**进程内 + 文件（`.wecom_token.json`）双缓存**，提前 5 分钟过期；
  遇 `40001/42001/41001` 自动强制刷新并重试。

### 2.2 接口清单（全部 `https://qyapi.weixin.qq.com/cgi-bin/`）

> 下表 Endpoint 均相对 `https://wecom.fjsg.com.cn/cgi-bin/`

| 用途 | Method | Endpoint | 关键入参 | 关键返回 |
|---|---|---|---|---|
| 获取 token | GET | `gettoken` | corpid, corpsecret | access_token, expires_in |
| 新建文档 | POST | `wedoc/create_doc` | spaceid, fatherid, **doc_type**(3文档/4表格/**10智能表格**/11智能文档), doc_name, admin_users | url, docid |
| 查询子表 | POST | `wedoc/smartsheet/get_sheet` | docid, need_all_type_sheet | sheet_list[].sheet_id/title/type |
| 新增子表 | POST | `wedoc/smartsheet/add_sheet` | docid, properties{title,index} | properties.sheet_id |
| 改名子表 | POST | `wedoc/smartsheet/update_sheet` | docid, properties{sheet_id,title} | properties |
| 查询字段 | POST | `wedoc/smartsheet/get_fields` | docid, sheet_id, offset, limit | field_list[] |
| 新增字段 | POST | `wedoc/smartsheet/add_fields` | docid, sheet_id, fields[{field_title,field_type}] | field_list |
| **新增记录** | POST | `wedoc/smartsheet/add_records` | docid, sheet_id, key_type, records[].values | records[] |
| 查询记录 | POST | `wedoc/smartsheet/get_records` | docid, sheet_id, offset, limit | records[] |
| 文档权限 | POST | `wedoc/mod_doc_member` | docid, update_file_member_list[{type:1,auth,userid}] | — |
| 查询权限 | POST | `wedoc/doc_get_auth` | docid | 查看规则/通知范围 |

### 2.3 字段类型（16 种，add_fields 枚举）

`FIELD_TYPE_TEXT` `NUMBER` `CHECKBOX` `DATE_TIME` `IMAGE` `USER` `URL` `SELECT`
`SINGLE_SELECT` `PROGRESS` `PHONE_NUMBER` `EMAIL` `LOCATION` `CURRENCY` `PERCENTAGE` `BARCODE`

### 2.4 单元格值（CellValue）—— 最容易写错的地方

```jsonc
// 文本
"月份": [{"type":"text","text":"2026-09"}]
// 数字（直接传 double）
"数值": 1055.09
// 链接（下钻字段）—— 数组目前只展示一个
"下钻链接": [{"type":"url","text":"▶ 下钻 DWD 临时表 · 三明一炼钢","link":"https://doc.weixin.qq.com/smartsheet/<docid>?tab=<sheet_id>"}]
```

`add_records` 统一用 `"key_type":"CELL_VALUE_KEY_TYPE_FIELD_TITLE"`（按列标题写入，可读且不依赖 field_id）。

---

## 3. 文档组织形式与数据映射规则

一个智能表格文档 = **21 张子表**，命名带序号前缀保证顺序。

### 3.1 下钻链（4 层，全部用超链接字段串联）

```
L1 01/02/03/12 趋势·同比环比·对标
        │  「下钻链接」(URL)
        ▼
L2 04_血缘链路_按工厂          ODS→DWD→DWS→ADS + 存储过程
        │  「下钻链接」(URL)
        ▼
L3 09_DWD临时表_<工厂>         TP003_TMP1_* 明细（按 FACTORY_DIV 过滤）
        │  「下钻链接」(URL)
        ▼
L4 10_ODS原始明细_<工厂>       ODS 最底层原始字段（按 FACTORY_PROD 过滤）
        │  「血缘回溯链接」(URL)
        ▼
   05_指标血缘矩阵_13列
```

`11_下钻链接索引` 把上述全部路径枚举成 28 行链接总表，可直接点。

### 3.2 子表清单（干跑实测）

| 子表 | 列数 | 行数 | 说明 |
|---|---:|---:|---|
| 00_说明与口径 | 2 | 14 | 口径、批次、缺口、异常、下钻用法 |
| 01_趋势明细_钢铁料耗 | 8 | 152 | 月份×工厂 |
| 02_趋势明细_炼钢成本 | 8 | 109 | 同上（泉州全空） |
| 03_同比环比 | 11 | 261 | 含上期值/去年同期值 |
| 04_血缘链路_按工厂(L2) | 11 | 10 | 5 厂 × 2 指标 |
| 05_指标血缘矩阵_13列 | 14 | 8 | 13 列原样 + 链接 |
| 06_指标体系注册 | 7 | 9 | 7 生产 + 2 成本 |
| 07_工厂维度字典 | 7 | 12 | 5 厂 + 7 个 ZB→DIV |
| 08_DWS逐日明细_202609 | 9 | 63 | 3 指标 × 21 天 |
| 09_DWD临时表_一炼钢11 | 17 | 8 | **仅 11** |
| 09_DWD临时表_二炼钢12 | 17 | 9 | **仅 12** |
| 09_DWD临时表_本部三明11+12 | 17 | 21 | 11/12/11+12/1A |
| 09_DWD临时表_罗源14 / 泉州13 | 17 | 1+1 | 区分说明行 |
| 10_ODS原始明细_一炼钢11 | 12 | 5 | **仅 FACTORY_PROD=11** |
| 10_ODS原始明细_二炼钢12 | 12 | 3 | **仅 12** |
| 10_ODS原始明细_本部三明11+12 | 12 | 8 | 11+12 |
| 10_ODS原始明细_罗源14 / 泉州13 | 12 | 1+1 | 区分说明行 |
| 11_下钻链接索引 | 6 | 28 | 超链接总表 |
| 12_最新月对标_202609 | 6 | 5 | 2026-09 五厂对标 |

**合计 729 行 / 21 子表。**

### 3.3 关键映射规则

- **工厂隔离**：一炼=11、二炼=12、本部=11+12(+1A)、罗源=14、泉州=13；
  DWD 用 `FACTORY_DIV/FACTORT_CODE` 过滤，ODS 用 `FACTORY_PROD` 过滤，罗源/泉州给出「自有 MES + 落地表」区分说明行。
- **工厂列定位**：按**列名**查找 `FACTORY_DIV`/`FACTORT_CODE`。
  ⚠️ 原 HTML 有 bug：`TP003_TMP1_2_1` 首列是 `REC_CREATE_TIME`、FACTORY_DIV 在第 2 列，
  写死下标 0 会把该表几乎全部误过滤（本部只出 1 行，应为 4 行）。脚本已修正，**原 HTML 也已同步修复**。
- **比率不可加**：钢铁料耗=分子/分母，先按基地聚合再相除，不在行级做平均。
- **空值**：源为 `null` 的行直接不生成（不留 0，避免污染均值）。
- **数据一致性**：源 `steel.benbu` 数组 34 值 vs 月份 33 期，末尾未对应月份的值忽略，并在 `00_说明与口径` 中如实标注。

---

## 4. 异常处理

| 场景 | 处理 |
|---|---|
| 鉴权失败 `40001/42001/41001` | 强制刷新 token 后自动重试（最多 `MAX_RETRY` 次） |
| 接口限流 `45009/45033/-1` | 指数退避 `min(2^n,30)s` + 随机抖动后重试 |
| 网络异常 | 同样退避重试；超限抛 `WecomError` |
| 参数错误 `40058/41004`、无权限 `301002` | 不重试，直接抛出并打印 errcode/path，便于定位 |
| 分页 | `get_fields`/`get_records` 均 `offset+limit` 循环到取完；`iter_records` 生成器 |
| 大数据量 | `add_records` 按 `BATCH_SIZE=100` 分批（单表上限 10 万行）；字段按 20 列分批（上限 150 列） |
| 幂等重跑 | `ensure_fields` 按标题去重；`--docid` 复用文档并按标题复用子表，不重复建 |
| 域名/超时 | 统一 30s 超时，失败退避 |

---

## 5. 使用方式

```bash
# 0) 无需安装依赖（纯标准库）。如需显式指定密钥：
#    set WECOM_CORPSECRET=xxxx          (Windows CMD)
#    export WECOM_CORPSECRET=xxxx       (bash)

# 1) 干跑（不调用任何写接口，验证结构 + 串厂自检）
python wecom_smartsheet_sync.py --dry-run

# 3) 正式落地
python wecom_smartsheet_sync.py

# 4) 复用已有文档增量同步
python wecom_smartsheet_sync.py --docid <已有docid>

# 5) 小样本试写（每表最多 N 行，先验证字段/权限）
python wecom_smartsheet_sync.py --limit 5
```

### 调用示例（单接口，便于你自测凭据）

```bash
# 取 token
curl -k "https://wecom.fjsg.com.cn/cgi-bin/gettoken?corpid=$CORPID&corpsecret=$SECRET"

# 新建智能表格
curl -k -X POST "https://wecom.fjsg.com.cn/cgi-bin/wedoc/create_doc?access_token=$TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"doc_type":10,"doc_name":"测试智能表格"}'

# 写一行（含下钻超链接）
curl -k -X POST "https://wecom.fjsg.com.cn/cgi-bin/wedoc/smartsheet/add_records?access_token=$TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "docid":"<DOCID>","sheet_id":"<SHEET_ID>",
    "key_type":"CELL_VALUE_KEY_TYPE_FIELD_TITLE",
    "records":[{"values":{
      "月份":[{"type":"text","text":"2026-09"}],
      "数值":1055.09,
      "下钻链接":[{"type":"url","text":"▶ 下钻","link":"https://doc.weixin.qq.com/smartsheet/<DOCID>?tab=<SHEET_ID>"}]
    }}]}'
```

---

## 6. 附：数据抽取

`report_data.json` 由 `_extract_report_data.js` 从 HTML 原样抽取（含血缘矩阵 8×13），
确保与源报表**逐字段一致**，不做手工转录：

```bash
node _extract_report_data.js
```
