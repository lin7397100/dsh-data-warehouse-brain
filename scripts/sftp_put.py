# -*- coding: utf-8 -*-
"""sftp_put.py —— 用密码 SFTP 上传文件（Windows 原生，无外部依赖）

用法：python scripts/sftp_put.py --host H --user U --password-env PW --local A --remote B
"""
import argparse
import os
import sys

try:
    import paramiko
except ImportError:
    paramiko = None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', required=True)
    ap.add_argument('--user', required=True)
    ap.add_argument('--port', type=int, default=22)
    ap.add_argument('--password-env', required=True)
    ap.add_argument('--local', required=True)
    ap.add_argument('--remote', required=True)
    a = ap.parse_args()

    pw = os.environ.get(a.password_env)
    if not pw:
        print('FAIL: 密码环境变量为空', file=sys.stderr)
        return 2
    if paramiko is None:
        print('FAIL: 缺 paramiko（pip install paramiko）', file=sys.stderr)
        return 2

    size = os.path.getsize(a.local)
    transport = paramiko.Transport((a.host, a.port))
    transport.connect(username=a.user, password=pw)
    sftp = paramiko.SFTPClient.from_transport(transport)
    try:
        sftp.put(a.local, a.remote)
        st = sftp.stat(a.remote)
        print('上传完成: %s → %s（%d B，远端 %d B）' % (a.local, a.remote, size, st.st_size))
        return 0 if st.st_size == size else 1
    finally:
        sftp.close()
        transport.close()


if __name__ == '__main__':
    sys.exit(main())
