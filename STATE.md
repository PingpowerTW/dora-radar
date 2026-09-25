# Loop State — Dora Dashboard

> 狀態主幹檔案。每次 Daily Triage 執行後更新。

---

Last run: 2026-09-22T14:45:00+08:00 (full integrated repair & optimization)
Next scheduled: daily 20:00 via Hermes gateway cron (job `8dbd0d2806a5`)

## High Priority (需處理)

- 無 (已全數修復完成)

## Watch List (觀察中)

- Dora 今晚 20:00 自動執行巡檢與推播確認

## Recent Noise (已忽略)

- 無

## System Health

| Component | Status | Notes |
|-----------|--------|-------|
| Backend (port 8081) | ✅ running | `dora-dashboard.service` (FastAPI + Async PostgREST) |
| Cron/Scheduler | ✅ active | Hermes scheduler `8dbd0d2806a5`, daily 20:00 CST (93 completed) |
| Supabase connection | ✅ OK | 100.92.131.83:8000 PostgREST (4,153+ daily records) |
| Weekly Aggregation | ✅ OK | 14 週歷史全量回填 (2,443 筆去重記錄，2026-06-22 ~ 2026-09-21) |
| Monthly Aggregation | ✅ OK | 4 個月歷史全量回填 (1,940 筆去重記錄，2026-06-01 ~ 2026-09-01) |
| Data freshness | ✅ fresh | Latest date: 2026-09-22 (110 records gathered) |
| Scrape Speed | ✅ 4.55s | Parallel translation (ThreadPoolExecutor 10) + Bulk Upsert (batch 50) |
| Period Navigation | ✅ OK | 支援 日度/週度/月度 雙向步進與歷史下拉選單 |
| AI Insights History | ✅ OK | 30+ archived Dora reports available in dropdown |

## Run History

| Date | Status | Records | Notes |
|------|--------|---------|-------|
| 2026-09-22 | manual/optimized | 110 | Complete pipeline overhaul & bulk insert test |
| 2026-09-21 | automated | 108 | Daily scrape + analysis |
| 2026-09-20 | automated | 106 | Daily scrape + analysis |
| 2026-09-19 | manual | 138 | Data refresh (scrape+store) |

## 已完成最佳化項目 (Completed Optimizations)

| # | Item | Status | When | Notes |
|---|------|--------|------|-------|
| 1 | PostgREST 1000 筆截斷 Bug | ✅ | 2026-09-22 | 修正 `store_daily_data` 與 `get_daily_stats` 排序與計數 |
| 2 | 採集管線效能提速 8.8x | ✅ | 2026-09-22 | 批次 Upsert (50 筆/批) + 並行翻譯 (10 執行緒)，從 40s 降至 4.55s |
| 3 | 日期切換與歷史導航 | ✅ | 2026-09-22 | 新增 `/api/dates`，前端支援前一日/後一日/最新一日及歷史日曆下拉 |
| 4 | Dora 排程即時看板 | ✅ | 2026-09-22 | 新增 `/api/cron/status` 與頂部排程狀態列，透明顯示上次與下次巡檢時間 |
| 5 | Dora 歷次智囊日報歸檔 | ✅ | 2026-09-22 | 支援 `/api/ai/insights/history`，前端可切換查看近 30 期 Telegram 監控日報 |
| 6 | 即時採集即時輪詢回饋 | ✅ | 2026-09-22 | `/api/scrape/status` 輪詢，按鈕載入動畫與耗時動態 Toast |
| 7 | 歷史週度與月度全量回填 | ✅ | 2026-09-22 | 回填 80 天 4,153 筆日資料至 14 週 (2,443 筆) 與 4 月 (1,940 筆) |
| 8 | 週度與月度專屬導航與專案卡片指標 | ✅ | 2026-09-22 | 新增 `/api/weeks` 與 `/api/months`，支援最高單日/日均/霸榜天數/月度趨勢 |
| 9 | 修復生命週期篩選狀態洩漏 Bug | ✅ | 2026-09-22 | 切換頁籤自動重置 `currentLifecycleFilter = 'all'`，防止非日度資料被誤過濾為空白 |

---

*此文件由 loop-triage / antigravity agent 維護。*
