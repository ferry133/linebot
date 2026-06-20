#!/usr/bin/env python3
"""LINE 對話內「線上說明」：把 docs/<role>-guide.md 轉成可在聊天室瀏覽的訊息。

- 主題選單（無 pb）：依角色列出各 `##` 主題按鈕 + 「完整手冊」。
- 單一主題（pb s=<i>）：顯示該段，附 (i+1/N) 位置與 上一/下一/目錄/全部 導覽。
- 完整手冊（pb s=all[&c=<i>]）：整份文字，標出「▶ 你在這」。

純文字/Flex 訊息 dict，交由 gateway outbox 以 Reply API 送出（不吃推播額度）。
"""

import os
import re

DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")
GUIDE_KEYWORDS = ("使用說明", "使用手冊", "操作說明", "怎麼用", "help", "Help")
ROLE_LABEL = {
    "admin": "管理員", "employee": "員工", "vendor": "廠商",
    "customer": "客戶", "visitor": "新手",
}
_GREEN = "#06c755"
_MSG_LIMIT = 4800  # 單則文字上限（LINE 為 5000，留餘裕）


# ── markdown → LINE 可讀文字 ─────────────────────────────────────────────────

def _strip_inline(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)            # **粗體**
    s = re.sub(r"`([^`]+)`", r"\1", s)                # `code`
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1（\2）", s)  # [text](url)
    return s


def _md_to_text(md: str) -> str:
    out = []
    for raw in md.splitlines():
        s = raw.strip()
        if not s:
            out.append("")
            continue
        if re.fullmatch(r"-{3,}", s):                 # 分隔線
            out.append("──────────")
            continue
        if "|" in s and re.fullmatch(r"[\s:\-\|]+", s):  # 表格分隔列 |---|---|
            continue
        if s.startswith("|") and s.endswith("|"):     # 表格資料列
            cells = [c.strip() for c in s.strip("|").split("|") if c.strip()]
            out.append("・" + " ｜ ".join(_strip_inline(c) for c in cells))
            continue
        m = re.match(r"#{3,6}\s+(.*)", s)             # 子標題
        if m:
            out.append("◆ " + _strip_inline(m.group(1)))
            continue
        if s.startswith(">"):                          # 引言
            out.append("💬 " + _strip_inline(s.lstrip("> ").strip()))
            continue
        out.append(_strip_inline(raw.rstrip()))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _load_sections(role: str):
    """回傳 [(title, body_text)]；以 `## ` 切段，跳過 H1 與前言。"""
    path = os.path.join(DOCS_DIR, f"{role}-guide.md")
    if not os.path.isfile(path):
        return []
    md = open(path, encoding="utf-8").read()
    sections = []
    for chunk in re.split(r"(?m)^##\s+", md)[1:]:
        head, _, rest = chunk.partition("\n")
        sections.append((_strip_inline(head.strip()), _md_to_text(rest)))
    return sections


def _guide_title(role: str) -> str:
    path = os.path.join(DOCS_DIR, f"{role}-guide.md")
    if not os.path.isfile(path):
        return "使用說明"
    first = open(path, encoding="utf-8").read().lstrip("# ").split("\n", 1)[0]
    return _strip_inline(first.strip())[:60]


def _chunk(text: str, limit: int = _MSG_LIMIT):
    blocks, buf, out = text.split("\n\n"), "", []
    for b in blocks:
        if len(buf) + len(b) + 2 > limit and buf:
            out.append(buf.strip())
            buf = ""
        buf += b + "\n\n"
    if buf.strip():
        out.append(buf.strip())
    return out or [""]


# ── Flex 元件 ────────────────────────────────────────────────────────────────

def _btn(label: str, data: str, primary=False):
    b = {"type": "button", "height": "sm",
         "action": {"type": "postback", "label": label[:40], "data": data, "displayText": label[:40]}}
    if primary:
        b["style"], b["color"] = "primary", _GREEN
    else:
        b["style"] = "secondary"
    return b


def _header(sub: str, title: str):
    return {"type": "box", "layout": "vertical", "contents": [
        {"type": "text", "text": sub, "size": "xs", "color": "#06794d"},
        {"type": "text", "text": title, "weight": "bold", "size": "md", "wrap": True, "margin": "sm"}]}


def _menu(role: str, sections):
    label = ROLE_LABEL.get(role, "")
    buttons = [_btn(t, f"o=guide&s={i}") for i, (t, _) in enumerate(sections)]
    buttons.append(_btn("📄 完整手冊", "o=guide&s=all", primary=True))
    return {"type": "flex", "altText": f"{label}線上說明",
            "contents": {"type": "bubble", "size": "mega",
                         "header": _header(f"意念情境・{label}線上說明", "請選擇主題 👇"),
                         "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": buttons}}}


def _section(role: str, sections, i: int):
    n = len(sections)
    title, body = sections[i]
    nav = []
    if i > 0:
        nav.append(_btn("⬅️ 上一", f"o=guide&s={i-1}"))
    if i < n - 1:
        nav.append(_btn("下一 ➡️", f"o=guide&s={i+1}"))
    foot = [{"type": "box", "layout": "horizontal", "spacing": "sm",
             "contents": nav or [{"type": "filler"}]},
            {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                _btn("☰ 目錄", "o=guide"), _btn("📄 全部", f"o=guide&s=all&c={i}")]}]
    return {"type": "flex", "altText": title,
            "contents": {"type": "bubble", "size": "mega",
                         "header": _header(f"({i+1}/{n}) {ROLE_LABEL.get(role,'')}說明", title),
                         "body": {"type": "box", "layout": "vertical", "contents": [
                             {"type": "text", "text": body or "（本節無內容）",
                              "wrap": True, "size": "sm", "color": "#333333"}]},
                         "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": foot}}}


def _full(role: str, sections, current):
    label = ROLE_LABEL.get(role, "")
    parts = []
    for i, (t, b) in enumerate(sections):
        mark = "　▶（你在這）" if current is not None and i == current else ""
        parts.append(f"【{t}】{mark}\n{b}".rstrip())
    full = f"📄 意念情境・{label}完整使用說明\n\n" + "\n\n".join(parts)
    msgs = [{"type": "text", "text": c} for c in _chunk(full)[:4]]
    msgs.append({"type": "flex", "altText": "回目錄",
                 "contents": {"type": "bubble", "size": "kilo",
                              "body": {"type": "box", "layout": "vertical", "contents": [
                                  _btn("☰ 回主題目錄", "o=guide")]}}})
    return msgs


# ── 對外入口 ─────────────────────────────────────────────────────────────────

def guide_messages(role: str, pb: dict | None = None) -> list:
    """依 postback（s / c）回傳要送出的 LINE 訊息陣列；無內容回 []。"""
    sections = _load_sections(role)
    if not sections:
        return []
    s = (pb or {}).get("s")
    if s is None:
        return [_menu(role, sections)]
    if s == "all":
        c = (pb or {}).get("c")
        return _full(role, sections, int(c) if (c or "").isdigit() else None)
    try:
        i = max(0, min(int(s), len(sections) - 1))
    except (TypeError, ValueError):
        i = 0
    return [_section(role, sections, i)]
