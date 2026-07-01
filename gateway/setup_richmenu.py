#!/usr/bin/env python3
"""一次性腳本：建立三格 LINE Rich Menu（今日提醒 / 查其他日期 / 使用說明）並設為預設。

三格皆為底圖上的隱形點擊區：
  左   → postback `o=daily`      → _handle_daily（今日內容，Reply＝免費）
  中   → datetimepicker `o=someday` → 選過去/未來日 → _handle_daily(as_of)（someday 投影、唯讀）
  右   → postback `o=guide`      → _handle_guide（依角色手冊）

datetimepicker 不設 initial/min/max：Rich Menu 建立一次、值會凍結，故省略 → 每次點按
以「當下今日」為預設，可任意選日（gateway 從 postback.params.date 取值）。

用法（部署需 LINE_CHANNEL_ACCESS_TOKEN）：
    python gateway/setup_richmenu.py --preview out.png   # 只產底圖預覽，不需 token、不部署
    python gateway/setup_richmenu.py                     # 自動產底圖 + 部署
    python gateway/setup_richmenu.py --image menu.png    # 用自備底圖（2500x843 PNG）
    python gateway/setup_richmenu.py --replace           # 先刪既有 rich menu 再建立

自備底圖：三等分寬對應左/中/右三格；建議 2500x843 PNG。想要更精緻的圖示風格，
直接提供設計好的 PNG 即可（點擊區座標已固定為三等分）。
"""

import argparse
import io
import os
import sys

try:
    import requests  # 部署時需要；--preview 只出圖不需網路
except ImportError:
    requests = None

TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
API = "https://api.line.me/v2/bot"
API_DATA = "https://api-data.line.me/v2/bot"
WIDTH, HEIGHT = 2500, 843

THIRD = WIDTH // 3

# 三格：(底色, 標籤, 圖示種類, action)
TILES = [
    ("#06C755", "今日提醒", "agenda",
     {"type": "postback", "data": "o=daily", "displayText": "今日提醒"}),
    ("#2D7FF9", "查其他日期", "calendar",
     {"type": "datetimepicker", "data": "o=someday", "mode": "date"}),
    ("#FF7A00", "使用說明", "help",
     {"type": "postback", "data": "o=guide", "displayText": "使用說明"}),
]

RICHMENU = {
    "size": {"width": WIDTH, "height": HEIGHT},
    "selected": True,
    "name": "main-menu-v2",
    "chatBarText": "📋今日 📅日期 說明",  # LINE 上限 14 字元（保守收短）
    "areas": [
        {"bounds": {"x": 0,         "y": 0, "width": THIRD,             "height": HEIGHT}, "action": TILES[0][3]},
        {"bounds": {"x": THIRD,     "y": 0, "width": THIRD,             "height": HEIGHT}, "action": TILES[1][3]},
        {"bounds": {"x": 2 * THIRD, "y": 0, "width": WIDTH - 2 * THIRD, "height": HEIGHT}, "action": TILES[2][3]},
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


# ─── 圖示（白色線條，畫在彩色格子上；避免 emoji 在 PIL 變方框）────────────

def _draw_agenda(d, cx, cy, s):
    """今日提醒：清單外框 + 三條線。"""
    w, h = s * 1.15, s * 1.35
    x0, y0 = cx - w / 2, cy - h / 2
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=18, outline="#ffffff", width=11)
    for k in range(3):
        yy = y0 + h * (0.32 + 0.20 * k)
        d.line([(x0 + w * 0.20, yy), (x0 + w * 0.80, yy)], fill="#ffffff", width=13)


def _draw_calendar(d, cx, cy, s):
    """查其他日期：日曆外框 + 標題列 + 掛環 + 日期點。"""
    w, h = s * 1.3, s * 1.25
    x0, y0 = cx - w / 2, cy - h / 2
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=18, outline="#ffffff", width=11)
    d.line([(x0, y0 + h * 0.30), (x0 + w, y0 + h * 0.30)], fill="#ffffff", width=11)  # 標題列
    for fx in (0.28, 0.72):  # 掛環
        d.line([(x0 + w * fx, y0 - 16), (x0 + w * fx, y0 + 20)], fill="#ffffff", width=13)
    for r in range(2):       # 日期點
        for c in range(3):
            dx = x0 + w * (0.28 + 0.22 * c)
            dy = y0 + h * (0.52 + 0.26 * r)
            d.ellipse([dx - 9, dy - 9, dx + 9, dy + 9], fill="#ffffff")


def _draw_help(d, cx, cy, s, font):
    """使用說明：圓形泡泡 + 問號。"""
    r = s * 0.78
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline="#ffffff", width=12)
    if font:
        box = d.textbbox((0, 0), "?", font=font)
        d.text((cx - (box[2] - box[0]) / 2 - box[0], cy - (box[3] - box[1]) / 2 - box[1]),
               "?", fill="#ffffff", font=font)


_ICONS = {"agenda": _draw_agenda, "calendar": _draw_calendar}


def _generate_image() -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (WIDTH, HEIGHT), "#EEF1F4")
    d = ImageDraw.Draw(img)
    margin, gap = 48, 36
    n = len(TILES)
    tile_w = (WIDTH - 2 * margin - (n - 1) * gap) / n
    label_font = _load_font(104)
    q_font = _load_font(210)
    for i, (color, label, icon, _action) in enumerate(TILES):
        x0 = margin + i * (tile_w + gap)
        x1 = x0 + tile_w
        y0, y1 = margin, HEIGHT - margin
        d.rounded_rectangle([x0, y0, x1, y1], radius=52, fill=color)
        cx = (x0 + x1) / 2
        icy = y0 + (y1 - y0) * 0.34
        if icon == "help":
            _draw_help(d, cx, icy, 150, q_font)
        else:
            _ICONS[icon](d, cx, icy, 150)
        if label_font is not None:
            box = d.textbbox((0, 0), label, font=label_font)
            d.text((cx - (box[2] - box[0]) / 2, y0 + (y1 - y0) * 0.60),
                   label, fill="#ffffff", font=label_font)
        else:
            # 無 CJK 字型 → 畫白條佔位，文字靠 chatBarText / 自備底圖
            d.rounded_rectangle([cx - 150, y1 - 130, cx + 150, y1 - 70], radius=30, fill="#ffffff")
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
    ap.add_argument("--preview", metavar="PATH", help="只把自動底圖寫到 PATH 預覽，不需 token、不部署")
    ap.add_argument("--replace", action="store_true", help="先刪除既有 rich menu")
    args = ap.parse_args()

    if args.preview:
        with open(args.preview, "wb") as f:
            f.write(_generate_image())
        print(f"preview written → {args.preview}")
        return

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
