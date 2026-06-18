# 月配息基金循環轉換模擬器

線上版：https://fund-opal.vercel.app/

純靜態網站（index.html / style.css / app.js / engine.js / data.js），部署在 Vercel，repo 根目錄就是部署的根目錄，不需要 build。改完檔案 `git push` 到 `main` 後 Vercel 會自動重新部署。

- `data.js`：三支美元月配息基金（JFZN3摩根多重收益／TLZN0安聯全球／ALBT8聯博美國成長）+ 安聯台灣科技基金（ACDD04）的歷史淨值與配息，內嵌成 JS 物件 `FUND_DATA`。
- `engine.js`：核心模擬邏輯 `simulate(params)`——三基金循環轉換（或單一基金買進持有）、配息部分轉出加碼安聯台灣科技、保單貸款試算。
- `app.js`：讀取畫面上的滑桿/輸入值，呼叫 `simulate()`，畫圖表（Chart.js）跟表格。
- `research/`：背後的原始 CSV 資料、資料蒐集/驗證用的 Python 腳本、目前的研究結論與待辦事項。**接續研究前請先看 [`research/README.md`](research/README.md)。**
