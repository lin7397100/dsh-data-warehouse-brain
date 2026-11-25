"""
企业微信发送器 - 发送文件到企业微信群聊
基于 report-exporter 的 appchat/send 方案修改
"""

import os
import requests

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
CONFIG = {
    "WECOM_BASE_URL":     os.getenv("WECOM_BASE_URL",  "https://wecom.fjsg.com.cn"),
    "WECOM_CHATID":       os.getenv("WECOM_CHATID",    "MTk3MDMyNTYwMzAxNTYxMjpHygrR7KYUifUkH0BE_m4"),
    "TOKEN_API_URL":      os.getenv("TOKEN_API_URL",   "http://eplat.fjsg.com/service/D_A_SMBBRAOC00_MRDJ_TOKEN"),
    "TOKEN_CLIENT_ID":    os.getenv("TOKEN_CLIENT_ID", "sgoc-oc01"),
    "TOKEN_CLIENT_SECRET":os.getenv("TOKEN_CLIENT_SECRET","FCCDFACD0DED39AEE63462C112A4F412"),
}


class WeComSender:
    """企业微信群聊发送器"""

    @staticmethod
    def get_token():
        """获取企微 Token"""
        payload = {
            'clientId': CONFIG["TOKEN_CLIENT_ID"],
            'clientSecret': CONFIG["TOKEN_CLIENT_SECRET"],
            'params': {},
            'offset': 0,
            'limit': 10,
            'userId': ''
        }

        resp = requests.post(CONFIG["TOKEN_API_URL"], json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        blocks = data.get('__blocks__', {})
        sys_info = data.get('__sys__', {})
        if not blocks or 'result' not in blocks:
            msg = sys_info.get('msg', '未知错误')
            raise Exception(f"Token 获取失败: {msg}")

        return data['__blocks__']['result']['rows'][0][0]

    @staticmethod
    def upload_file(token, file_path):
        """上传文件到企微临时素材库"""
        url = f"{CONFIG['WECOM_BASE_URL']}/cgi-bin/media/upload?access_token={token}&type=file"

        with open(file_path, 'rb') as f:
            resp = requests.post(url, files={"media": (os.path.basename(file_path), f, "application/octet-stream")}, timeout=60)

        resp.raise_for_status()
        data = resp.json()

        if data.get('errcode', 0) != 0:
            raise Exception(f"文件上传失败: {data.get('errmsg')}")

        return data['media_id']

    @staticmethod
    def send_file(token, media_id, chatid):
        """发送文件消息到群聊（appchat/send）"""
        url = f"{CONFIG['WECOM_BASE_URL']}/cgi-bin/appchat/send?access_token={token}"

        payload = {
            "chatid":  chatid,
            "msgtype": "file",
            "file":    {"media_id": media_id},
        }

        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if data.get('errcode', 0) != 0:
            raise Exception(f"文件发送失败: {data.get('errmsg')}")

        return True

    @staticmethod
    def send(file_path, chatid=None):
        """发送文件到企微群聊"""
        chatid = chatid or CONFIG["WECOM_CHATID"]

        print(f"📎 文件: {os.path.basename(file_path)}")
        print(f"💬 目标群聊: {chatid}")
        print(f"🌐 企微API: {CONFIG['WECOM_BASE_URL']}")

        print("[1/3] 正在获取企微Token...")
        token = WeComSender.get_token()
        print("      Token 获取成功")

        print(f"[2/3] 正在上传 {os.path.basename(file_path)}...")
        media_id = WeComSender.upload_file(token, file_path)
        print(f"      media_id: {media_id}")

        print(f"[3/3] 正在发送到群聊 {chatid}...")
        WeComSender.send_file(token, media_id, chatid)
        print("      发送成功")

        print("\n✅ 成功！文件已发送到企微群聊。")
