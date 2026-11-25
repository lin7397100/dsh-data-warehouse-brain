"""
企业微信发送器 - 自动发送文件到企业微信群聊
"""

import os
import requests

# 企微配置
WECOM_BASE_URL = "https://wecom.fjsg.com.cn"
TOKEN_API_URL = "http://eplat.fjsg.com/service/D_A_SMBBRAOC00_MRDJ_TOKEN"
TOKEN_CLIENT_ID = "sgoc-oc01"
TOKEN_CLIENT_SECRET = "FCCDFACD0DED39AEE63462C112A4F412"
DEFAULT_CHATID = "MTk3MDMyNTYwMzAxNTYxMjpHygrR7KYUifUkH0BE_m4"


class WeComSender:
    """企业微信发送器（群聊模式）"""

    @staticmethod
    def get_token():
        """获取企微 Token（POST JSON 方式）"""
        payload = {
            "clientId": TOKEN_CLIENT_ID,
            "clientSecret": TOKEN_CLIENT_SECRET,
            "params": {},
            "offset": 0,
            "limit": 10,
            "userId": ""
        }

        resp = requests.post(TOKEN_API_URL, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        blocks = data.get("__blocks__", {})
        if not blocks or "result" not in blocks:
            msg = data.get("__sys__", {}).get("msg", "未知错误")
            raise Exception(f"Token 获取失败: {msg}")

        token = data["__blocks__"]["result"]["rows"][0][0]
        return token

    @staticmethod
    def upload_file(token, file_path):
        """上传文件到企微临时素材库"""
        url = f"{WECOM_BASE_URL}/cgi-bin/media/upload"
        params = {"access_token": token, "type": "file"}

        mime_types = {
            ".html": "text/html",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls": "application/vnd.ms-excel",
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".png": "image/png",
            ".jpg": "image/jpeg",
        }
        mime_type = mime_types.get(os.path.splitext(file_path)[1].lower(), "application/octet-stream")

        with open(file_path, 'rb') as f:
            files = {'media': (os.path.basename(file_path), f, mime_type)}
            resp = requests.post(url, params=params, files=files, timeout=60)

        resp.raise_for_status()
        data = resp.json()

        if data.get('errcode', 0) != 0:
            raise Exception(f"文件上传失败: {data.get('errmsg')}")

        return data['media_id']

    @staticmethod
    def send_file(token, media_id, chatid):
        """发送文件消息到群聊"""
        url = f"{WECOM_BASE_URL}/cgi-bin/appchat/send"
        params = {"access_token": token}

        payload = {
            "chatid": chatid,
            "msgtype": "file",
            "file": {"media_id": media_id}
        }

        resp = requests.post(url, params=params, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if data.get('errcode', 0) != 0:
            raise Exception(f"文件发送失败: {data.get('errmsg')}")

        return True

    @staticmethod
    def send(file_path, chatid=None):
        """发送文件到企微群聊"""
        if chatid is None:
            chatid = DEFAULT_CHATID

        print(f"📎 文件: {os.path.basename(file_path)}")
        print(f"💬 目标群聊: {chatid}")
        print(f"🌐 企微API: {WECOM_BASE_URL}")

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
