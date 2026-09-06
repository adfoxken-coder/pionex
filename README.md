# Pionex 合約技術條件監控 + Telegram 通知

台北時間每天 06:00–23:59,每 5 分鐘自動抓取一次 **Pionex 交易所目前支援的所有
合約(PERP)幣種**資料,同時符合三個技術條件時,透過 Telegram 推播訊息通知你。
完全免費,不需要自己的電腦或伺服器(repo 目前是 Public,GitHub Actions 執行時間無上限)。

---

## 運作原理

- 資料來源:Pionex 公開 API(`api.pionex.com`),不需要 API Key
  - `GET /api/v1/common/symbols?type=PERP` → 取得目前所有合約幣種清單
  - `GET /api/v1/market/tickers?type=PERP` → 取得 24 小時成交金額,做初步篩選
  - `GET /api/v1/market/klines` → 針對篩選後的幣種,抓取 5 分鐘 K 線做技術判斷
- 執行環境:**GitHub Actions**,台北時間每天 06:00–23:59、每 5 分鐘執行一次
- 通知方式:**Telegram Bot**,發送訊息給你自己

## 偵測條件(可在 `config.json` 調整數值)

同時符合以下三個條件的幣種才會觸發通知:

1. **24 小時成交金額(USDT)** > `min_24h_amount_usdt`(預設 20,000 USDT)
2. **最新收盤 5 分鐘 K 線的成交量** > `vol_multiplier` 倍的 **MAVOL5**
   (取這根 K 線「之前」的 5 根平均成交量,不含本身),**且該 K 線收陽**(收盤價 > 開盤價)
3. **最新收盤 K 線漲跌幅絕對值** ≥ `pct_change_multiplier` 倍的「前一根 K 線」
   漲跌幅絕對值;若前一根漲跌幅絕對值為 0,則改比較「前前一根」

> **技術假設說明:** 因為排程頻率是每 5 分鐘,程式採用 **5 分鐘 K 線** 做判斷
> (`config.json` 裡的 `kline_interval`)。如果之後想調整週期,記得同步調整這個值。

## 排程時間

台北時間(UTC+8)每天 06:00–23:59,換算成 GitHub 用的 UTC 時間是
22:00(前一天)~ 15:59(當天),因為跨過 UTC 午夜,workflow 裡用兩段
hour 範圍表示:`*/5 0-15,22,23 * * *`。00:00–05:59(台北時間)不會執行。

## Telegram 通知範例

```
⚠️ Pionex 條件符合快訊 (2026-09-06 17:30 UTC+8)
=============================
條件
1.24小時成交量>20000usdt
2.成交量>1.5倍mavol5
3.漲幅實體為前一根的2.0倍
=============================
btc: 上漲 1.03%(現價79952.4)
```

幣種名稱只顯示幣別本身(例如 `btc`),不含 `_USDT_PERP` 這種交易對後綴;
時間統一顯示台北時間(UTC+8)。

---

## 第一步:建立 Telegram Bot(取得 Token 和 Chat ID)

1. 在 Telegram 搜尋並打開官方的 **@BotFather** 這個帳號
2. 傳送指令 `/newbot`,依照指示幫你的 Bot 取一個名稱(例如 `Pionex 價格警示`)
   和一個以 `bot` 結尾的 username(例如 `pionex_alert_bot`)
3. 建立完成後,BotFather 會回傳一段類似
   `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` 的文字,
   這就是你的 **`TELEGRAM_BOT_TOKEN`**,複製起來
4. 到 Telegram 搜尋你剛剛建立的 Bot username,點擊進去並按 **Start**
   (一定要先跟 Bot 說過話,Bot 才能主動傳訊息給你)
5. 接著取得你的 **Chat ID**:在瀏覽器打開下面網址(把 `<TOKEN>` 換成你的 Token):
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   在回傳的 JSON 裡找 `"chat":{"id": 數字, ...}`,這個數字就是你的 **`TELEGRAM_CHAT_ID`**
   (如果畫面是空的,回去跟 Bot 隨便傳一句話再重新整理這個網址)

---

## 第二步:建立 GitHub Repository

1. 到 [github.com](https://github.com) 註冊/登入帳號(免費)
2. 建立一個新的 **Private repository**(私人的,避免你的設定被別人看到)
3. 把這個資料夾裡的所有檔案上傳上去(可以直接在網頁上用「Add file → Upload files」拖拉上傳),
   記得保留資料夾結構,`.github/workflows/pionex_alert.yml` 這個路徑要維持不變

## 第三步:設定 GitHub Secrets

1. 到你的 repository 頁面,點選 **Settings → Secrets and variables → Actions**
2. 點擊 **New repository secret**,新增兩組:
   - Name: `TELEGRAM_BOT_TOKEN`,Value:貼上第一步取得的 Token
   - Name: `TELEGRAM_CHAT_ID`,Value:貼上第一步取得的 Chat ID
3. 儲存

## 第四步:啟用並測試排程

1. 到 repository 的 **Actions** 分頁,如果出現提示,點擊啟用 workflows
2. 點選左側的 **Pionex Contract Price Alert**
3. 點擊右側 **Run workflow** 手動觸發一次,測試是否成功收到 Telegram 訊息
4. 沒問題的話,之後就會**每 5 分鐘自動執行一次**(台北時間 06:00–23:59 期間),不需要再手動操作

---

## 調整偵測條件

打開 `config.json` 修改,例如:

```json
{
  "kline_interval": "5M",
  "min_24h_amount_usdt": 20000,
  "mavol_period": 5,
  "vol_multiplier": 1.5,
  "pct_change_multiplier": 2.0,
  "kline_fetch_limit": 15,
  "request_sleep_sec": 0.15
}
```

- `min_24h_amount_usdt`:條件一,24 小時成交金額(USDT)門檻
- `mavol_period` / `vol_multiplier`:條件二,MAVOL 的期數和成交量倍數門檻
- `pct_change_multiplier`:條件三,漲跌幅需超過前一根的倍數
- `kline_interval`:K 線週期,**如果之後改動排程頻率,記得同步調整這個值**
- `kline_fetch_limit`、`request_sleep_sec`:內部技術參數,一般不需要調整

改完後把 `config.json` 上傳/更新到 GitHub repo 即可,下一次執行就會套用新設定。

## 檔案說明

| 檔案 | 說明 |
|---|---|
| `fetch_and_alert.py` | 主程式,抓資料、判斷三個條件、發送 Telegram 訊息 |
| `config.json` | 你可自訂的偵測條件參數 |
| `state.json` | 程式自動維護,記錄最近一次執行時間與符合數量,不需要手動編輯 |
| `requirements.txt` | Python 套件需求(只需要 `requests`) |
| `.github/workflows/pionex_alert.yml` | GitHub Actions 排程設定,台北時間每天 06:00–23:59、每 5 分鐘執行一次 |

## 常見問題

**Q: 完全不用付費嗎?**
A: 是的。你的 repo 目前是 Public,GitHub Actions 執行時間**完全不限制、無上限**,
完全免費。Pionex 的市場資料 API 也是公開免費的。

**Q: 排程真的準時每 5 分鐘執行嗎?**
A: GitHub 的 cron 排程在系統忙碌時可能會延遲幾分鐘,屬正常現象,不影響整體監控效果。

**Q: 想追蹤的幣種代號要去哪裡查?**
A: 可以直接在瀏覽器打開這個網址查看目前所有 Pionex 合約幣種:
`https://api.pionex.com/api/v1/common/symbols?type=PERP`

