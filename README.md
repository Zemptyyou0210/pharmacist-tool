# 藥師諮詢紀錄輔助工具

## 檔案說明
- `app.py` — 主程式
- `requirements.txt` — 套件需求
- `drug_db_sample.csv` — 院內品項範例（請改名為 drug_db.csv 並換成你們的資料）

## 部署方式

### 本機測試
```bash
pip install -r requirements.txt
streamlit run app.py
```

### Streamlit Community Cloud
1. 把三個檔案推上 GitHub（public repo）
2. 去 share.streamlit.io 登入 → Deploy

### 院內 Server
```bash
pip install -r requirements.txt
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

## 院內品項 CSV 格式
第一行為欄位名稱，需包含：
- 藥品名稱欄：欄位名含 drug / name / 藥品 / 品名
- ATC欄：欄位名含 atc / class / 分類

```csv
drug_name,atc_code
Warfarin 5mg,B
Amlodipine Besylate 5mg,C
```

## 功能
- 貼上藥品文字 → 自動切割 + 對照院內品項帶入 ATC
- 每筆藥品展開細填（狀態、ATC、劑量、頻次、途徑）
- 追蹤數值（BP、GluAC、GluPC、HbA1c、Cr）
- 字數即時計算，超過 200 字提示
- 產生 HIS 短版（貼備註欄用）
- 下載完整 Excel（含藥品清單 + 諮詢資訊兩個 sheet）
- 底部貼入分析工具（解析 HIS 備註回結構化資料）
