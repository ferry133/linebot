#!/usr/bin/env python3
"""一次性腳本：建立含「📖 使用說明」的 LINE Rich Menu 並設為預設。

點擊整塊 → postback `o=guide` → gateway 轉 customer-service `_handle_guide`
→ 依角色回覆專屬手冊連結。

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

RICHMENU = {
    "size": {"width": WIDTH, "height": HEIGHT},
    "selected": True,
    "name": "guide-menu",
    "chatBarText": "📖 使用說明",
    "areas": [
        {
            "bounds": {"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT},
            "action": {"type": "postback", "data": "o=guide", "displayText": "使用說明"},
        }
    ],
}

_FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
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
    return ImageFont.load_default()


def _generate_image() -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (WIDTH, HEIGHT), "#06c755")
    d = ImageDraw.Draw(img)
    label = "📖  使用說明"
    sub = "點此查看你的操作說明"
    f1, f2 = _load_font(220), _load_font(96)
    for text, font, y in ((label, f1, HEIGHT * 0.30), (sub, f2, HEIGHT * 0.66)):
        try:
            l, t, r, b = d.textbbox((0, 0), text, font=font)
            w = r - l
        except Exception:
            w = font.getlength(text) if hasattr(font, "getlength") else len(text) * 10
        d.text(((WIDTH - w) / 2, y), text, fill="#ffffff", font=font)
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
