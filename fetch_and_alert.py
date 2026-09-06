"""
Pionex 合約(PERP)價格監控 + Telegram 通知
=========================================

功能:
1. 呼叫 Pionex 公開 API,取得「目前 Pionex 支援的所有合約(PERP)幣種」清單
2. 取得這些幣種目前的價格(24hr ticker)
3. 依照 config.json 裡設定的條件做判斷:
   - pct_change_alert: 與「上次執行時」的價格相比,漲跌幅超過此百分比就發警示
   - price_thresholds: 針對指定幣種設定「高於/低於某價格」就發警示
4. 若有任何幣種符合條件,透過 Telegram Bot 發送訊息給你

執行環境需要兩個環境變數(在 GitHub Actions 裡用 Secrets 設定):
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

改用 Telegram 而非 LINE 的原因:Telegram Bot 訊息完全免費、無每月則數上限,
比 LINE Messaging API(免費方案每月僅 200 則)更適合這種可能高頻率觸發的
價格警示用途。

本機測試時,你可以用:
    export TELEGRAM_BOT_TOKEN="123456:xxxx"
    export TELEGRAM_CHAT_ID="123456789"
    python fetch_and_alert.py
"""

import json
import os
from datetime import datetime, timezone

import requests

PIONEX_BASE = "https://api.pionex.com"
STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

DEFAULT_CONFIG = {
    # 與上次執行時的價格相比,漲跌幅超過這個百分比就發警示
    "pct_change_alert": 5.0,
    # 針對特定幣種設定價格門檻,例如:
    # "price_thresholds": {
    #     "BTC_USDT_PERP": {"above": 70000, "below": 60000},
    #     "ETH_USDT_PERP": {"above": 4000}
    # }
    "price_thresholds": {},
}


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def get_perp_symbols():
    """取得目前 Pionex 支援的所有合約(PERP)幣種代號集合"""
    resp = requests.get(
        f"{PIONEX_BASE}/api/v1/common/symbols",
        params={"type": "PERP"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("result"):
        raise RuntimeError(f"Pionex symbols API error: {data}")
    return {
        s["symbol"]
        for s in data["data"]["symbols"]
        if s.get("enable", True)
    }


def get_perp_tickers():
    """取得所有合約(PERP)幣種的最新價格資料"""
    resp = requests.get(
        f"{PIONEX_BASE}/api/v1/market/tickers",
        params={"type": "PERP"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("result"):
        raise RuntimeError(f"Pionex tickers API error: {data}")
    return {t["symbol"]: t for t in data["data"]["tickers"]}


def send_telegram_message(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[警告] 未設定 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID,跳過推播,僅印出訊息:")
        print(text)
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = {
        "chat_id": chat_id,
        "text": text[:4000],
    }
    r = requests.post(url, json=body, timeout=15)
    if r.status_code != 200:
        print(f"[錯誤] Telegram 推播失敗: {r.status_code} {r.text}")
    else:
        print("[完成] Telegram 推播成功")


def main():
    config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
    state = load_json(STATE_FILE, {"last_prices": {}})

    perp_symbols = get_perp_symbols()
    tickers = get_perp_tickers()

    alerts = []
    new_last_prices = {}

    for symbol in perp_symbols:
        ticker = tickers.get(symbol)
        if not ticker:
            continue
        try:
            close = float(ticker["close"])
        except (TypeError, ValueError):
            continue

        new_last_prices[symbol] = close

        # 條件一:與上次執行時的價格相比,漲跌幅是否超過門檻
        prev = state.get("last_prices", {}).get(symbol)
        if prev:
            pct = (close - prev) / prev * 100
            if abs(pct) >= config.get("pct_change_alert", 5.0):
                direction = "上漲" if pct > 0 else "下跌"
                alerts.append(
                    f"{symbol}: {direction} {abs(pct):.2f}%(現價 {close})"
                )

        # 條件二:自訂價格門檻(高於 / 低於)
        th = config.get("price_thresholds", {}).get(symbol)
        if th:
            if "above" in th and close >= th["above"]:
                alerts.append(f"{symbol}: 價格 {close} 已高於門檻 {th['above']}")
            if "below" in th and close <= th["below"]:
                alerts.append(f"{symbol}: 價格 {close} 已低於門檻 {th['below']}")

    state["last_prices"] = new_last_prices
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_json(STATE_FILE, state)

    print(f"本次檢查了 {len(perp_symbols)} 個 Pionex 合約幣種。")

    if alerts:
        header = (
            f"⚠️ Pionex 合約價格警示 "
            f"({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})\n"
        )
        message = header + "\n".join(alerts)
        print(message)
        send_telegram_message(message)
    else:
        print("沒有符合條件的幣種,本次不發送通知。")


if __name__ == "__main__":
    main()
