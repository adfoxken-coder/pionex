# Pionex 合約價格監控 + Telegram 通知

每小時自動抓取 **Pionex 交易所目前支援的所有合約(PERP)幣種**價格,
符合你設定的條件時,透過 Telegram 推播訊息通知你。完全免費,不需要自己的電腦或伺服器。

---

## 運作原理

- 資料來源:Pionex 公開 API(`api.pionex.com`),不需要 API Key
  - `GET /api/v1/common/symbols?type=PERP` → 取得目前所有合約幣種清單
  - `GET /api/v1/market/tickers?type=PERP` → 取得這些幣種的即時價格
- 執行環境:**GitHub Actions**(GitHub 提供的免費雲端排程服務),每小時自動執行一次
- 通知方式:**Telegram Bot**,發送訊息給你自己

> 為什麼選 Telegram 而不是 LINE?LINE Messaging API 免費方案每月只有 200 則推播額度,
> 如果監控的合約幣種數量多、又設定較敏感的漲跌幅門檻,很容易一個月就超過。
> Telegram Bot 傳送訊息**完全免費、沒有則數上限**,更適合這種用途,設定也更簡單。

## 內建的兩種警示條件(可在 `config.json` 調整)

1. **漲跌幅警示**:任一合約幣種價格與「上次執行(上一小時)」相比,漲跌幅超過
   `pct_change_alert`(預設 5%)就發警示
2. **價格門檻警示**:針對你指定的幣種,設定「高於/低於某個價格」就發警示

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
4. 沒問題的話,之後就會**每小時自動執行**,不需要再手動操作

---

## 調整警示條件

打開 `config.json` 修改,例如:

```json
{
  "pct_change_alert": 3.0,
  "price_thresholds": {
    "BTC_USDT_PERP": { "above": 70000, "below": 60000 },
    "ETH_USDT_PERP": { "above": 4000 }
  }
}
```

- `pct_change_alert`:每小時漲跌幅超過幾 % 就通知(上面例子改成 3%)
- `price_thresholds`:針對特定合約幣種代號(格式通常是 `幣種_USDT_PERP`),
  設定 `above`(高於此價格通知)、`below`(低於此價格通知),兩者可同時設定或只設一個

改完後把 `config.json` 上傳/更新到 GitHub repo 即可,下一次執行就會套用新設定。

## 檔案說明

| 檔案 | 說明 |
|---|---|
| `fetch_and_alert.py` | 主程式,抓資料、判斷條件、發送 Telegram 訊息 |
| `config.json` | 你可自訂的警示條件 |
| `state.json` | 程式自動維護,記錄上次執行時的價格(用來算漲跌幅),不需要手動編輯 |
| `requirements.txt` | Python 套件需求(只需要 `requests`) |
| `.github/workflows/pionex_alert.yml` | GitHub Actions 排程設定,每小時執行一次 |

## 常見問題

**Q: 完全不用付費嗎?**
A: 是的。GitHub Actions 對 public/private repo 都有免費額度,這個任務每小時執行約 1 分鐘,
遠低於免費額度(private repo 每月 2000 分鐘)。Pionex 的市場資料 API 也是公開免費的。

**Q: 排程真的準時每小時執行嗎?**
A: GitHub 的 cron 排程在系統忙碌時可能會延遲幾分鐘,屬正常現象,不影響整體監控效果。

**Q: 想追蹤的幣種代號要去哪裡查?**
A: 可以直接在瀏覽器打開這個網址查看目前所有 Pionex 合約幣種:
`https://api.pionex.com/api/v1/common/symbols?type=PERP`
