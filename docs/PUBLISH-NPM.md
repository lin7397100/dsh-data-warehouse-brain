# 发到 npm（让内网服务器一条命令装完）

> 目标：`dsh plugin --profile web add @<scope>/dsh-data-warehouse-brain@1.0.1`
> —— 不再传文件、不再依赖 GitHub、不再碰 codeload。
>
> 前提：本包**零运行时依赖、无构建步骤**，`npm publish` 后即可用；中国境内服务器把 registry 指到
> `https://registry.npmmirror.com` 就能直连（DSH 的默认 fallback 也是它）。

---

## 0. 先决定包名（这一步最容易卡住）

npm 的规则：`@scope/name` 里的 **scope 必须是你的**（npm 用户或组织）。当前包名是
`@sansteel/dsh-data-warehouse-brain`，能不能用取决于：

| 你的情况 | 做法 |
|---|---|
| 你在 npmjs.com 有组织 `sansteel`（Organizations 里能看到，你是 owner/member） | **不用改**，直接发 |
| 没有，但想用这个品牌名 | 去 npmjs.com → Organizations → **Create organization** 建 `sansteel`（公开包免费），再发 |
| 不想建组织 / 想立刻发 | **改成你自己的 scope**：`@lin7397100/dsh-data-warehouse-brain` |
| 想让人少打字 | **改成无 scope**：`dsh-data-warehouse-brain`（名字当前未被占用，已验证 E404） |

改名只需一条命令（会自动同步 patch 表达式、面板宿主行、client 模块 id，并跑总校验）：

```bash
python scripts/set_package_name.py @lin7397100/dsh-data-warehouse-brain
# 或
python scripts/set_package_name.py dsh-data-warehouse-brain
```

> 包里已内置 `publishConfig.access = "public"`，scope 包不会误发成私有（私有要付费，别人也装不了）。

## 1. 登录（在你自己的终端里做，别把 token 发到对话里）

```bash
npm login
# 浏览器/OTP 走完后
npm whoami
```

CI 或不想交互时才用 token：在 npmjs.com → Access Tokens 建 **Granular / Automation** token，
写进 `~/.npmrc`：

```ini
//registry.npmjs.org/:_authToken=${NPM_TOKEN}
```

> 用环境变量引用，不要把 token 明文写进仓库；更不要贴到聊天窗口。

## 2. 发布前自检（30 秒，避免发错内容）

```bash
python scripts/verify_package.py          # 27 项校验（含"包名三处一致"）
npm pack --dry-run                        # 看真实入包清单
npm view <你的包名> version               # E404 = 名字可用；有版本号 = 已被占
```

期望：verify 全绿、`npm pack` 约 337 个文件 / 2.4MB、`scripts/` 维护脚本不在包内。

## 3. 发布

```bash
npm publish --access public
```

- 开了 2FA 会让你输入一次性验证码（`--otp=123456` 也可）
- 成功后会打印 `+ @scope/name@1.0.1`
- 名字被别人抢注会报 `E404 Scope not found` 或 `E403 You do not have permission`

验证：

```bash
npm view @lin7397100/dsh-data-warehouse-brain version dist.tarball
curl -sS -o /dev/null -w '%{http_code}\n' https://registry.npmmirror.com/@lin7397100/dsh-data-warehouse-brain
```

## 4. 让 `10.233.2.32` 能装

npm 官方源在境内不稳，镜像同步通常 1–10 分钟：

```bash
# 触发/确认镜像同步（通常自动）
curl -sS https://registry.npmmirror.com/@lin7397100/dsh-data-warehouse-brain | head -c 200

# 在该用户 profile 里指定源（二选一）
echo '@lin7397100:registry=https://registry.npmmirror.com/' >> /data/dsh-users/230012/.dsh/profiles/web/.npmrc

# 然后安装（图形界面「安装源」也可以选「中国大陆镜像源」）
dsh plugin --profile web add @lin7397100/dsh-data-warehouse-brain@1.0.1
```

> 注意：pnpm 装 **带 scope 的包**时，`@scope:registry` 必须写在 `.npmrc` 里，否则仍会去官方源并超时。
> 无 scope 的包直接设 `registry=https://registry.npmmirror.com/` 即可。

## 5. 以后每次升级

```bash
# 1) 改代码/人设 → 重建 → 校验
python scripts/build_package.py && python scripts/verify_package.py

# 2) 升版本（会打 git tag）
npm version patch -m "v%s"      # 1.0.1 → 1.0.2
git push && git push --tags

# 3) 发布
npm publish --access public
```

> **版本号必须变**：团队根供给按包内版本号决定是否重铺 `$DSH_HOME/dwb-team` 的脚本。

## 6. 回滚与撤包

```bash
npm deprecate @scope/name@1.0.1 "有缺陷，请用 1.0.2"   # 推荐：保留可追溯
npm unpublish @scope/name@1.0.1                        # 仅 72 小时内；会破坏依赖它的锁文件
```

回滚到旧版：用户在 profile 里 `dsh plugin --profile web add @scope/name@1.0.0`（需该版本仍存在）。

## 7. 报错速查

| 报错 | 原因 | 处理 |
|---|---|---|
| `E402 Payment Required` | scoped 包默认私有 | 加 `--access public`（本包已内置 publishConfig） |
| `E404 Scope not found` | `@sansteel` 不是你的 | 建组织，或 `set_package_name.py` 换成自己的 scope |
| `E403 You do not have permission` | 名字被他人占用 / 未登录 | `npm whoami` 确认账号；换名或申请 |
| `E403 Two-factor authentication required` | 账号开了 2FA | 带 `--otp=xxxxxx`，或先在网页生成 token |
| `EPUBLISHCONFLICT` | 版本号已存在 | `npm version patch` 升版本再发 |
| `npm error code ENOTFOUND` | 网络/DNS | 换 `--registry https://registry.npmmirror.com`（发布只能发官方源） |
| 装完侧栏没出现 | 共享服务器的 registry 没指向镜像 | 见第 4 节的 `.npmrc`；或模板 `@scope:registry` 写错 |

> 发布**只能**发到官方 registry（`registry.npmjs.org`）；npmmirror 只做只读镜像。所以发布机器要能连官方源，
> 或让 CI 代发。

## 8. 发完之后 DSH 侧怎么用

```bash
# 用户侧（已是内网镜像源）
dsh plugin --profile web add @lin7397100/dsh-data-warehouse-brain@1.0.1
# 图形界面：插件 → 安装插件 → 填 @lin7397100/dsh-data-warehouse-brain@1.0.1
```

DSH 的插件管理器支持 registry 包名/版本，装完会自动选中组合包，`updateBundle` 也能用（比 Git 安装好维护）。
