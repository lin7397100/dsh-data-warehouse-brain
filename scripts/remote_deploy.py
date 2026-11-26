# -*- coding: utf-8 -*-
"""remote_deploy.py —— 上传并原地升级远端某个用户的 DSH profile

设计约束：本机沙箱禁止「用管道捕获子进程输出」（Node/Python 的 capture_output
一律 EPERM），因此这里：
  - 打包在调用方（PowerShell）完成，本脚本只挑最新的 .tgz；
  - 上传用 paramiko 在进程内完成（不走子进程）；
  - 远端命令用 ssh 但 stdio 继承，输出直接打到终端。

用法：
  set REMOTE_PW=...
  python scripts/remote_deploy.py --host H --user U --password-env REMOTE_PW \\
      --target-user 230012 --profile web [--restart] [--dry-run]
"""
import argparse
import hashlib
import os
import subprocess
import sys
import tempfile

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASKPASS_NT = '@echo off\r\necho %DWB_SSH_PW%\r\n'

DEPLOY = r'''#!/bin/bash
set -euo pipefail
TGZ="__TGZ__"
PKGDIR="__PKGDIR__"
ROOT="__ROOT__"
USER_ID="__UID__"
STAMP=$(date +%Y%m%d-%H%M%S)

echo "[3/6] 校验完整性"
actual=$(sha256sum "$TGZ" | cut -d' ' -f1)
[ "$actual" = "__SHA__" ] || { echo "FAIL sha256: $actual"; exit 1; }
echo "  sha256 OK"

echo "[4/6] 备份并替换"
if [ -d "$PKGDIR" ]; then
  cp -a "$PKGDIR" "${PKGDIR}.bak-${STAMP}"
  echo "  backup -> ${PKGDIR}.bak-${STAMP}"
fi
STAGE=$(mktemp -d)
tar xzf "$TGZ" -C "$STAGE"
rm -rf "$PKGDIR"
mkdir -p "$(dirname "$PKGDIR")"
cp -a "$STAGE/package" "$PKGDIR"
rm -rf "$STAGE"
chown -R "$USER_ID:$USER_ID" "$PKGDIR" 2>/dev/null || true

echo "[5/6] 校验"
V=$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$PKGDIR/package.json" | head -1)
echo "  version=$V"
printf "  files: "; find "$PKGDIR" -type f | wc -l
printf "  mcp.js: "; [ -f "$PKGDIR/mcp.js" ] && echo yes || echo NO
printf "  subpath-fix(baseURI): "; grep -c 'document.baseURI' "$PKGDIR/client.js" || true
printf "  presets: "; grep -cE '^    - id: preset-' "$PKGDIR/cordis.patch.yml" || true
printf "  preset-inner-mcp(expect 0): "; grep -cE '^ +- id: mcp-' "$PKGDIR/cordis.patch.yml" || true
printf "  skills: "; find "$PKGDIR/skills" -name SKILL.md | wc -l
printf "  bundle-selected: "; grep -q '@sansteel/dsh-data-warehouse-brain' "$ROOT/package.json" && echo yes || echo NO
VH=/data/dsh-users/$USER_ID/.dsh/dwb-team
[ -d "$VH" ] && echo "$V" > "$VH/.dwb-version"

if [ "__RESTART__" = "1" ]; then
  echo "[6/6] 重启 dsh-user@$USER_ID"
  sudo -n systemctl restart "dsh-user@$USER_ID"
  for i in $(seq 1 20); do
    sleep 2
    s=$(sudo -n systemctl is-active "dsh-user@$USER_ID" || true)
    [ "$s" = "active" ] && break
  done
  echo "  status=$s"
  PORT=$(grep -oE '[0-9]+' "/data/dsh-users/$USER_ID/port.env" | head -1)
  echo "  port=$PORT"
  echo -n "  panel API (expect 401 = host half alive): "
  curl -s -o /dev/null -w '%{http_code}\n' "http://10.233.2.32:$PORT/dwb-team/api/root" || true
  echo -n "  subpath API (expect 401 or 404-with-prefix): "
  curl -s -o /dev/null -w '%{http_code}\n' "http://10.233.2.32:$PORT/dsh/dwb-team/api/root" || true
fi
echo "DONE"
'''


def sftp_put(host, user, pw, local, remote, port=22):
    import paramiko
    t = paramiko.Transport((host, port))
    t.connect(username=user, password=pw)
    try:
        sftp = paramiko.SFTPClient.from_transport(t)
        try:
            sftp.put(local, remote)
            return sftp.stat(remote).st_size
        finally:
            sftp.close()
    finally:
        t.close()


def ssh_run(host, user, pw, script_path, port=22):
    """stdio 继承，避免沙箱的管道限制。"""
    tmpdir = tempfile.mkdtemp(prefix='dwb-ssh-')
    askpass = os.path.join(tmpdir, 'askpass.cmd') if os.name == 'nt' else os.path.join(tmpdir, 'askpass.sh')
    with open(askpass, 'w', encoding='ascii', newline='') as f:
        f.write(ASKPASS_NT if os.name == 'nt' else "#!/bin/sh\nprintf '%s\\n' \"$DWB_SSH_PW\"\n")
    if os.name != 'nt':
        os.chmod(askpass, 0o700)
    env = dict(os.environ)
    env.update({
        'DWB_SSH_PW': pw, 'SSH_ASKPASS': askpass, 'SSH_ASKPASS_REQUIRE': 'force',
        'DISPLAY': env.get('DISPLAY') or 'dwb', 'GIT_TERMINAL_PROMPT': '0',
    })
    cmd = [
        'ssh', '-o', 'StrictHostKeyChecking=accept-new',
        '-o', 'PreferredAuthentications=password,keyboard-interactive',
        '-o', 'PubkeyAuthentication=no',
        '-o', 'NumberOfPasswordPrompts=1', '-o', 'ConnectTimeout=20',
        '-p', str(port), '%s@%s' % (user, host), 'bash -s',
    ]
    with open(script_path, 'rb') as f:
        return subprocess.run(cmd, stdin=f, env=env).returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', required=True)
    ap.add_argument('--user', required=True)
    ap.add_argument('--password-env', required=True)
    ap.add_argument('--target-user', required=True)
    ap.add_argument('--profile', default='web')
    ap.add_argument('--restart', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    pw = os.environ.get(a.password_env)
    if not pw:
        print('FAIL: %s 为空' % a.password_env, file=sys.stderr)
        return 2

    cands = [f for f in os.listdir(PKG) if f.endswith('.tgz')]
    if not cands:
        print('FAIL: 仓库根没有 .tgz，请先 npm pack', file=sys.stderr)
        return 2
    tgz = max(cands, key=lambda f: os.path.getmtime(os.path.join(PKG, f)))
    local = os.path.join(PKG, tgz)
    sha = hashlib.sha256(open(local, 'rb').read()).hexdigest()
    print('[1/6] 包: %s (%d KB) sha256=%s' % (tgz, os.path.getsize(local) // 1024, sha[:16] + '...'))

    root = '/data/dsh-users/%s/.dsh/profiles/%s' % (a.target_user, a.profile)
    pkgdir = root + '/node_modules/@sansteel/dsh-data-warehouse-brain'
    remote_tgz = '/tmp/' + tgz

    if a.dry_run:
        print('[dry-run] 上传 %s → %s，解包覆盖 %s，restart=%s' % (tgz, remote_tgz, pkgdir, a.restart))
        return 0

    size = sftp_put(a.host, a.user, pw, local, remote_tgz)
    print('[2/6] 上传完成 %d B' % size)
    if size != os.path.getsize(local):
        print('FAIL: 上传大小不一致', file=sys.stderr)
        return 1

    body = (DEPLOY.replace('__TGZ__', remote_tgz)
                  .replace('__PKGDIR__', pkgdir)
                  .replace('__ROOT__', root)
                  .replace('__UID__', a.target_user)
                  .replace('__SHA__', sha)
                  .replace('__RESTART__', '1' if a.restart else '0'))
    sh = os.path.join(PKG, '_deploy_remote.sh')
    with open(sh, 'w', encoding='utf-8', newline='\n') as f:
        f.write(body)
    try:
        rc = ssh_run(a.host, a.user, pw, sh)
    finally:
        os.remove(sh)
    return rc


if __name__ == '__main__':
    sys.exit(main())
