#!/usr/bin/env python3
"""
GitHub Trending Dashboard Backend
==================================
High-performance FastAPI backend for Dora GitHub Trending Dashboard.
Provides async REST API endpoints, in-memory TTL caching, repo history analytics,
and static frontend serving.
"""

import os
import sys
import json
import time
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

import httpx
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ============================================================
# CONFIGURATION
# ============================================================
SUPABASE_URL = os.getenv("SUPABASE_URL", "http://100.92.131.83:8000").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
if not SUPABASE_SERVICE_KEY:
    SUPABASE_SERVICE_KEY = os.getenv("SERVICE_ROLE_KEY", "")

# Auto-detect keys from supabase .env if not set
if not SUPABASE_ANON_KEY or not SUPABASE_SERVICE_KEY:
    env_path = "/home/pipadmin/supabase/.env"
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("ANON_KEY=") and "=" in line:
                    SUPABASE_ANON_KEY = line.split("=", 1)[1]
                elif line.startswith("SERVICE_ROLE_KEY=") and "=" in line:
                    SUPABASE_SERVICE_KEY = line.split("=", 1)[1]

SCRIPTS_DIR = Path(__file__).parent
FRONTEND_DIR = SCRIPTS_DIR / "frontend"
INSIGHT_FILE = SCRIPTS_DIR / "latest_insight.json"

# ============================================================
# IN-MEMORY TTL CACHE
# ============================================================
class SimpleCache:
    def __init__(self, default_ttl: int = 60):
        self.cache: Dict[str, tuple[float, Any]] = {}
        self.default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        if key in self.cache:
            expires_at, val = self.cache[key]
            if time.time() < expires_at:
                return val
            else:
                del self.cache[key]
        return None

    def set(self, key: str, val: Any, ttl: Optional[int] = None):
        ttl = ttl if ttl is not None else self.default_ttl
        self.cache[key] = (time.time() + ttl, val)

    def clear(self):
        self.cache.clear()

cache = SimpleCache(default_ttl=45)

# Global Async HTTP Client
http_client: Optional[httpx.AsyncClient] = None

# ============================================================
# SUPABASE ASYNC QUERY HELPER
# ============================================================
async def async_supabase_get(
    table: str, 
    filters: dict = None, 
    order: str = None, 
    limit: int = None, 
    offset: int = None,
    select: str = "*"
) -> list:
    """Async query data from Supabase PostgREST."""
    global http_client
    if http_client is None or http_client.is_closed:
        http_client = httpx.AsyncClient(timeout=15.0)

    params = [f"select={select}"]
    
    if filters:
        for k, v in filters.items():
            if isinstance(v, list):
                params.append(f"{k}=in.{','.join(str(x) for x in v)}")
            elif isinstance(v, str) and v.startswith("'"):
                params.append(f"{k}=eq.{v.strip(chr(39))}")
            elif '[' in k and ']' in k:
                clean_key = k.split('[')[0]
                operator = k.split('[')[1].rstrip(']')
                params.append(f"{clean_key}={operator}.{v}")
            else:
                params.append(f"{k}=eq.{v}")
    
    if order:
        order_parts = order.split(",")
        cleaned_parts = []
        for part in order_parts:
            part = part.strip()
            if " " in part:
                fields = part.rsplit(" ", 1)
                cleaned_parts.append(f"{fields[0]}.{fields[1]}")
            else:
                cleaned_parts.append(part)
        order_clean = ",".join(cleaned_parts)
        params.append(f"order={order_clean}")
        
    if limit:
        params.append(f"limit={limit}")
    if offset:
        params.append(f"offset={offset}")
    
    query_str = "&".join(params)
    url = f"{SUPABASE_URL}/rest/v1/{table}?{query_str}"
    
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Accept": "application/json"
    }
    
    try:
        resp = await http_client.get(url, headers=headers)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"⚠️ Supabase query status {resp.status_code}: {resp.text}", file=sys.stderr)
            return []
    except Exception as e:
        print(f"⚠️ Supabase async query error: {e}", file=sys.stderr)
        return []


async def async_supabase_count(table: str, filters: dict = None) -> int:
    """Get exact count of rows matching filters using PostgREST HEAD/count=exact."""
    global http_client
    if http_client is None or http_client.is_closed:
        http_client = httpx.AsyncClient(timeout=15.0)

    params = ["select=id"]
    if filters:
        for k, v in filters.items():
            if isinstance(v, list):
                params.append(f"{k}=in.{','.join(str(x) for x in v)}")
            elif isinstance(v, str) and v.startswith("'"):
                params.append(f"{k}=eq.{v.strip(chr(39))}")
            elif '[' in k and ']' in k:
                clean_key = k.split('[')[0]
                operator = k.split('[')[1].rstrip(']')
                params.append(f"{clean_key}={operator}.{v}")
            else:
                params.append(f"{k}=eq.{v}")

    query_str = "&".join(params)
    url = f"{SUPABASE_URL}/rest/v1/{table}?{query_str}"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Prefer": "count=exact",
        "Range": "0-0"
    }
    try:
        resp = await http_client.get(url, headers=headers)
        content_range = resp.headers.get("content-range", "")
        if "/" in content_range:
            count_part = content_range.split("/")[1]
            if count_part.isdigit():
                return int(count_part)
    except Exception as e:
        print(f"⚠️ Supabase count error: {e}", file=sys.stderr)
    return 0


def supabase_get(table: str, filters: dict = None, order: str = None, 
                 limit: int = None, select: str = "*") -> list:
    """Synchronous fallback for scripts / CLI."""
    import urllib.request
    params = [f"select={select}"]
    if filters:
        for k, v in filters.items():
            if isinstance(v, list):
                params.append(f"{k}=in.{','.join(str(x) for x in v)}")
            elif isinstance(v, str) and v.startswith("'"):
                params.append(f"{k}=eq.{v.strip(chr(39))}")
            elif '[' in k and ']' in k:
                clean_key = k.split('[')[0]
                operator = k.split('[')[1].rstrip(']')
                params.append(f"{clean_key}={operator}.{v}")
            else:
                params.append(f"{k}=eq.{v}")
    if order:
        order_parts = order.split(",")
        cleaned_parts = []
        for part in order_parts:
            part = part.strip()
            if " " in part:
                fields = part.rsplit(" ", 1)
                cleaned_parts.append(f"{fields[0]}.{fields[1]}")
            else:
                cleaned_parts.append(part)
        params.append(f"order={urllib.request.quote(','.join(cleaned_parts))}")
    if limit:
        params.append(f"limit={limit}")
    
    query = "&".join(params)
    url = f"{SUPABASE_URL}/rest/v1/{table}?{query}"
    req = urllib.request.Request(url)
    req.add_header("apikey", SUPABASE_ANON_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_SERVICE_KEY}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  ⚠️  Supabase query error: {e}", file=sys.stderr)
        return []

# ============================================================
# FASTAPI APPLICATION
# ============================================================
app = FastAPI(
    title="Dora GitHub Trending Dashboard API",
    description="Intelligent AI Agent Evolution & GitHub Trend Analysis Backend",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    global http_client
    http_client = httpx.AsyncClient(timeout=15.0)

@app.on_event("shutdown")
async def shutdown_event():
    global http_client
    if http_client:
        await http_client.aclose()

## ============================================================
# API ENDPOINTS: DAILY
# ============================================================
@app.get("/api/dates")
async def get_available_dates():
    """Get list of distinct dates available in descending order."""
    cached = cache.get("available_dates")
    if cached:
        return cached

    # Query all records in chunks of 1000 to get full date history
    date_counts: Dict[str, int] = {}
    for offset in range(0, 10000, 1000):
        records = await async_supabase_get(
            "github_trending_daily",
            select="date",
            order="date.desc",
            limit=1000,
            offset=offset if offset > 0 else None
        )
        if not records:
            break
        for r in records:
            d = r.get("date")
            if d:
                date_counts[d] = date_counts.get(d, 0) + 1
        if len(records) < 1000:
            break

    sorted_dates = [
        {"date": d, "count": c} 
        for d, c in sorted(date_counts.items(), key=lambda x: x[0], reverse=True)
    ]
    latest_date = sorted_dates[0]["date"] if sorted_dates else datetime.now().strftime("%Y-%m-%d")

    result = {
        "latest": latest_date,
        "today": datetime.now().strftime("%Y-%m-%d"),
        "dates": sorted_dates
    }
    cache.set("available_dates", result, ttl=45)
    return result


@app.get("/api/daily", response_model=List[Dict[str, Any]])
async def get_daily_trending(
    date: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD) or 'latest'"),
    limit: int = Query(150, ge=1, le=300, description="Max results"),
    relevance: Optional[str] = Query(None, description="Filter by relevance (critical/high/medium/low)"),
    language: Optional[str] = Query(None, description="Filter by programming language"),
    search: Optional[str] = Query(None, description="Search repo name or description"),
    sort: str = Query("today", description="Sort by: today, total, growth, streak, name")
):
    """Get daily trending repositories with multi-dimensional filtering. Defaults to latest available date."""
    filters = {}
    
    # Auto-detect latest date if not explicitly specified
    if not date or date == "latest":
        latest_row = await async_supabase_get(
            "github_trending_daily",
            select="date",
            order="date.desc",
            limit=1
        )
        if latest_row and latest_row[0].get("date"):
            date = str(latest_row[0]["date"])

    if date:
        filters["date"] = f"'{date}'"
    if relevance:
        filters["relevance_level"] = f"'{relevance}'"
    if language and language.lower() != "all":
        filters["language"] = f"'{language}'"

    order_clause = "today_stars.desc"
    if sort == "total":
        order_clause = "total_stars.desc"
    elif sort == "growth":
        order_clause = "growth_rate.desc"
    elif sort == "streak":
        order_clause = "consecutive_days.desc"
    elif sort == "name":
        order_clause = "repo_name.asc"

    repos = await async_supabase_get(
        "github_trending_daily", 
        filters=filters, 
        order=order_clause,
        limit=limit
    )

    if search:
        s_lower = search.lower().strip()
        repos = [
            r for r in repos 
            if s_lower in r.get("repo_name", "").lower() 
            or s_lower in (r.get("description") or "").lower() 
            or s_lower in (r.get("description_zh") or "").lower()
            or any(s_lower in tag.lower() for tag in (r.get("relevance_tags") or []))
            or any(s_lower in ch.lower() for ch in (r.get("channels") or []))
        ]

    return repos


@app.get("/api/daily/latest")
async def get_latest_daily(limit: int = Query(7, ge=1, le=30, description="Last N days")):
    """Get the latest N days of trending data grouped by date."""
    cache_key = f"latest_daily_{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    repos = await async_supabase_get(
        "github_trending_daily", 
        order="date.desc,today_stars.desc",
        limit=limit * 35
    )

    from collections import OrderedDict
    daily_groups = OrderedDict()
    for r in repos:
        d = r.get("date")
        if d not in daily_groups:
            daily_groups[d] = []
        daily_groups[d].append(r)

    latest = dict(list(daily_groups.items())[:limit])
    cache.set(cache_key, latest, ttl=60)
    return latest


@app.get("/api/daily/stats")
async def get_daily_stats():
    """Get accurate statistics about daily trending data with in-memory TTL caching."""
    cached = cache.get("daily_stats")
    if cached:
        return cached

    # 1. Exact total records from database
    total_records = await async_supabase_count("github_trending_daily")

    # 2. Latest and earliest dates
    latest_row = await async_supabase_get("github_trending_daily", select="date", order="date.desc", limit=1)
    earliest_row = await async_supabase_get("github_trending_daily", select="date", order="date.asc", limit=1)
    latest_date = latest_row[0].get("date") if latest_row else None
    earliest_date = earliest_row[0].get("date") if earliest_row else None

    # 3. Active recent snapshot (ordered by date.desc, limit 1000) for language and relevance breakdown
    recent_repos = await async_supabase_get(
        "github_trending_daily", 
        select="date,repo_name,relevance_level,language,total_stars,today_stars",
        order="date.desc",
        limit=1000
    )

    if not recent_repos:
        return {"total_records": 0, "unique_dates": 0, "unique_repos": 0}

    dates = set(r.get("date") for r in recent_repos if r.get("date"))
    repo_names = set(r.get("repo_name") for r in recent_repos if r.get("repo_name"))

    relevance_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    lang_counts: Dict[str, int] = {}
    top_today_star = 0
    top_repo = None

    for r in recent_repos:
        level = r.get("relevance_level", "low")
        relevance_counts[level] = relevance_counts.get(level, 0) + 1
        
        lang = r.get("language")
        if lang and lang != "Unknown":
            lang_counts[lang] = lang_counts.get(lang, 0) + 1

        t_star = r.get("today_stars") or 0
        if t_star > top_today_star:
            top_today_star = t_star
            top_repo = r.get("repo_name")

    # Sort languages
    sorted_langs = sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    stats = {
        "total_records": total_records or len(recent_repos),
        "unique_dates": len(dates),
        "unique_repos": len(repo_names),
        "relevance_distribution": relevance_counts,
        "top_languages": dict(sorted_langs),
        "date_range": {
            "earliest": earliest_date,
            "latest": latest_date,
        },
        "highlight": {
            "top_today_repo": top_repo,
            "top_today_stars": top_today_star,
        }
    }

    cache.set("daily_stats", stats, ttl=60)
    return stats


# ============================================================
# API ENDPOINTS: WEEKLY & MONTHLY
# ============================================================
@app.get("/api/weekly", response_model=List[Dict[str, Any]])
async def get_weekly_trending(
    week_start: Optional[str] = Query(None, description="Filter by week start date"),
    limit: int = Query(60, ge=1, le=200, description="Max results"),
    language: Optional[str] = Query(None, description="Filter by language"),
    sort: str = Query("total", description="Sort by: total, peak, avg")
):
    """Get weekly aggregated trending repositories."""
    filters = {}
    if week_start:
        filters["week_start"] = f"'{week_start}'"
    if language and language.lower() != "all":
        filters["language"] = f"'{language}'"

    order_field = "total_stars.desc" if sort == "total" else "peak_today_stars.desc" if sort == "peak" else "avg_daily_stars.desc"

    repos = await async_supabase_get(
        "github_trending_weekly", 
        filters=filters,
        order=order_field,
        limit=limit
    )
    return repos


@app.get("/api/weekly/latest")
async def get_latest_weekly(limit: int = Query(4, ge=1, le=12, description="Last N weeks")):
    """Get the latest N weeks of aggregated data."""
    cache_key = f"latest_weekly_{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    repos = await async_supabase_get(
        "github_trending_weekly", 
        order="week_start.desc,total_stars.desc",
        limit=limit * 50
    )

    from collections import OrderedDict
    weekly_groups = OrderedDict()
    for r in repos:
        ws = r.get("week_start")
        if ws not in weekly_groups:
            weekly_groups[ws] = []
        weekly_groups[ws].append(r)

    latest = dict(list(weekly_groups.items())[:limit])
    cache.set(cache_key, latest, ttl=60)
    return latest


@app.get("/api/monthly", response_model=List[Dict[str, Any]])
async def get_monthly_trending(
    month_start: Optional[str] = Query(None, description="Filter by month start date"),
    limit: int = Query(60, ge=1, le=200, description="Max results"),
    language: Optional[str] = Query(None, description="Filter by language"),
    sort: str = Query("total", description="Sort by: total, peak, appearances")
):
    """Get monthly aggregated trending repositories."""
    filters = {}
    if month_start:
        filters["month_start"] = f"'{month_start}'"
    if language and language.lower() != "all":
        filters["language"] = f"'{language}'"

    order_field = "total_stars.desc" if sort == "total" else "peak_today_stars.desc" if sort == "peak" else "total_appearances.desc"

    repos = await async_supabase_get(
        "github_trending_monthly", 
        filters=filters,
        order=order_field,
        limit=limit
    )
    return repos


@app.get("/api/monthly/latest")
async def get_latest_monthly(limit: int = Query(6, ge=1, le=24, description="Last N months")):
    """Get the latest N months of aggregated data."""
    cache_key = f"latest_monthly_{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    repos = await async_supabase_get(
        "github_trending_monthly", 
        order="month_start.desc,total_stars.desc",
        limit=limit * 50
    )

    from collections import OrderedDict
    monthly_groups = OrderedDict()
    for r in repos:
        ms = r.get("month_start")
        if ms not in monthly_groups:
            monthly_groups[ms] = []
        monthly_groups[ms].append(r)

    latest = dict(list(monthly_groups.items())[:limit])
    cache.set(cache_key, latest, ttl=60)
    return latest


# ============================================================
# API ENDPOINTS: TREND ANALYSIS & REPO HISTORY
# ============================================================
@app.get("/api/languages")
async def get_languages():
    """Get available programming languages and their repository counts."""
    cached = cache.get("languages_list")
    if cached:
        return cached

    repos = await async_supabase_get(
        "github_trending_daily",
        select="language,language_color",
        limit=5000
    )

    lang_map: Dict[str, Dict[str, Any]] = {}
    for r in repos:
        lang = r.get("language")
        if lang and lang != "Unknown":
            if lang not in lang_map:
                lang_map[lang] = {
                    "name": lang,
                    "color": r.get("language_color") or "#8b949e",
                    "count": 0
                }
            lang_map[lang]["count"] += 1

    sorted_langs = sorted(lang_map.values(), key=lambda x: x["count"], reverse=True)
    cache.set("languages_list", sorted_langs, ttl=120)
    return sorted_langs


@app.get("/api/trends/rising-stars")
async def get_rising_stars(min_appearances: int = Query(2, ge=2, le=10), limit: int = Query(20, ge=1, le=50)):
    """Get repositories that consistently trend across multiple days."""
    cache_key = f"rising_stars_{min_appearances}_{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    repos = await async_supabase_get(
        "github_trending_daily",
        select="repo_name,repo_url,description,description_zh,language,language_color,total_stars,today_stars,relevance_level,relevance_tags,date",
        limit=10000
    )

    repo_map: Dict[str, Dict[str, Any]] = {}
    for r in repos:
        name = r.get("repo_name")
        if not name:
            continue
        if name not in repo_map:
            repo_map[name] = {
                "repo_name": name,
                "repo_url": r.get("repo_url"),
                "description": r.get("description"),
                "description_zh": r.get("description_zh", ""),
                "language": r.get("language", "Unknown"),
                "language_color": r.get("language_color", ""),
                "total_stars": r.get("total_stars") or 0,
                "total_appearances": 0,
                "total_today_stars": 0,
                "peak_today_stars": 0,
                "relevance_level": r.get("relevance_level", "low"),
                "relevance_tags": r.get("relevance_tags", []),
                "dates": []
            }
        
        entry = repo_map[name]
        if not entry["description_zh"] and r.get("description_zh"):
            entry["description_zh"] = r.get("description_zh")
        entry["total_appearances"] += 1
        t_star = r.get("today_stars") or 0
        entry["total_today_stars"] += t_star
        if t_star > entry["peak_today_stars"]:
            entry["peak_today_stars"] = t_star
        if (r.get("total_stars") or 0) > entry["total_stars"]:
            entry["total_stars"] = r.get("total_stars") or 0
        entry["dates"].append(str(r.get("date")))

    rising = [
        v for v in repo_map.values() 
        if v["total_appearances"] >= min_appearances
    ]
    rising.sort(key=lambda x: (x["total_appearances"], x["total_today_stars"]), reverse=True)
    result = rising[:limit]
    cache.set(cache_key, result, ttl=60)
    return result


@app.get("/api/trends/daily-top")
async def get_daily_top_repos(days: int = Query(7, ge=1, le=30), limit: int = Query(20, ge=1, le=50)):
    """Get top repositories over the last N days."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    repos = await async_supabase_get(
        "github_trending_daily",
        filters={"date[gte]": cutoff},
        order="today_stars.desc",
        limit=days * 25
    )
    return repos[:limit]


@app.get("/api/repo/{owner}/{repo_name}/history")
async def get_repo_history(owner: str, repo_name: str):
    """Get historical tracking data and star growth timeline for a specific repository."""
    full_name = f"{owner}/{repo_name}"
    cache_key = f"repo_hist_{full_name}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    records = await async_supabase_get(
        "github_trending_daily",
        filters={"repo_name": f"'{full_name}'"},
        order="date.asc",
        limit=100
    )

    if not records:
        raise HTTPException(status_code=404, detail="Repository not found in history")

    timeline = []
    total_gain = 0
    zh_desc = ""
    for rec in records:
        today_star = rec.get("today_stars") or 0
        total_gain += today_star
        if not zh_desc and rec.get("description_zh"):
            zh_desc = rec.get("description_zh")
        timeline.append({
            "date": str(rec.get("date")),
            "today_stars": today_star,
            "total_stars": rec.get("total_stars") or 0,
            "relevance_level": rec.get("relevance_level"),
        })

    latest = records[-1]
    history_data = {
        "repo_name": full_name,
        "repo_url": latest.get("repo_url"),
        "description": latest.get("description"),
        "description_zh": zh_desc or latest.get("description_zh", ""),
        "language": latest.get("language", "Unknown"),
        "language_color": latest.get("language_color", ""),
        "forks": latest.get("forks", 0),
        "total_stars": latest.get("total_stars", 0),
        "total_appearances": len(records),
        "first_seen": str(records[0].get("date")),
        "last_seen": str(records[-1].get("date")),
        "cumulative_trending_stars": total_gain,
        "relevance_level": latest.get("relevance_level"),
        "relevance_tags": latest.get("relevance_tags", []),
        "timeline": timeline,
    }

    cache.set(cache_key, history_data, ttl=60)
    return history_data


@app.get("/api/ai/latest-insight")
async def get_latest_insight():
    """Get Dora's latest AI trend insight, recommendations, and report summary."""
    if INSIGHT_FILE.exists():
        try:
            with open(INSIGHT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
        except Exception as e:
            print(f"⚠️ Error reading insight file: {e}", file=sys.stderr)

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "updated_at": datetime.now().isoformat(),
        "top_picks": [],
        "trends": {"agent_count": 0, "skill_count": 0, "video_count": 0},
        "top3": [],
        "markdown_report": "尚無最新分析報告，請觸發即時採集或等待每日排程。",
        "total_repos": 0
    }


# ============================================================
# API ENDPOINTS: SCRAPE TRIGGER & STATUS
# ============================================================
_SCRAPE_LOCK = asyncio.Lock()
_scrape_state = {
    "is_running": False,
    "last_run": None,
    "last_status": "idle",
    "last_records": 0,
    "duration_sec": 0,
    "message": "系統待命中"
}

@app.get("/api/scrape/status")
async def get_scrape_status():
    """Get live status of GitHub Trending scraping task."""
    return _scrape_state

@app.post("/api/scrape/trigger")
async def trigger_live_scrape(background_tasks: BackgroundTasks):
    """Trigger an on-demand GitHub Trending scraping and aggregation run."""
    global _scrape_state
    if _SCRAPE_LOCK.locked() or _scrape_state["is_running"]:
        return JSONResponse(
            status_code=429, 
            content={"status": "busy", "message": "採集任務正在執行中，請稍候..."}
        )

    async def run_task():
        global _scrape_state
        _scrape_state["is_running"] = True
        _scrape_state["message"] = "正在爬取 GitHub Trending 8 頻道並進行相關性分類與翻譯..."
        start_t = time.time()
        try:
            from github_trending_analysis import run_full_cycle
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, run_full_cycle)
            dur = round(time.time() - start_t, 2)
            cache.clear()
            records_count = result.get("records", 0) if isinstance(result, dict) else 0
            _scrape_state = {
                "is_running": False,
                "last_run": datetime.now().isoformat(),
                "last_status": "ok",
                "last_records": records_count,
                "duration_sec": dur,
                "message": f"採集完成！共收錄 {records_count} 筆專案 (耗時 {dur}s)"
            }
            print(f"✅ On-demand scrape completed: {records_count} records ({dur}s).")
        except Exception as e:
            dur = round(time.time() - start_t, 2)
            _scrape_state = {
                "is_running": False,
                "last_run": datetime.now().isoformat(),
                "last_status": "error",
                "last_records": 0,
                "duration_sec": dur,
                "message": f"採集失敗：{str(e)}"
            }
            print(f"❌ On-demand scrape error: {e}", file=sys.stderr)

    background_tasks.add_task(run_task)
    return {
        "status": "started", 
        "message": "GitHub Trending 採集任務已在後台啟動，預計 3-8 秒內完成。"
    }


# ============================================================
# API ENDPOINTS: DORA CRON & HISTORICAL INSIGHTS
# ============================================================
@app.get("/api/cron/status")
async def get_cron_status():
    """Get Dora's automated monitoring cron job status from Hermes scheduler."""
    jobs_file = Path("/home/pipadmin/.hermes/cron/jobs.json")
    if not jobs_file.exists():
        return {
            "status": "not_configured",
            "schedule_human": "每日 20:00 (台北時間)",
            "message": "Cron jobs file not found"
        }

    try:
        with open(jobs_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            jobs = data.get("jobs", [])
            target_job = next((j for j in jobs if j.get("id") == "8dbd0d2806a5"), None)
            if target_job:
                return {
                    "status": "active" if target_job.get("enabled") else "paused",
                    "name": target_job.get("name"),
                    "schedule": target_job.get("schedule_display", "0 20 * * *"),
                    "schedule_human": "每日 20:00 (台北時間)",
                    "next_run_at": target_job.get("next_run_at"),
                    "last_run_at": target_job.get("last_run_at"),
                    "last_status": target_job.get("last_status"),
                    "completed_times": target_job.get("repeat", {}).get("completed", 0),
                    "platform": target_job.get("origin", {}).get("platform"),
                    "chat_name": target_job.get("origin", {}).get("chat_name")
                }
    except Exception as e:
        print(f"⚠️ Error reading cron status: {e}", file=sys.stderr)

    return {
        "status": "active",
        "schedule": "0 20 * * *",
        "schedule_human": "每日 20:00 (台北時間)"
    }


@app.get("/api/ai/insights/history")
async def get_insights_history():
    """Get list of historical daily insight reports."""
    output_dir = Path("/home/pipadmin/.hermes/cron/output")
    reports = []
    if output_dir.exists():
        for p in sorted(output_dir.glob("8dbd0d2806a5_*.txt"), reverse=True):
            fname = p.name
            parts = fname.replace(".txt", "").split("_")
            if len(parts) >= 3:
                d_str = parts[1] # YYYYMMDD
                t_str = parts[2] # HHMMSS
                date_formatted = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
                time_formatted = f"{t_str[:2]}:{t_str[2:4]}:{t_str[4:]}"
                reports.append({
                    "id": fname,
                    "date": date_formatted,
                    "time": time_formatted,
                    "datetime": f"{date_formatted} {time_formatted}",
                    "size": p.stat().st_size
                })
    return reports[:30]


@app.get("/api/ai/insights/report/{filename}")
async def get_historical_report(filename: str):
    """Get content of a specific historical report."""
    output_dir = Path("/home/pipadmin/.hermes/cron/output")
    target = output_dir / filename
    # Security: prevent directory traversal
    try:
        if not target.resolve().is_relative_to(output_dir.resolve()):
            raise HTTPException(status_code=403, detail="Forbidden")
    except Exception:
        raise HTTPException(status_code=403, detail="Forbidden")

    if not target.exists():
        raise HTTPException(status_code=404, detail="Report not found")

    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
            if "## 📊 每日 GitHub 熱門專案監控報告" in content:
                content = content[content.index("## 📊 每日 GitHub 熱門專案監控報告"):]
            elif "## 📊" in content:
                content = content[content.index("## 📊"):]
            
            import re
            date_m = re.search(r"(\d{4}-\d{2}-\d{2})", content)
            date_str = date_m.group(1) if date_m else filename
            return {
                "filename": filename,
                "date": date_str,
                "markdown_report": content,
                "content": content,
                "trends": {"agent_count": "-", "skill_count": "-", "video_count": "-"},
                "top3": [],
                "total_repos": "-"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# STATIC FILES & HEALTH
# ============================================================
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
async def serve_dashboard():
    """Serve the main dashboard Single Page Application."""
    html_path = FRONTEND_DIR / "index.html"
    if html_path.exists():
        return FileResponse(html_path)
    return HTMLResponse("<h1>Dora GitHub Trending Dashboard</h1><p>Frontend file not found.</p>")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "supabase_url": SUPABASE_URL,
        "timestamp": datetime.now().isoformat(),
        "cache_entries": len(cache.cache)
    }


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8081"))
    print(f"🚀 Starting Dora Dashboard Backend on port {port}...")
    print(f"📊 Supabase: {SUPABASE_URL}")
    uvicorn.run(app, host="0.0.0.0", port=port)

