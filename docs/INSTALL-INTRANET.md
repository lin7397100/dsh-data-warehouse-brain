# 内网 / 连不上 GitHub 时的安装办法

> 症状：`dsh plugin … add github:lin7397100/dsh-data-warehouse-brain` 卡在
> `GET https://codeload.github.com/…/tar.gz/… error (UND_ERR_CONNECT_TIMEOUT)` → `fetch failed`。
> 原因：`github:` 这种 spec 由 pnpm 直接去 **codeload.github.com** 拉 tar 包，与包本身无关
> （本包零运行时依赖，2.36MB，自带 `patch` 与技能）。
>
> 目标：让"装插件"不再依赖 GitHub。下面四条路线按**见效速度**排，A/B 可今天落地，C/D 是长期治理。

---

## 0. 先花 10 秒判断环境（在服务器上跑）

```bash
curl -sS -o /dev/null -w 'github=%{http_code}\n'   --max-time 8 https://github.com/
curl -sS -o /dev/null -w 'codeload=%{http_code}\n' --max-time 8 https://codeload.github.com/
curl -sS -o /dev/null -w 'npmmirror=%{http_code}\n' --max-time 8 https://registry.npmmirror.com/
env | grep -iE 'https?_proxy|no_proxy' || echo '（无代理环境变量）'
```

| 结果 | 走哪条 |
|---|---|
| `codeload` 通 | 其实可以直接装；若时通时不通 → C |
| 有公司代理且 `https_proxy` 已设 | 先试 `HTTPS_PROXY=… dsh plugin … add github:…`；不行走 A/B |
| `npmmirror` 通 | **A**（内网 npm 源）或直接发公网 npm |
| 三个都不通 | **B**（本地目录分发，唯一稳的） |

---

## A. 内网 npm 源（长期最优，一次发布全员受益）

原理：把包发到内网 Nexus / Verdaccio，之后每台机器 `pnpm add @sansteel/dsh-data-warehouse-brain@1.0.1`，**完全不碰 GitHub**，且支持版本、缓存与离线重装。

### A1. 若已有公司 Nexus（推荐直接用）

```bash
# 一次性：发布
npm config set @sansteel:registry https://nexus.corp/repository/npm-hosted/
npm config set //nexus.corp/repository/npm-hosted/:_authToken "$NEXUS_TOKEN"
npm publish --registry https://nexus.corp/repository/npm-hosted/

# 每台机器：安装
dsh plugin --profile web add @sansteel/dsh-data-warehouse-brain@1.0.1
```

> 若 Nexus 走 group 仓库，把 `@sansteel` 的 scope 指向 hosted，group 再聚合 proxy+hosted。

### A2. 若没有 Nexus：本机起 Verdaccio（5 分钟）

```bash
docker run -d --name verdaccio -p 4873:4873 \
  -v /data/verdaccio:/verdaccio/storage verdaccio/verdaccio:5

# 建账号（首次）
npm adduser --registry http://127.0.0.1:4873

# 发布
npm publish --registry http://127.0.0.1:4873
```

### A3. 客户端指向内网源

`$DSH_HOME/profiles/web/.npmrc`（或用户级 `~/.npmrc`）：

```ini
@sansteel:registry=http://10.233.2.32:4873/
```

然后正常装：

```bash
dsh plugin --profile web add @sansteel/dsh-data-warehouse-brain@1.0.1
```

> 优点：`updateBundle` 可用、能锁版本、能回滚；pnpm 只连内网，稳定。

---

## B. 服务器本地目录分发（零新服务，今天就能用）

原理：把解包后的目录放在服务器共享路径，所有用户从**本地路径**安装。全程零网络。

### B1. 一次性准备（管理员）

```bash
# 1) 传包（从你自己的电脑）
scp sansteel-dsh-data-warehouse-brain-1.0.1.tgz user@10.233.2.32:/tmp/
#    校验：sha256sum → 8af47103e77fbf697cbaeb0cdef030eea9eb6b58b62282e23626e397363a891d

# 2) 放到带版本号的共享目录（建议只读）
mkdir -p /opt/dsh-plugins/sansteel-dsh-data-warehouse-brain/1.0.1
tar xzf /tmp/sansteel-dsh-data-warehouse-brain-1.0.1.tgz \
    -C /opt/dsh-plugins/sansteel-dsh-data-warehouse-brain/1.0.1 --strip-components=1
chmod -R a+rX /opt/dsh-plugins
```

### B2. 每个用户安装（两条路任选）

**图形界面（最省事）**：设置 → 插件 → 安装插件 → 填

```
/opt/dsh-plugins/sansteel-dsh-data-warehouse-brain/1.0.1
```

**或命令行**（用仓库里的脚本，自动补 `dsh.profile.bundles`）：

```bash
# 脚本在本包的 scripts/ 目录；tgz 或已解包目录都行
bash scripts/install_offline.sh /opt/dsh-plugins/sansteel-dsh-data-warehouse-brain/1.0.1 \
     --home /data/dsh-users/230012/.dsh --profile web
```

脚本做的事：校验包名/版本 → 优先 `dsh plugin add file:…`（否则 pnpm，再否则直接铺 `node_modules`）→ 把包名追加进 `dsh.profile.bundles`（带 `package.json.bak-dwb` 备份）→ 打印技能数并提示重启。

### B3. 多用户批量（管理员）

```bash
for home in /data/dsh-users/*/.dsh; do
  [ -d "$home/profiles/web" ] || continue
  echo "== $home"
  bash scripts/install_offline.sh \
    /opt/dsh-plugins/sansteel-dsh-data-warehouse-brain/1.0.1 \
    --home "$home" --profile web
  # 用 root 装会把文件写成 root 所有，装完记得归还原主：
  chown -R "$(stat -c %u:%g "$home")" "$home/profiles/web"
done
```

### B4. 升级（以后每次都一样）

```bash
# 新版本放新目录，不动旧目录（可回滚）
mkdir -p /opt/dsh-plugins/dsh-data-warehouse-brain/1.0.2
tar xzf /tmp/sansteel-…-1.0.2.tgz -C /opt/dsh-plugins/dsh-data-warehouse-brain/1.0.2 --strip-components=1
bash scripts/install_offline.sh /opt/dsh-plugins/dsh-data-warehouse-brain/1.0.2 --home /data/dsh-users/230012/.dsh
```

> 团队根供给按包内版本号判断：版本变了才会重铺 `$DSH_HOME/dwb-team` 的脚本，所以**升级必须改版本号**，不能原地覆盖同版本号。

---

## C. GitHub 代理（网络有加速代理时）

```bash
# 直接把代理 URL 当 tarball 装
dsh plugin --profile web add \
  https://<代理前缀>/https://github.com/lin7397100/dsh-data-warehouse-brain/archive/refs/tags/v1.0.1.tar.gz

# 或给 pnpm 挂代理（能连 codeload 就恢复 github: 方式）
HTTPS_PROXY=http://proxy.corp:8080 HTTP_PROXY=http://proxy.corp:8080 \
  dsh plugin --profile web add github:lin7397100/dsh-data-warehouse-brain@v1.0.1
```

> 注意：`github:` 走的是 `fetch`（codeload），不是 git，所以 `~/.gitconfig` 的 `url.insteadOf` **不能**救它；必须让 pnpm 的 HTTPS 出口通，或改用 A/B。

---

## D. 内网 Git 镜像（有 GitLab/Gitea 时）

```bash
# 镜像仓库（GitLab 支持 pull mirror，或定时 git clone --mirror）
git clone --mirror git@github.com:lin7397100/dsh-data-warehouse-brain.git
# 推到内网
git push --mirror git@gitlab.corp:dsh/dsh-data-warehouse-brain.git

# 每台机器
dsh plugin --profile web add git+ssh://git@gitlab.corp/dsh/dsh-data-warehouse-brain.git#v1.0.1
```

> 内网 git 也要能 `git clone` 成功；`git+ssh` spec 由 pnpm 调 git 克隆，不走 codeload，通常比 github: 稳。

---

## 排查清单（装完不生效时）

| 现象 | 原因 | 处理 |
|---|---|---|
| 装完没有「数仓专家团」侧栏 | 组合包没被选中 | `dsh.profile.bundles` 里要有 `@sansteel/dsh-data-warehouse-brain`；图形界面安装会自动加 |
| Agent 选择器没有冶衡 | 没重启实例 | preset 与客户端插件在进程启动时装配，**必须重启该用户的 DSH** |
| `--dump-config` 里 preset 只有 4 个 | 包没进入组合 | 同上；或包名解析失败（看 stderr 的 `Repository not found` / `Cannot find module`） |
| 面板 401 | 未带登录态 | 从 `dsh web` 打印的 `?token=` URL 打开一次，浏览器带上 cookie 后接口才通 |
| 装了但技能为空 | `bundledSkillDir` 解析不到 | 确认 `package.json` 里有 `"exports": {"./package.json": "./package.json"}`（本包已带） |
| 两个侧栏入口 | 旧的 `@local/dwb-team-panel` 还在 | 移除旧插件，或禁用其条目 |

## 一句话建议

**今天**：走 B（本地目录 + `install_offline.sh`），10 分钟让 `10.233.2.32` 上所有人能装。
**这周**：把包发到内网 Nexus/Verdaccio（A），之后升级、回滚、批量部署都不再依赖任何外网。
