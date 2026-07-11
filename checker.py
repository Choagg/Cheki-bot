#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot check zaiko (在庫 / tồn kho) cho phim Fujifilm instax (チェキ)
trên các trang bán hàng online tại Nhật.

CHỈ dùng để THEO DÕI & THÔNG BÁO khi có hàng — KHÔNG tự động mua/checkout.
Nhiều shop cấm dùng bot cho mục đích 転売 (mua đi bán lại), hãy dùng có trách nhiệm.

Cài đặt:
    pip install requests beautifulsoup4 --break-system-packages

Chạy:
    python3 checker.py                # chạy 1 lần
    python3 checker.py --loop         # chạy lặp lại theo check_interval_seconds trong config.json
"""

import json
import re
import sys
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH = BASE_DIR / "state.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# Các cụm từ tiếng Nhật báo hết hàng (ưu tiên kiểm tra trước, vì cụ thể hơn)
OUT_OF_STOCK_PATTERNS = [
    "在庫切れ", "在庫なし", "在庫 ×", "在庫：×", "売り切れ", "売切れ",
    "SOLD OUT", "sold out", "販売終了", "取扱終了",
    "現在お取り扱いできません", "只今、在庫がありません",
    "入荷未定", "只今品切れ中", "この商品は現在お取り扱いできません",
    "残り0", "在庫が不足",
]

# Các cụm từ báo còn hàng
IN_STOCK_PATTERNS = [
    "在庫あり", "在庫 〇", "在庫：〇", "カートに入れる", "今すぐ購入",
    "ショッピングカートに入れる", "購入する", "残りわずか",
    "お届け日", "通常配送", "翌日お届け",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("cheki-bot")


def load_json(path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_page(url: str) -> str | None:
    try:
        headers = dict(HEADERS)
        headers["Referer"] = "https://www.google.com/"
        session = requests.Session()
        resp = session.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        # Một số trang Nhật (vd Fujifilm Mall) dùng bảng mã Shift-JIS/EUC-JP thay vì UTF-8.
        # Nếu không set đúng, chữ tiếng Nhật sẽ bị đọc sai (mojibake) -> không nhận diện được từ khóa.
        if not resp.encoding or resp.encoding.lower() in ("iso-8859-1", "ascii"):
            resp.encoding = resp.apparent_encoding
        return resp.text
    except requests.RequestException as e:
        log.warning(f"Lỗi khi tải {url}: {e}")
        return None


def detect_stock_status(html: str, site: str) -> str:
    """
    Trả về 'in_stock', 'out_of_stock' hoặc 'unknown'.
    Dùng kết hợp: parser riêng cho từng site (nếu cấu trúc ổn định)
    + fallback bằng keyword matching trên toàn bộ text trang.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # --- Parser riêng theo site (ưu tiên, chính xác hơn) ---
    if site == "amazon":
        # Amazon: nút "カートに入れる" / "今すぐ買う" hoặc dòng "現在在庫切れです"
        if re.search(r"現在在庫切れ|一時的に在庫切れ", text):
            return "out_of_stock"
        buy_box = soup.find(id="add-to-cart-button") or soup.find(id="buy-now-button")
        if buy_box:
            return "in_stock"

    elif site == "rakuten":
        if re.search(r"売り切れ|販売を終了", text):
            return "out_of_stock"
        if re.search(r"カートに入れる|購入手続きへ", text):
            return "in_stock"

    elif site == "yodobashi":
        if re.search(r"入荷次第発送|お取り寄せ|販売を終了", text):
            return "out_of_stock"
        if re.search(r"カートに入れる", text):
            return "in_stock"

    elif site == "yahoo":
        if re.search(r"売り切れ|販売終了", text):
            return "out_of_stock"
        if re.search(r"カートに入れる|購入手続きへ", text):
            return "in_stock"

    elif site == "fujifilm_mall":
        # Fujifilm Mall hiển thị trạng thái tồn kho trong thuộc tính "value" của nút bấm,
        # vd: <input class="btn_cart_l_ inactive_" type="button" value="在庫なし">
        m = re.search(r'class="btn_cart_l_[^"]*"\s+type="button"\s+value="([^"]+)"', html)
        if m:
            btn_value = m.group(1)
            if "在庫なし" in btn_value or "売り切れ" in btn_value or "SOLD" in btn_value.upper():
                return "out_of_stock"
            if "カート" in btn_value or "購入" in btn_value or "在庫あり" in btn_value:
                return "in_stock"
        if re.search(r"SOLD OUT|売り切れ", text, re.IGNORECASE):
            return "out_of_stock"
        if re.search(r"カートに入れる", text):
            return "in_stock"

    elif site == "bigcamera":
        # ビックカメラ.com: "在庫なし" / "お取り寄せ" hoặc "カートに入れる"
        if re.search(r"在庫なし|お取り寄せ|販売を終了しました", text):
            return "out_of_stock"
        if re.search(r"カートに入れる|注文する", text):
            return "in_stock"

    elif site == "sofmap":
        if re.search(r"在庫なし|販売終了", text):
            return "out_of_stock"
        if re.search(r"カートに入れる", text):
            return "in_stock"

    elif site == "joshin":
        if re.search(r"在庫切れ|販売終了", text):
            return "out_of_stock"
        if re.search(r"カートに入れる|買い物カゴに入れる", text):
            return "in_stock"

    # --- Fallback: keyword matching chung (tìm cả trong text hiển thị lẫn HTML gốc,
    # vì một số trang đặt trạng thái trong thuộc tính value=/alt= không hiện trong text) ---
    combined = text + " " + html
    for kw in OUT_OF_STOCK_PATTERNS:
        if kw in combined:
            return "out_of_stock"
    for kw in IN_STOCK_PATTERNS:
        if kw in combined:
            return "in_stock"

    return "unknown"


def send_telegram(bot_token: str, chat_id: str, product_name: str, url: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"🟢 CÒN HÀNG!\n{product_name}\n{url}\n({now})"
    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(api_url, json=payload, timeout=10)
        r.raise_for_status()
        log.info(f"Đã gửi Telegram: {product_name}")
    except requests.RequestException as e:
        log.error(f"Gửi Telegram thất bại: {e}")


def send_webhook(webhook_url: str, webhook_type: str, product_name: str, url: str, status: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"🟢 **CÒN HÀNG!** {product_name}\n{url}\n({now})"

    if webhook_type == "discord":
        payload = {"content": message}
    elif webhook_type == "slack":
        payload = {"text": message}
    else:
        log.warning(f"webhook_type không hợp lệ: {webhook_type}")
        return

    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        r.raise_for_status()
        log.info(f"Đã gửi thông báo: {product_name}")
    except requests.RequestException as e:
        log.error(f"Gửi webhook thất bại: {e}")


def notify(config: dict, product_name: str, url: str, status: str):
    import os
    notify_type = config.get("notify_type", "telegram")

    if notify_type == "telegram":
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN") or config.get("telegram_bot_token", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID") or config.get("telegram_chat_id", "")
        if bot_token and "XXXX" not in bot_token and chat_id and "XXXX" not in str(chat_id):
            send_telegram(bot_token, chat_id, product_name, url)
        else:
            log.info(f"[THÔNG BÁO - chưa cấu hình Telegram] {product_name} CÓ HÀNG: {url}")
    elif notify_type in ("discord", "slack"):
        webhook_url = os.environ.get("WEBHOOK_URL") or config.get("webhook_url", "")
        if webhook_url and "XXXX" not in webhook_url:
            send_webhook(webhook_url, notify_type, product_name, url, status)
        else:
            log.info(f"[THÔNG BÁO - chưa cấu hình webhook] {product_name} CÓ HÀNG: {url}")
    else:
        log.warning(f"notify_type không hợp lệ: {notify_type}")


def check_once(config: dict, state: dict):
    for product in config.get("products", []):
        name = product["name"]
        url = product["url"]
        site = product["site"]

        if "XXXX" in url:
            log.info(f"Bỏ qua (chưa cấu hình URL thật): {name}")
            continue

        html = fetch_page(url)
        if html is None:
            continue

        status = detect_stock_status(html, site)
        prev_status = state.get(url, {}).get("status")

        log.info(f"[{name}] -> {status}")

        # DEBUG: nếu không nhận diện được trạng thái, in ra đoạn text quanh khu vực
        # giá tiền (thường gần nút mua/trạng thái tồn kho) để biết cấu trúc thực tế
        if status == "unknown":
            soup_debug = BeautifulSoup(html, "html.parser")
            text_debug = soup_debug.get_text(" ", strip=True)
            log.info(f"  [DEBUG length - {name}]: tổng {len(text_debug)} ký tự")
            idx = text_debug.find("円")  # tìm chỗ có giá tiền (vd 990円)
            if idx == -1:
                idx = len(text_debug) // 2  # fallback: lấy đoạn giữa trang
            start = max(0, idx - 150)
            snippet = text_debug[start:start + 900]
            log.info(f"  [DEBUG snippet - {name}]: {snippet}")

            # Quét thêm trong HTML gốc (không chỉ text hiển thị) để tìm nút dạng ảnh
            # (vd <input type="image" alt="カートに入れる">), vốn không xuất hiện trong get_text()
            for kw in ["カート", "在庫", "SOLD", "売切", "売り切", "購入", "cart", "Cart"]:
                pos = html.find(kw)
                if pos != -1:
                    ctx = html[max(0, pos - 100):pos + 100].replace("\n", " ")
                    log.info(f"  [DEBUG html quanh '{kw}']: ...{ctx}...")

        # Chỉ báo khi chuyển từ (hết hàng/không rõ) -> còn hàng
        if status == "in_stock" and prev_status != "in_stock":
            notify(config, name, url, status)

        state[url] = {"status": status, "checked_at": datetime.now().isoformat()}

        # Nghỉ giữa các request để tránh spam server / bị chặn
        time.sleep(3)

    save_json(STATE_PATH, state)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="Chạy lặp lại liên tục")
    args = parser.parse_args()

    config = load_json(CONFIG_PATH, None)
    if config is None:
        log.error(f"Không tìm thấy {CONFIG_PATH}")
        sys.exit(1)

    state = load_json(STATE_PATH, {})

    if args.loop:
        interval = config.get("check_interval_seconds", 300)
        log.info(f"Bắt đầu chạy lặp, mỗi {interval} giây. Nhấn Ctrl+C để dừng.")
        while True:
            check_once(config, state)
            time.sleep(interval)
    else:
        check_once(config, state)


if __name__ == "__main__":
    main()
