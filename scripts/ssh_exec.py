# -*- coding: utf-8 -*-
"""ssh_exec.py —— 用密码登录执行远程命令（Windows 原生，无 sshpass/plink 依赖）

原理：Windows OpenSSH 9.x 支持 SSH_ASKPASS + SSH_ASKPASS_REQUIRE=force。
我们把密码写进一个临时 askpass 脚本（用完即删），交给 ssh 自己读取，
避免密码出现在命令行参数、进程列表或任何持久文件里。

用法：
  python scripts/ssh_exec.py --host 10.233.2.32 --user dmx --password-env REMOTE_PW -- cmd...
  python scripts/ssh_exec.py --host h --user u --password-env PW --script local_sh_file
  python scripts/ssh_exec.py --host h --user u --password-env PW --sudo-env SUDO_PW -- cmd...

退出码：远端命令的退出码（连接失败返回 255）
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

ASKPASS_CMD = r"""@echo off
echo %~1 | findstr /C:"password" >nul && (
  echo %DWB_SSH_PW%
) || (
  echo %DWB_SSH_PW%
)
"""
ASKPASS_PS1 = r"""#!/bin/sh
printf '%s\n' "$DWB_SSH_PW"
"""


def make_askpass(tmpdir):
    """生成 askpass 脚本；密码经环境变量传入，不落盘明文。"""
    if os.name == 'nt':
        path = os.path.join(tmpdir, 'askpass.cmd')
        with open(path, 'w', encoding='ascii', newline='\r\n') as f:
            f.write('@echo off\r\necho %DWB_SSH_PW%\r\n')
    else:
        path = os.path.join(tmpdir, 'askpass.sh')
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(ASKPASS_PS1)
        os.chmod(path, 0o700)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', required=True)
    ap.add_argument('--user', required=True)
    ap.add_argument('--port', default='22')
    ap.add_argument('--password-env', required=True, help='存放密码的环境变量名')
    ap.add_argument('--script', help='把该本地文件当作远端脚本执行（bash -s）')
    ap.add_argument('--timeout', type=int, default=1800)
    ap.add_argument('cmd', nargs='*', help='远端命令')
    a = ap.parse_args()

    pw = os.environ.get(a.password_env)
    if not pw:
        print('FAIL: 环境变量 %s 为空' % a.password_env, file=sys.stderr)
        return 2

    tmpdir = tempfile.mkdtemp(prefix='dwb-ssh-')
    try:
        askpass = make_askpass(tmpdir)
        env = dict(os.environ)
        env['DWB_SSH_PW'] = pw
        env['SSH_ASKPASS'] = askpass
        env['SSH_ASKPASS_REQUIRE'] = 'force'
        env['DISPLAY'] = env.get('DISPLAY') or 'dwb'
        env['GIT_TERMINAL_PROMPT'] = '0'

        base = [
            'ssh',
            '-o', 'StrictHostKeyChecking=accept-new',
            '-o', 'PreferredAuthentications=password,keyboard-interactive',
            '-o', 'PubkeyAuthentication=no',
            '-o', 'NumberOfPasswordPrompts=1',
            '-o', 'ConnectTimeout=20',
            '-o', 'ServerAliveInterval=15',
            '-p', a.port,
            '%s@%s' % (a.user, a.host),
        ]
        if a.script:
            with open(a.script, 'rb') as f:
                payload = f.read()
            cmd = base + ['bash -s']
            proc = subprocess.run(cmd, input=payload, env=env, timeout=a.timeout)
        else:
            quote = ' '.join(a.cmd) if a.cmd else 'echo NO_COMMAND'
            proc = subprocess.run(base + [quote], env=env, timeout=a.timeout)
        return proc.returncode
    except subprocess.TimeoutExpired:
        print('FAIL: 远端命令超时', file=sys.stderr)
        return 124
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
