# 数仓智脑专家团 · DSH 组合包

一个 DSH（DeepSeek Harness）组合包：装上就有 **24 位数据仓库专家 + 65 个技能 + 侧边栏看板**。

- **主理人冶衡（Axis）**：拆解任务、按白名单派发专家、验收汇总，自己不取数、不写 SQL。
- **22 位专家**：语义层（铨度）、本体（鼎元）、元数据与血缘（舆图）、数仓开发（淬锋）、质量与根因（砺真）、洞察可视化（明鉴）、治理（守钧）、指标构建（矩衡）、记忆与技能进化、监管（监衡）、5S 开发/答疑、成本域（成枢）、生产域（管枢）等。
- **快问车道**：单指标裸查，直达物化 SQL，不派专家。

## 安装

### 方式一：图形界面（推荐）

1. 打开 DSH → 设置 → **插件** → **安装插件**
2. 填入本仓库地址：`https://github.com/lin7397100/dsh-data-warehouse-brain`
3. 安装后启用，**完全退出 DSH 再重新打开**
4. 新会话的 Agent 选择器里会出现「冶衡 · 首席数仓编排师」等 24 个 preset；左侧栏出现「数仓专家团」看板

### 方式二：命令行

```bash
dsh plugin --profile web add github:lin7397100/dsh-data-warehouse-brain@v1.0.1
```

### 方式三：离线 / 内网服务器（无法访问 codeload.github.com 时）

`github:` 安装会去 `codeload.github.com` 拉 tar 包，某些内网或境内网络会**连接超时**。此时用本地目录安装，全程不走网络：

```bash
# 1) 把 tgz 传到目标机器（这里从你自己的电脑 scp）
scp sansteel-dsh-data-warehouse-brain-1.0.1.tgz user@server:/tmp/

# 2) 解包成目录（npm 包的根在 package/）
mkdir -p /opt/dsh-plugins && tar xzf /tmp/sansteel-dsh-data-warehouse-brain-1.0.1.tgz -C /opt/dsh-plugins

# 3a) 图形界面：设置 → 插件 → 安装插件 → 填绝对路径 /opt/dsh-plugins/package
# 3b) 或命令行：
dsh plugin --profile web add file:/opt/dsh-plugins/package
```

命令行装完还要把组合包选中（图形界面会自动选中）：编辑 `$DSH_HOME/profiles/web/package.json`，在 `dsh.profile.bundles` 末尾加一行

```json
"@sansteel/dsh-data-warehouse-brain"
```

然后重启 DSH。

> 校验下载完整性：`sha256sum sansteel-dsh-data-warehouse-brain-1.0.1.tgz`
> 校验完整性：`sha256sum <tgz>`，与 GitHub Release 附件说明里的值比对。
如果所在网络有 GitHub 加速代理，也可以直接把代理 URL 当 tarball 装：

```bash
dsh plugin --profile web add https://<代理前缀>/https://github.com/lin7397100/dsh-data-warehouse-brain/archive/refs/tags/v1.0.1.tar.gz
```

> 内网服务器（连不上 codeload）的完整方案——内网 npm 源、本地目录分发、批量部署、升级回滚、排查清单——见 [`docs/INSTALL-INTRANET.md`](docs/INSTALL-INTRANET.md)，另附一键脚本 `scripts/install_offline.sh`。
>
> 想发到 npm（之后所有人一条命令装完、不碰 GitHub）：见 [`docs/PUBLISH-NPM.md`](docs/PUBLISH-NPM.md)，附发布脚本 `scripts/publish_npm.ps1`。

> 安装后**必须重启 DSH**：preset 组合与客户端插件在进程启动时装配。

## 你会得到什么

| 载荷 | 内容 |
|---|---|
| 24 个 preset | 1 主理人 + 22 专家 + 1 快问，含人设、工具集、上下文压缩、派发白名单 |
| 65 个技能 | 语义层 / 本体 / 四级指标 / 血缘 / 根因 / 质量 / 治理 / 看板 / 报告 / 企微交付 等，装完即出现在技能目录 |
| 侧边栏看板 | 专家名册、运行概览、路由记录、调度链路四个页签；同源只读 API `/dwb-team/api/*` |
| 团队运行脚本 | 闸门脚本（GATE-0/判型/断言/血缘）、台账、报表等，首启铺到团队根 |

## 首次启动做了什么

插件激活时把包内资产铺到**团队根**，默认 `$DSH_HOME/dwb-team`（Windows 为 `%USERPROFILE%\.dsh\dwb-team`）：

```
$DSH_HOME/dwb-team/
├── agents/        24 份人设 + references/ 详细规范
├── skills/        65 个技能（同时以 bundledSkillDir 挂给每个 preset）
├── tools/         闸门与取数脚本
├── scripts/       台账与报表脚本
├── panel/roster.json
├── observed/      运行时台账（用户数据，升级不覆盖）
└── knowledge/     用户自备知识（包内不含）
```

- 只在**版本变化**时重铺（`.dwb-version` 标记），`observed/`、`knowledge/`、`panel/overrides/` 永不覆盖。
- 想换位置：在插件配置里改 `teamRoot`。

## 配置

在 profile patch 里覆盖 `dwb-team` 行的 `config`：

```yaml
- id: dwb-team
  config:
    teamRoot: 'D:/data/dwb-team'   # 团队根，留空用 $DSH_HOME/dwb-team
```

环境变量：

| 变量 | 作用 |
|---|---|
| `DSH_HOME` | DSH 配置根，决定默认团队根 |
| `DWB_INTERNAL_MCP` | 设为 `1` 才启用内网 MCP（WeKnora 知识库、DB2、企微投递）。默认关闭 |
| `SG_MCP` | 设为 `off` 关闭全部 MCP 客户端 |
| `SG_EPLAT_MCP_URL` | EPLAT 5S 元数据 MCP 端点（Oracle 只读） |

## 能力边界（请先读）

- **不含知识语料**：`knowledge/`（DDL、口径、语料，约 36MB）不在包内。依赖本地知识检索的技能会自动降级到 WeKnora / DB2 通道；两者都不可用时如实说明「知识源缺失」，不编造。
- **内网 MCP 默认关**：WeKnora、DB2、企微等端点默认不可用，专家会走降级链。需要时设 `DWB_INTERNAL_MCP=1` 并保证网络可达。
- **闸门脚本是尽力而为**：`tools/` 下的闸门脚本在缺语料/缺依赖时会报错，此时专家应记录「闸门未启用」并继续，不得以闸门失败为由拒答。
- **数据不出本机**：面板只读本地文件；包内没有任何外部上报。

## 维护

```bash
python scripts/build_package.py --check   # 校验 patch / roster / 技能归属
python scripts/verify_package.py          # 发行前总校验（路径、元数据、一致性）
python scripts/build_package.py           # 改完 agents/*.md 后重建人设与名册
```

## 许可

MIT。`assets/avatars/` 为项目自绘头像；图标见 `icon.svg`。
