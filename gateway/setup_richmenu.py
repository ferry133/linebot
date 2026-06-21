#!/usr/bin/env python3
"""一次性腳本：建立含「📋 今日提醒」與「📖 使用說明」兩塊的 LINE Rich Menu 並設為預設。

左半 → postback `o=daily` → customer-service `_handle_daily`（on-demand 拉取每日內容，走 Reply API＝免費）。
右半 → postback `o=guide` → customer-service `_handle_guide`（依角色回覆專屬手冊連結）。

用法（需 LINE_CHANNEL_ACCESS_TOKEN 環境變數）：
    python gateway/setup_richmenu.py                 # 自動產生底圖
    python gateway/setup_richmenu.py --image menu.png # 用自備底圖（2500x843 PNG）
    python gateway/setup_richmenu.py --replace        # 先刪除既有 rich menu 再建立

注意：在有中文字型的環境（如 macOS）執行，自動底圖的中文才不會變成方框；
slim 容器內無 CJK 字型時建議改用 --image 提供設計好的圖。
"""

import argparse
import io
import os
import sys

import requests

TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
API = "https://api.line.me/v2/bot"
API_DATA = "https://api-data.line.me/v2/bot"
WIDTH, HEIGHT = 2500, 843

HALF = WIDTH // 2

RICHMENU = {
    "size": {"width": WIDTH, "height": HEIGHT},
    "selected": True,
    "name": "main-menu",
    "chatBarText": "📋今日 📖說明",  # LINE 上限 14 字元
    "areas": [
        {
            # 左半：今日提醒（on-demand 拉取，走 Reply API＝免費）
            "bounds": {"x": 0, "y": 0, "width": HALF, "height": HEIGHT},
            "action": {"type": "postback", "data": "o=daily", "displayText": "今日提醒"},
        },
        {
            # 右半：使用說明
            "bounds": {"x": HALF, "y": 0, "width": WIDTH - HALF, "height": HEIGHT},
            "action": {"type": "postback", "data": "o=guide", "displayText": "使用說明"},
        },
    ],
}

_FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Debian fonts-noto-cjk
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _auth():
    if not TOKEN:
        sys.exit("ERROR: LINE_CHANNEL_ACCESS_TOKEN not set")
    return {"Authorization": f"Bearer {TOKEN}"}


def _load_font(size):
    from PIL import ImageFont
    for p in _FONT_CANDIDATES:
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return None  # 無可縮放/CJK 字型（如 slim 容器）


def _generate_image() -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (WIDTH, HEIGHT), "#06c755")
    d = ImageDraw.Draw(img)
    # 中央分隔線（兩個按鈕區）
    d.line([(HALF, 90), (HALF, HEIGHT - 90)], fill="#ffffff", width=8)
    f1 = _load_font(150)
    if f1 is not None:
        # 有 CJK 字型（如在 macOS 執行）→ 直接畫中文，左右兩欄
        f2 = _load_font(70)
        cols = (
            (HALF // 2,            "📋  今日提醒", "查看今日工程提醒"),
            (HALF + (WIDTH - HALF) // 2, "📖  使用說明", "查看你的操作說明"),
        )
        for cx, title, subtitle in cols:
            for text, font, y in ((title, f1, int(HEIGHT * 0.28)), (subtitle, f2, int(HEIGHT * 0.62))):
                box = d.textbbox((0, 0), text, font=font)
                d.text((cx - (box[2] - box[0]) / 2, y), text, fill="#ffffff", font=font)
    else:
        # 無字型（slim 容器）→ 幾何設計，避免中文變方框；文字標籤由 chatBarText 顯示
        for x0 in (HALF // 2, HALF + (WIDTH - HALF) // 2):
            d.rounded_rectangle([x0 - 130, HEIGHT * 0.40, x0 + 130, HEIGHT * 0.60], radius=44, fill="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _delete_existing():
    r = requests.get(f"{API}/richmenu/list", headers=_auth())
    for rm in r.json().get("richmenus", []):
        rid = rm["richMenuId"]
        requests.delete(f"{API}/richmenu/{rid}", headers=_auth())
        print(f"deleted existing rich menu {rid}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", help="2500x843 PNG/JPEG 底圖（不給則自動產生）")
    ap.add_argument("--replace", action="store_true", help="先刪除既有 rich menu")
    args = ap.parse_args()

    if args.replace:
        _delete_existing()

    img_bytes = open(args.image, "rb").read() if args.image else _generate_image()
    ctype = "image/png"
    if args.image and args.image.lower().endswith((".jpg", ".jpeg")):
        ctype = "image/jpeg"

    # 1) 建立 rich menu
    r = requests.post(f"{API}/richmenu", headers={**_auth(), "Content-Type": "application/json"}, json=RICHMENU)
    r.raise_for_status()
    rid = r.json()["richMenuId"]
    print(f"created rich menu {rid}")

    # 2) 上傳底圖
    r = requests.post(f"{API_DATA}/richmenu/{rid}/content", headers={**_auth(), "Content-Type": ctype}, data=img_bytes)
    r.raise_for_status()
    print("uploaded image")

    # 3) 設為所有使用者的預設 rich menu
    r = requests.post(f"{API}/user/all/richmenu/{rid}", headers=_auth())
    r.raise_for_status()
    print(f"set as default rich menu ✓  ({rid})")


if __name__ == "__main__":
    main()
