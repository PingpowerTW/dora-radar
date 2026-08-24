#!/usr/bin/env python3
"""
GitHub Trending Analyzer with Supabase Integration
===================================================
Scrapes GitHub Trending, classifies relevance, and stores data in Supabase.
Generates daily/weekly/monthly reports with trend analysis.
"""

import json
import sys
import re
import os
import hashlib
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import quote


# ============================================================
# SUPABASE CONFIG
# ============================================================
SUPABASE_URL = os.getenv("SUPABASE_URL", "http://100.92.131.83:8000")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
if not SUPABASE_SERVICE_KEY:
    SUPABASE_SERVICE_KEY = os.getenv("SERVICE_ROLE_KEY", "")

# Auto-detect from supabase .env
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


def supabase_post(table: str, data: dict) -> dict:
    """Insert or upsert data into Supabase using PostgREST merge-duplicates."""
    import urllib.request
    
    # Determine conflict target based on table
    if table == "github_trending_daily":
        conflict_cols = "date,repo_name"
    elif table == "github_trending_weekly":
        conflict_cols = "week_start,repo_name"
    elif table == "github_trending_monthly":
        conflict_cols = "month_start,repo_name"
    else:
        conflict_cols = None
    
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if conflict_cols:
        url += f"?on_conflict={conflict_cols}"
        
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("apikey", SUPABASE_ANON_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_SERVICE_KEY}")
    req.add_header("Prefer", "resolution=merge-duplicates,return=representation")
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        print(f"  ⚠️  Supabase insert error for {data.get('repo_name', '?')} in {table} (HTTP {e.code}): {e.read().decode()}", file=sys.stderr)
        return {}
    except Exception as e:
        print(f"  ⚠️  Supabase insert error for {data.get('repo_name', '?')} in {table}: {e}", file=sys.stderr)
        return {}


def supabase_get(table: str, filters: dict = None, order: str = None, limit: int = None, select: str = None) -> list:
    """Query data from Supabase."""
    import urllib.request
    params = []
    if select:
        params.append(f"select={quote(select)}")
    if filters:
        for k, v in filters.items():
            if k == "select":
                params.append(f"select={quote(str(v))}")
            elif isinstance(v, list):
                params.append(f"{k}=in.({','.join(str(x) for x in v)})")
            elif isinstance(v, str) and v.startswith("'"):
                params.append(f"{k}=eq.{v.strip(chr(39))}")
            elif '[' in k and ']' in k:
                # Range filters: date[gte], date[lte] -> PostgREST format: date=gte.value
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
        params.append(f"order={quote(order_clean)}")
    if limit:
        params.append(f"limit={limit}")
    
    query = "&".join(params)
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if query:
        url += f"?{query}"
    
    req = urllib.request.Request(url)
    req.add_header("apikey", SUPABASE_ANON_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_SERVICE_KEY}")
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  ⚠️  Supabase query error: {e}", file=sys.stderr)
        return []


# ============================================================
# ============================================================
# MULTI-CHANNEL SCRAPING & PIPELINE
# ============================================================
TRENDING_CHANNELS = {
    "All": "https://github.com/trending?since=daily",
    "Python": "https://github.com/trending/python?since=daily",
    "TypeScript": "https://github.com/trending/typescript?since=daily",
    "JavaScript": "https://github.com/trending/javascript?since=daily",
    "Rust": "https://github.com/trending/rust?since=daily",
    "Go": "https://github.com/trending/go?since=daily",
    "C++": "https://github.com/trending/c++?since=daily",
    "Jupyter": "https://github.com/trending/jupyter-notebook?since=daily",
}


def scrape_single_channel(item: tuple[str, str]) -> tuple[str, list[dict]]:
    """Scrape a single language channel on GitHub Trending."""
    channel_name, url = item
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    req.add_header("Accept-Language", "en-US,en;q=0.9")
    
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  ⚠️ Error scraping channel {channel_name}: {e}", file=sys.stderr)
        return channel_name, []
    
    repos = []
    article_pattern = r'<article class="Box-row">'
    articles = re.split(article_pattern, html)
    
    for art in articles[1:]:
        name_match = re.search(r'<h2[^>]*>[\s\n]*<a[^>]*href="/([^"]+)"', art)
        desc_match = re.search(r'<p class="col-9[^"]*"[^>]*>([\s\S]*?)</p>', art)
        lang_match = re.search(r'<span itemprop="programmingLanguage">([^<]+)</span>', art)
        lang_color_match = re.search(r'<span class="repo-language-color"[^>]*style="background-color:\s*([^;\"]+)', art)
        stars_match = re.search(r'href="/[^"]+/stargazers"[\s\S]*?>[\s\S]*?([\d,]+)\s*</a>', art)
        forks_match = re.search(r'href="/[^"]+/forks"[\s\S]*?>[\s\S]*?([\d,]+)\s*</a>', art)
        today_match = re.search(r'([\d,]+)\s*stars today', art)
        
        if name_match:
            repo_name = name_match.group(1).strip()
            clean_desc = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip() if desc_match else ""
            clean_desc = clean_desc.replace('\n', ' ').strip()
            
            total_stars_str = stars_match.group(1).strip() if stars_match else "0"
            today_stars_str = today_match.group(1).strip() if today_match else "0"
            forks_str = forks_match.group(1).strip() if forks_match else "0"
            language = lang_match.group(1).strip() if lang_match else ("Python" if channel_name == "Python" else "Unknown")
            language_color = lang_color_match.group(1).strip() if lang_color_match else ""
            
            repos.append({
                "name": repo_name,
                "url": f"https://github.com/{repo_name}",
                "desc": clean_desc[:500],
                "total_stars": total_stars_str,
                "today_stars": today_stars_str,
                "forks": forks_str,
                "language": language,
                "language_color": language_color,
                "channel": channel_name,
            })
    
    return channel_name, repos


def scrape_github_trending() -> list[dict]:
    """Scrape multiple GitHub Trending channels in parallel and deduplicate."""
    from concurrent.futures import ThreadPoolExecutor
    
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(scrape_single_channel, TRENDING_CHANNELS.items()))
    
    dedup_map: dict[str, dict] = {}
    for ch_name, repos in results:
        for r in repos:
            name = r["name"]
            if name not in dedup_map:
                dedup_map[name] = {
                    **r,
                    "channels": [ch_name]
                }
            else:
                existing = dedup_map[name]
                if ch_name not in existing["channels"]:
                    existing["channels"].append(ch_name)
                # Keep richer metadata if previously missing
                if existing["language"] == "Unknown" and r["language"] != "Unknown":
                    existing["language"] = r["language"]
                    existing["language_color"] = r["language_color"]
                if parse_stars(r["today_stars"]) > parse_stars(existing["today_stars"]):
                    existing["today_stars"] = r["today_stars"]
                if parse_stars(r["total_stars"]) > parse_stars(existing["total_stars"]):
                    existing["total_stars"] = r["total_stars"]

    return list(dedup_map.values())


def classify_relevance(repo: dict) -> tuple[str, list[str]]:
    """Classify how relevant a repo is for Hermes Agent evolution."""
    text = (repo["name"] + " " + repo["desc"]).lower()
    reasons = []
    
    agent_keywords = [
        "agent", "ai agent", "coding agent", "autonomous", "superagent", 
        "meta-agent", "orchestrat", "multi-agent", "mcp", "model context protocol",
        "hermes", "claude code", "cursor", "copilot", "devin"
    ]
    for kw in agent_keywords:
        if kw in text:
            reasons.append(f"🤖 {kw}")
    
    skill_keywords = [
        "skill", "planning", "self-improv", "evolv", "meta", "prompt", 
        "instruction", "reflection", "memory", "workflow", "reasoning"
    ]
    for kw in skill_keywords:
        if kw in text:
            reasons.append(f"📋 {kw}")
    
    infra_keywords = [
        "llm", "model", "inference", "training", "fine-tun", "benchmark", 
        "evaluat", "vllm", "ollama", "transformer", "embedding", "rag"
    ]
    for kw in infra_keywords:
        if kw in text:
            reasons.append(f"🔧 {kw}")
    
    tool_keywords = [
        "database", "pdf", "video", "design", "editor", "scrape", "web", 
        "terminal", "cli", "audio", "voice", "vision"
    ]
    for kw in tool_keywords:
        if kw in text:
            reasons.append(f"🛠 {kw}")
    
    if not reasons:
        return "low", ["通用開源專案"]
    
    # Deduplicate reasons while preserving order
    seen = set()
    deduped_reasons = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            deduped_reasons.append(r)
    
    has_agent = any("🤖" in r for r in deduped_reasons)
    has_skill = any("📋" in r for r in deduped_reasons)
    
    if has_agent:
        return "critical", deduped_reasons
    elif has_skill or len(deduped_reasons) >= 3:
        return "high", deduped_reasons
    elif len(deduped_reasons) >= 2:
        return "medium", deduped_reasons
    else:
        return "low", deduped_reasons


def translate_en_to_zhtw(text: str) -> str:
    """Translate English text to Traditional Chinese (zh-TW) with multi-tier fallback."""
    if not text or not text.strip():
        return ""
    text = text.strip()
    
    # 1. Google Clients5 Web API
    try:
        url = f"https://clients5.google.com/translate_a/t?client=dict-chrome-ex&sl=en&tl=zh-TW&q={urllib.parse.quote(text)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
            if isinstance(data, list) and len(data) > 0:
                if isinstance(data[0], list):
                    return "".join(data[0])
                elif isinstance(data[0], str):
                    return data[0]
    except Exception:
        pass

    # 2. MyMemory API Fallback
    try:
        url = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(text)}&langpair=en|zh-TW"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            res = json.loads(r.read().decode("utf-8"))
            translated = res.get("responseData", {}).get("translatedText")
            if translated and not translated.startswith("MYMEMORY WARNING"):
                return translated
    except Exception:
        pass
        
    return text


def parse_stars(s) -> int:
    """Parse star/fork count string to integer."""
    if not s or s == "?":
        return 0
    if isinstance(s, (int, float)):
        return int(s)
    return int(str(s).replace(",", "").strip())


# ============================================================
# STORE TO SUPABASE (WITH SMART LIFECYCLE)
# ============================================================
def store_daily_data(date_str: str, repos: list) -> int:
    """Store daily trending data with lifecycle analysis (is_new, consecutive_days, growth_rate)."""
    # Fetch historical appearance dates for all repos prior to date_str
    history_records = supabase_get(
        "github_trending_daily", 
        {"date[lt]": date_str, "select": "repo_name,date,consecutive_days", "limit": 10000}
    )
    
    historical_repos = set()
    yesterday_map = {}
    
    curr_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    yesterday_date_str = (curr_date - timedelta(days=1)).strftime("%Y-%m-%d")
    
    for h in history_records:
        r_name = h.get("repo_name")
        if r_name:
            historical_repos.add(r_name)
            if str(h.get("date")) == yesterday_date_str:
                yesterday_map[r_name] = h.get("consecutive_days") or 1

    count = 0
    for repo in repos:
        name = repo["name"]
        level, reasons = classify_relevance(repo)
        zh_desc = translate_en_to_zhtw(repo.get("desc", ""))
        repo["desc_zh"] = zh_desc
        
        total_stars = parse_stars(repo["total_stars"])
        today_stars = parse_stars(repo["today_stars"])
        
        # 1. Lifecycle: is_new (first seen in tracking history)
        is_new = name not in historical_repos
        
        # 2. Consecutive days streak
        consecutive_days = (yesterday_map.get(name, 0) + 1) if name in yesterday_map else 1
        
        # 3. Growth rate (% increase today)
        growth_rate = round((today_stars / total_stars) * 100, 2) if total_stars > 0 else 0.0
        if growth_rate > 100.0:
            growth_rate = 100.0
        
        repo["is_new"] = is_new
        repo["consecutive_days"] = consecutive_days
        repo["growth_rate"] = growth_rate
        
        data = {
            "date": date_str,
            "repo_name": name,
            "repo_url": repo["url"],
            "description": repo["desc"],
            "description_zh": zh_desc,
            "total_stars": total_stars,
            "today_stars": today_stars,
            "forks": parse_stars(repo.get("forks", 0)),
            "language": repo.get("language", "Unknown"),
            "language_color": repo.get("language_color", ""),
            "relevance_level": level,
            "relevance_tags": reasons,
            "is_new": is_new,
            "consecutive_days": consecutive_days,
            "growth_rate": growth_rate,
            "channels": repo.get("channels", ["All"]),
        }
        result = supabase_post("github_trending_daily", data)
        if result:
            count += 1
    return count


# ============================================================
# WEEKLY AGGREGATION
# ============================================================
def aggregate_weekly():
    """Aggregate daily data into weekly summary."""
    from datetime import date as date_type
    
    today = date_type.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    
    # Get all repos in this week
    repos = supabase_get("github_trending_daily", {
        "date[gte]": week_start.isoformat(),
        "date[lte]": week_end.isoformat(),
    })
    
    if not repos:
        return None
    
    # Deduplicate: group by repo_name, take highest total_stars
    repo_map = {}
    for r in repos:
        name = r["repo_name"]
        if name not in repo_map or (r.get("total_stars") or 0) > (repo_map[name].get("total_stars") or 0):
            repo_map[name] = r
    
    # Calculate averages
    weekly_data = []
    for name, r in repo_map.items():
        days_with_repo = [x for x in repos if x["repo_name"] == name]
        avg_today = sum((d.get("today_stars") or 0) for d in days_with_repo) / len(days_with_repo) if days_with_repo else 0
        peak_today = max((d.get("today_stars") or 0) for d in days_with_repo) if days_with_repo else 0
        
        weekly_data.append({
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "repo_name": r["repo_name"],
            "repo_url": r["repo_url"],
            "description": r.get("description", ""),
            "description_zh": r.get("description_zh", ""),
            "total_stars": r.get("total_stars", 0),
            "peak_today_stars": peak_today,
            "avg_daily_stars": round(avg_today, 2),
            "language": r.get("language", "Unknown"),
            "language_color": r.get("language_color", ""),
            "forks": r.get("forks", 0),
            "relevance_level": r.get("relevance_level", "low"),
            "relevance_tags": r.get("relevance_tags", []),
        })
    
    # Sort by total_stars descending
    weekly_data.sort(key=lambda x: (x["total_stars"] or 0), reverse=True)
    
    # Store to weekly table
    for wd in weekly_data:
        supabase_post("github_trending_weekly", wd)
    
    return weekly_data


# ============================================================
# MONTHLY AGGREGATION
# ============================================================
def aggregate_monthly():
    """Aggregate daily data into monthly summary."""
    from datetime import date as date_type
    
    today = date_type.today()
    month_start = today.replace(day=1)
    if today.month == 12:
        month_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    
    repos = supabase_get("github_trending_daily", {
        "date[gte]": month_start.isoformat(),
        "date[lte]": month_end.isoformat(),
    })
    
    if not repos:
        return None
    
    # Group by repo_name
    repo_map = {}
    for r in repos:
        name = r["repo_name"]
        if name not in repo_map:
            repo_map[name] = []
        repo_map[name].append(r)
    
    monthly_data = []
    for name, days in repo_map.items():
        total_stars = max((d.get("total_stars") or 0) for d in days)
        peak_today = max((d.get("today_stars") or 0) for d in days)
        avg_today = sum((d.get("today_stars") or 0) for d in days) / len(days)
        
        # Determine trend direction
        if len(days) >= 3:
            first_half = sum((d.get("today_stars") or 0) for d in days[:len(days)//2]) / (len(days)//2)
            second_half = sum((d.get("today_stars") or 0) for d in days[len(days)//2:]) / (len(days) - len(days)//2)
            if second_half > first_half * 1.2:
                trend = "rising"
            elif second_half < first_half * 0.8:
                trend = "falling"
            else:
                trend = "stable"
        else:
            trend = "stable"
        
        monthly_data.append({
            "month_start": month_start.isoformat(),
            "month_end": month_end.isoformat(),
            "repo_name": name,
            "repo_url": days[0]["repo_url"],
            "description": days[0].get("description", ""),
            "description_zh": days[0].get("description_zh", ""),
            "total_stars": total_stars,
            "peak_today_stars": peak_today,
            "total_appearances": len(days),
            "avg_daily_stars": round(avg_today, 2),
            "language": days[0].get("language", "Unknown"),
            "language_color": days[0].get("language_color", ""),
            "forks": days[0].get("forks", 0),
            "relevance_level": days[0].get("relevance_level", "low"),
            "relevance_tags": days[0].get("relevance_tags", []),
            "trend_direction": trend,
        })
    
    monthly_data.sort(key=lambda x: (x["total_stars"] or 0), reverse=True)
    
    for md in monthly_data:
        supabase_post("github_trending_monthly", md)
    
    return monthly_data


# ============================================================
# REPORT GENERATION
# ============================================================
def generate_daily_report(date_str: str, repos: list) -> str:
    """Generate the daily trending report."""
    today = datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d (%A)")
    
    # Classify all repos and ensure Chinese translations are present
    classified = []
    for repo in repos:
        level, reasons = classify_relevance(repo)
        repo["relevance"] = level
        repo["reasons"] = reasons
        repo["today_stars_num"] = parse_stars(repo["today_stars"])
        repo["total_stars_num"] = parse_stars(repo["total_stars"])
        if not repo.get("desc_zh"):
            repo["desc_zh"] = translate_en_to_zhtw(repo.get("desc", ""))
        repo["description_zh"] = repo["desc_zh"]
        classified.append(repo)
    
    report = f"# 📊 每日 GitHub 開源雷達與趨勢報告\n"
    report += f"**日期：** {today}\n"
    report += f"**來源：** GitHub Trending 多語言子榜 (Python, TS, JS, Rust, Go, C++, Jupyter)\n"
    report += f"**去重總計：** ✅ 本日監控 {len(repos)} 個不重複專案\n\n"
    
    # Section 1: Top picks
    report += "---\n\n"
    report += "## 💡 Dora 的精選推薦 (對 Hermes 自我進化最有價值)\n\n"
    
    priority = [r for r in classified if r["relevance"] in ("critical", "high")]
    priority.sort(key=lambda x: x["today_stars_num"], reverse=True)
    
    if priority:
        for i, repo in enumerate(priority[:8], 1):
            emoji = {"critical": "🔴", "high": "🟠"}.get(repo["relevance"], "⚪")
            zh_desc = repo.get("desc_zh") or repo.get("desc", "")
            new_tag = " ✨ NEW" if repo.get("is_new") else f" 🔥 連續 {repo.get('consecutive_days', 1)} 天"
            report += f"### {i}. {emoji} [{repo['name']}]({repo['url']}){new_tag}\n"
            report += f"- **Stars:** {repo['total_stars']} (今日 +{repo['today_stars']})\n"
            report += f"- **分類:** {repo['relevance'].upper()} | **語言:** {repo.get('language', 'Unknown')}\n"
            report += f"- **簡介:** {zh_desc}\n\n"
    else:
        report += "_沒有高相關性專案_\n\n"
    
    # Section 2: Newly Emerging (First Seen)
    new_repos = [r for r in classified if r.get("is_new")]
    new_repos.sort(key=lambda x: x["today_stars_num"], reverse=True)
    if new_repos:
        report += "---\n\n"
        report += f"## ✨ 今日首發新面孔 (首次上榜，共 {len(new_repos)} 個)\n\n"
        report += "| # | 新進專案 | 語言 | ⭐ Total | 今日新增 | 相關性 |\n"
        report += "|---|----------|------|----------|----------|--------|\n"
        relevance_icons = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}
        for i, repo in enumerate(new_repos[:10], 1):
            icon = relevance_icons.get(repo["relevance"], "⚪")
            report += f"| {i} | [{repo['name']}]({repo['url']}) | {repo.get('language', '-')} | {repo['total_stars']} | +{repo['today_stars']} | {icon} {repo['relevance']} |\n"
        report += "\n"

    # Section 3: All trending ranking
    report += "---\n\n"
    report += "## 📈 今日 GitHub Trending 全覽 TOP 20\n\n"
    report += "| # | 專案 | 語言 | ⭐ Total | 今日新增 | 相關性 |\n"
    report += "|---|------|------|----------|----------|--------|\n"
    
    classified.sort(key=lambda x: x["today_stars_num"], reverse=True)
    relevance_icons = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}
    
    for i, repo in enumerate(classified[:20], 1):
        icon = relevance_icons.get(repo["relevance"], "⚪")
        report += f"| {i} | [{repo['name']}]({repo['url']}) | {repo.get('language', '-')} | {repo['total_stars']} | +{repo['today_stars']} | {icon} {repo['relevance']} |\n"
    
    report += "\n---\n\n"
    report += "## 🔍 Dora 的觀察與建議\n\n"
    
    agent_count = sum(1 for r in classified if r["relevance"] == "critical")
    skill_count = sum(1 for r in classified if "skill" in " ".join(r["reasons"]).lower())
    new_count = len(new_repos)
    
    report += f"### 趨勢分析\n\n"
    report += f"- **🤖 Agent 熱潮持續升溫：** 今日 {agent_count} 個專案直接與 AI Agent 相關\n"
    report += f"- **✨ 新血湧入：** 今日共有 {new_count} 個專案為首次進入觀測站雷達\n"
    if skill_count:
        report += f"- **📋 Skill 機制成為共識：** {skill_count} 個專案聚焦於 Skills/能力模組化\n"
    
    report += "\n### 值得深入研究的 TOP 3\n\n"
    top3 = [r for r in classified if r["relevance"] in ("critical", "high")][:3]
    for i, repo in enumerate(top3, 1):
        zh_desc = repo.get("desc_zh") or repo.get("desc", "")
        report += f"{i}. **[{repo['name']}]({repo['url']})** — {zh_desc}\n"
    
    report += "\n---\n\n"
    report += f"*報告由 Hermes Agent Dora 自動生成 | 下次執行: 明日同一時間*\n"
    
    # Also save structured insight to local JSON for backend API
    try:
        insight_file = Path(__file__).parent / "latest_insight.json"
        insight_data = {
            "date": date_str,
            "updated_at": datetime.now().isoformat(),
            "top_picks": priority[:8],
            "new_repos": new_repos[:10],
            "trends": {
                "agent_count": agent_count,
                "skill_count": skill_count,
                "new_count": new_count,
            },
            "top3": top3,
            "markdown_report": report,
            "total_repos": len(repos),
        }
        with open(insight_file, "w", encoding="utf-8") as f:
            json.dump(insight_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  ⚠️  Failed to save latest_insight.json: {e}", file=sys.stderr)
    
    return report


# ============================================================
# MAIN
# ============================================================
def run_full_cycle():
    """Run full scraping, storing, report generation and aggregations."""
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"🔄 GitHub Trending 分析開始 ({today})...")
    
    # Fetch trending
    repos = scrape_github_trending()
    
    if isinstance(repos, dict) and "error" in repos:
        print(f"⚠️ 抓取失敗: {repos['error']}")
        return {"status": "error", "error": repos["error"]}
    
    if not repos:
        print("_⚠️ 未找到熱門專案_")
        return {"status": "empty", "records": 0}
    
    print(f"✅ 抓取到 {len(repos)} 個熱門專案")
    
    # Store to Supabase
    print("💾 儲存至 Supabase...")
    count = store_daily_data(today, repos)
    print(f"✅ 已儲存 {count} 筆資料")
    
    # Generate report
    report = generate_daily_report(today, repos)
    
    # Aggregate weekly
    print("\n📅 計算每週統計...")
    weekly = aggregate_weekly()
    if weekly:
        print(f"✅ 每週統計完成：{len(weekly)} 個去重專案")
    
    # Aggregate monthly
    print("📆 計算每月統計...")
    monthly = aggregate_monthly()
    if monthly:
        print(f"✅ 每月統計完成：{len(monthly)} 個去重專案")
        
    return {
        "status": "ok",
        "date": today,
        "records": count,
        "weekly_records": len(weekly) if weekly else 0,
        "monthly_records": len(monthly) if monthly else 0,
        "report": report
    }


def main():
    """Main entry point."""
    res = run_full_cycle()
    if res.get("report"):
        print(res["report"])


if __name__ == "__main__":
    main()
