# -*- coding: utf-8 -*-
"""生成专家团头像缩略图（96x96 PNG），供 dwb-team-panel 名册渲染。

原始 512x512 原图只在交付包 avatars/ 存档；本脚本按 panel/roster.json 的 preset id
映射，缺头像的 preset 回退 team.png。缩略图同时写到：
  - 团队根 panel/dwb-team-panel/assets/avatars/（开发/已装副本来源）
  - 交付包 panel/dwb-team-panel/assets/avatars/（打包副本）
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.environ.get(
    "DWB_PKG",
    r"C:\Users\lin\Doubao\chats\2026-11-17\new-chat-1\dsh-data-warehouse-brain",
)
SRC_DIR = os.path.join(PKG, "avatars")
ROSTER = os.path.join(ROOT, "panel", "roster.json")
THUMB_SIZE = 96

OUT_DIRS = [
    os.path.join(ROOT, "panel", "dwb-team-panel", "assets", "avatars"),
    os.path.join(PKG, "panel", "dwb-team-panel", "assets", "avatars"),
]


def main():
    try:
        from PIL import Image
    except ImportError:
        print("❌ 需要 Pillow（内置 python 已带）", file=sys.stderr)
        return 1

    with open(ROSTER, encoding="utf-8") as f:
        roster = json.load(f)
    ids = [a["id"] for a in roster.get("agents", [])]

    missing = []
    written = 0
    total_bytes = 0
    for out_dir in OUT_DIRS:
        os.makedirs(out_dir, exist_ok=True)

    for pid in ids:
        src = os.path.join(SRC_DIR, pid + ".png")
        if not os.path.exists(src):
            src = os.path.join(SRC_DIR, "team.png")
            missing.append(pid)
        if not os.path.exists(src):
            print(f"❌ 无头像且无 team 兜底：{pid}", file=sys.stderr)
            continue
        img = Image.open(src).convert("RGBA")
        img.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.LANCZOS)
        canvas = Image.new("RGBA", (THUMB_SIZE, THUMB_SIZE), (255, 255, 255, 0))
        ox = (THUMB_SIZE - img.width) // 2
        oy = (THUMB_SIZE - img.height) // 2
        canvas.paste(img, (ox, oy), img)
        for out_dir in OUT_DIRS:
            dst = os.path.join(out_dir, pid + ".png")
            canvas.save(dst, format="PNG", optimize=True)
        written += 1
        total_bytes += os.path.getsize(os.path.join(OUT_DIRS[0], pid + ".png"))

    print(f"✅ 生成 {written} 个缩略图，合计 {total_bytes/1024:.1f} KB")
    if missing:
        print("⚠️  回退 team.png：" + ", ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
