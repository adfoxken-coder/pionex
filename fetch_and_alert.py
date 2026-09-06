"""
Pionex 合約(PERP)技術條件監控 + Telegram 通知
=============================================

功能:
1. 取得 Pionex 目前支援的所有合約(PERP)幣種
2. 篩選出「24 小時成交金額(USDT) > 門檻」的幣種
3. 針對這些幣種抓取 5 分鐘 K 線,計算並判斷三個條件:
   條件一:該幣種 24 小時成交金額(USDT) > min_24h_amount_usdt
   條件二:最新收盤 K 線的成交量 > vol_multiplier 倍的 MAVOL5(近 5 根 K 線
           成交量的平均值,含本身),且該 K 線收陽(收盤價 > 開盤價)
   條件三:最新收盤 K 線漲跌幅絕對值 >= pct_change_multiplier 倍的「前一根
           K 線」漲跌幅絕對值;若前一根漲跌幅絕對值為 0,則改比較「前前一根」
4. 三個條件同時成立的幣種,整理成一則訊息透過 Telegram 發送通知

執行環境需要兩個環境變數(在 GitHub Actions 裡用 Secrets 設定):
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID
"""

import json
import os
import time
from datetime import datetime, timezone, timedelta

import requests

PIONEX_BASE = "https://api.pionex.com"
STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

TAIPEI_TZ = timezone(timedelta(hours=8))

DEFAULT_CONFIG = {
    "kline_interval": "15M",         # 使用的 K 線週期,需與排程頻率搭配
    "min_24h_amount_usdt": 20000,    # 條件一:24 小時成交金額(USDT)門檻
    "mavol_period": 5,               # 條件二:MAVOL 的期數
    "vol_multiplier": 1.5,           # 條件二:成交量需超過 MAVOL 的倍數
    "pct_change_multiplier": 2.0,    # 條件三:漲跌幅需超過前一根的倍數
    "min_body_ratio": 0.7,           # 條件四:實體(收盤-開盤)需佔整根K線(高-低)的比例
    "max_prev_wick_ratio": 0.5,      # 條件五:前一根K線影線不能超過最新這根K線(高-低)的比例
    "kline_fetch_limit": 15,         # 每次抓取的 K 線根數(需 >= mavol_period + 3)
    "request_sleep_sec": 0.15,       # 每次呼叫 klines API 之間的間隔,避免超過速率限制

    # 只偵測加密貨幣,排除美股代幣(xStocks)、貴金屬等非加密貨幣資產。
    # 這份清單是根據公開資訊整理,不保證完整;發現漏網或誤殺歡迎手動增減。
    "excluded_base_currencies": [
        # 美股代幣(xStocks,Backed Finance 發行)
        "AAPLX", "TSLAX", "NVDAX", "SPYX", "QQQX", "MSTRX", "CRCLX", "GOOGLX",
        "VTIX", "BRK.BX", "UNHX", "GMEX", "CMCSAX", "PGX", "NFLXX", "XOMX",
        "AMBRX", "LLYX", "ABBVX", "VX", "CSCOX", "MCDX", "NVOX", "KRAQX",
        "PFEX", "INTCX", "HOODX", "AMZNX", "METAX", "COINX", "MSFTX",
        "TQQQX", "DFDVX", "ASMLX",
        # 貴金屬
        "PPLTX", "XAU", "XAG", "XPT", "XPD", "PAXG", "XAUT",
    ],
    # 「基礎貨幣」本身就是穩定幣的合約(例如 USDT/TRY、USDT/BRL 這類外匯型合約),
    # 屬於「其他」類別而非一般加密貨幣方向性交易標的,一併排除
    "excluded_stablecoin_bases": [
        "USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD", "USDD", "PYUSD", "USDE",
    ],
    # 若幣種名稱(name 欄位)包含以下關鍵字,也會自動排除(不分大小寫)
    "exclude_name_keywords": [
        "stock", "xstock", "gold", "silver", "platinum", "palladium", "metal",
    ],
}

INTERVAL_MS = {
    "1M": 1 * 60 * 1000,
    "5M": 5 * 60 * 1000,
    "15M": 15 * 60 * 1000,
    "30M": 30 * 60 * 1000,
    "60M": 60 * 60 * 1000,
    "4H": 4 * 60 * 60 * 1000,
    "8H": 8 * 60 * 60 * 1000,
    "12H": 12 * 60 * 60 * 1000,
    "1D": 24 * 60 * 60 * 1000,
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
    """取得目前 Pionex 支援的所有合約(PERP)幣種,回傳 {symbol: {"base": ..., "name": ...}}"""
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
        s["symbol"]: {
            "base": s.get("baseCurrency", s["symbol"]),
            "name": s.get("name", ""),
        }
        for s in data["data"]["symbols"]
        if s.get("enable", True)
    }


def get_perp_tickers():
    """取得所有合約(PERP)幣種的 24 小時行情資料"""
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


def get_klines(session, symbol, interval, limit):
    resp = session.get(
        f"{PIONEX_BASE}/api/v1/market/klines",
        params={"symbol": symbol, "interval": interval, "limit": limit},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("result"):
        return []
    return data["data"]["klines"]


def format_price(x):
    s = f"{x:.6f}".rstrip("0").rstrip(".")
    return s if s else "0"


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


def evaluate_symbol(klines, config, interval_ms, now_ms):
    """回傳 (是否符合條件, 最新收盤價, 最新漲跌幅%) 或 (False, None, None)"""
    if not klines:
        return False, None, None

    sorted_klines = sorted(klines, key=lambda k: k["time"])
    # 只保留「已經收盤」的 K 線(排除還在形成中的最新一根)
    closed = [k for k in sorted_klines if k["time"] + interval_ms <= now_ms]

    mavol_period = config["mavol_period"]
    # 需要:最新這根 + 前面 mavol_period 根(不含本身)才能算 MAVOL,另外還要有前前根
    if len(closed) < max(mavol_period + 1, 3):
        return False, None, None  # 資料不足,跳過

    latest = closed[-1]
    prev = closed[-2]
    prev_prev = closed[-3]

    latest_open = float(latest["open"])
    latest_close = float(latest["close"])
    latest_high = float(latest["high"])
    latest_low = float(latest["low"])
    latest_vol = float(latest["volume"])

    if latest_open == 0:
        return False, None, None

    is_bullish = latest_close > latest_open
    latest_pct = (latest_close - latest_open) / latest_open * 100

    # 條件二:成交量 > vol_multiplier 倍的 MAVOL(取「這根之前」的 mavol_period 根,不含本身)
    recent_for_mavol = closed[-(mavol_period + 1):-1]
    mavol = sum(float(k["volume"]) for k in recent_for_mavol) / mavol_period
    vol_ok = mavol > 0 and latest_vol > config["vol_multiplier"] * mavol

    # 條件三:漲跌幅絕對值 >= pct_change_multiplier 倍的前一根(前一根為 0 則比前前一根)
    def candle_pct(k):
        o = float(k["open"])
        c = float(k["close"])
        if o == 0:
            return 0.0
        return (c - o) / o * 100

    prev_pct = candle_pct(prev)
    if abs(prev_pct) == 0:
        baseline = abs(candle_pct(prev_prev))
    else:
        baseline = abs(prev_pct)
    pct_ok = abs(latest_pct) >= config["pct_change_multiplier"] * baseline

    # 條件四:飽滿陽K,實體(收盤-開盤)佔整根K線(最高-最低)的比例 >= min_body_ratio
    candle_range = latest_high - latest_low
    if candle_range > 0:
        body_ratio = (latest_close - latest_open) / candle_range
    else:
        body_ratio = 0.0
    body_ok = body_ratio >= config["min_body_ratio"]

    # 條件五:前一根 K 線的「上影線」不能超過最新這根 K 線「實體」的一半
    prev_high = float(prev["high"])
    prev_open = float(prev["open"])
    prev_close = float(prev["close"])
    prev_upper_wick = prev_high - max(prev_open, prev_close)
    latest_body = latest_close - latest_open  # 已知 is_bullish 為真時此值為正
    if latest_body > 0:
        wick_ok = prev_upper_wick <= config["max_prev_wick_ratio"] * latest_body
    else:
        wick_ok = False

    matched = is_bullish and vol_ok and pct_ok and body_ok and wick_ok
    return matched, latest_close, latest_pct


def is_excluded_asset(symbol_info, config):
    """判斷是否為要排除的非加密貨幣資產(美股代幣、貴金屬、外匯型合約等)"""
    base = symbol_info.get("base", "").upper()
    name = (symbol_info.get("name") or "").lower()

    excluded_bases = {b.upper() for b in config.get("excluded_base_currencies", [])}
    if base in excluded_bases:
        return True

    stablecoin_bases = {b.upper() for b in config.get("excluded_stablecoin_bases", [])}
    if base in stablecoin_bases:
        return True  # 基礎貨幣本身是穩定幣,通常是外匯型合約,非一般加密貨幣

    keywords = config.get("exclude_name_keywords", [])
    if name and any(kw.lower() in name for kw in keywords):
        return True

    return False


def main():
    config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
    # 補齊任何缺少的設定值(例如使用者只改了部分欄位)
    for k, v in DEFAULT_CONFIG.items():
        config.setdefault(k, v)

    now_ms = int(time.time() * 1000)
    interval = config["kline_interval"]
    interval_ms = INTERVAL_MS.get(interval, 15 * 60 * 1000)

    symbols_map = get_perp_symbols()      # {symbol: {"base":..., "name":...}}
    tickers = get_perp_tickers()          # {symbol: ticker}

    # 先排除非加密貨幣資產(美股代幣、貴金屬等)
    crypto_only = {
        symbol: info
        for symbol, info in symbols_map.items()
        if not is_excluded_asset(info, config)
    }
    excluded_count = len(symbols_map) - len(crypto_only)
    print(f"排除非加密貨幣資產(美股代幣/貴金屬等)數量:{excluded_count} / {len(symbols_map)}")

    # 條件一:先用 24 小時成交金額篩選,減少後續 K 線 API 呼叫量
    candidates = []
    for symbol, info in crypto_only.items():
        ticker = tickers.get(symbol)
        if not ticker:
            continue
        try:
            amount_24h = float(ticker.get("amount", 0))
        except (TypeError, ValueError):
            continue
        if amount_24h > config["min_24h_amount_usdt"]:
            candidates.append((symbol, info["base"]))

    print(f"通過 24 小時成交金額篩選的幣種數量:{len(candidates)} / {len(crypto_only)}")

    session = requests.Session()
    matches = []

    for symbol, base_currency in candidates:
        try:
            klines = get_klines(session, symbol, interval, config["kline_fetch_limit"])
        except Exception as e:
            print(f"[警告] 取得 {symbol} K 線失敗:{e}")
            continue
        finally:
            time.sleep(config["request_sleep_sec"])

        matched, close_price, pct = evaluate_symbol(klines, config, interval_ms, now_ms)
        if matched:
            matches.append((base_currency, close_price, pct))

    print(f"本次符合全部條件的幣種數量:{len(matches)}")

    state = load_json(STATE_FILE, {})
    state["last_run_utc"] = datetime.now(timezone.utc).isoformat()
    state["last_match_count"] = len(matches)
    save_json(STATE_FILE, state)

    if matches:
        now_taipei = datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M")
        interval_minutes = interval_ms // 60000
        lines = [
            f"⚠️ Pionex 條件符合快訊 ({now_taipei} UTC+8)",
            "=============================",
            f"條件(當前偵測 {interval_minutes} 分鐘級別)",
            f"1.24小時成交量>{int(config['min_24h_amount_usdt'])}usdt",
            f"2.成交量>{config['vol_multiplier']}倍mavol{config['mavol_period']}",
            f"3.漲幅實體為前一根的{config['pct_change_multiplier']}倍",
            f"4.實體飽滿陽K(實體≥{int(config['min_body_ratio']*100)}%)",
            f"5.前一根上影線≤最新K線實體的{int(config['max_prev_wick_ratio']*100)}%",
            "=============================",
        ]
        for base_currency, close_price, pct in matches:
            lines.append(
                f"{base_currency.lower()}: 上漲 {pct:.2f}%(現價{format_price(close_price)})"
            )
        message = "\n".join(lines)
        print(message)
        send_telegram_message(message)
    else:
        print("沒有符合條件的幣種,本次不發送通知。")


if __name__ == "__main__":
    main()
