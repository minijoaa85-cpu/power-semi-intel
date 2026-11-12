#!/usr/bin/env python3
"""
주간 전력반도체 기술 동향 & 최신 논문 자동 수집 파이프라인 (v2.5)
- arXiv API: GaN, SiC, Superjunction MOSFET, Shielded Gate Trench 최신 논문 수집
- RSS Feeds: 전력반도체 산업 뉴스 및 선진사 동향 수집
- Gemini API (선택): GitHub Secrets에 GEMINI_API_KEY 등록 시 영문 논문/뉴스를 한국어 실무 언어로 자동 요약 및 BV/Ron,sp/FOM 추출
"""

import json
import os
import re
import datetime
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import feedparser
except ImportError:
    feedparser = None

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "dashboard_data.json"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

ARXIV_QUERIES = [
    '("GaN" AND ("power" OR "HEMT" OR "GaN-on-Si"))',
    '("SiC" AND ("MOSFET" OR "trench"))',
    '("superjunction" OR "super-junction" OR "shielded gate trench" OR "split-gate trench")'
]

RSS_FEEDS = [
    ("Power Electronics News", "https://www.powerelectronicsnews.com/feed/"),
    ("Compound Semiconductor", "https://compoundsemiconductor.net/rss/news"),
]

KEYWORDS_MAP = {
    "GaN": ["gan", "gallium nitride", "hemt", "p-gan", "gan-on-si", "coolgan", "bds"],
    "SiC": ["sic", "silicon carbide", "4h-sic", "trench mosfet", "elitesic"],
    "SJ-MOS": ["superjunction", "super junction", "super-junction", "sj mosfet", "mdmesh", "coolmos"],
    "SGT": ["shielded gate", "split-gate", "split gate", "sgt", "ud sgt"]
}


def get_iso_week():
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    year, week, _ = now.isocalendar()
    code = f"{year}-W{week:02d}"
    month = now.month
    week_of_month = (now.day - 1) // 7 + 1
    label = f"{year}년 {month}월 {week_of_month}주차"
    return code, label, now.strftime("%Y-%m-%d")


def classify_device(text: str) -> str:
    lower = text.lower()
    for device, kws in KEYWORDS_MAP.items():
        if any(kw in lower for kw in kws):
            return device
    return "GaN"


def extract_metrics(text: str):
    bv_match = re.search(r"(\d{2,4}(?:\.\d+)?)\s*(?:V|kV)\b", text, re.IGNORECASE)
    ron_match = re.search(r"(\d+(?:\.\d+)?)\s*m[ΩO]·?cm", text, re.IGNORECASE)
    bv = bv_match.group(0) if bv_match else "-"
    ron_sp = ron_match.group(1) if ron_match else "-"
    return bv, ron_sp


def call_gemini_json(prompt: str):
    if not GEMINI_API_KEY:
        return None
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            res = json.loads(resp.read().decode("utf-8"))
        text = res["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except Exception as e:
        print(f"[WARN] Gemini API summarization fallback: {e}")
        return None


def summarize_paper_ko(title: str, summary: str, default_device: str, default_bv: str, default_ron: str):
    prompt = (
        "You are a Power Semiconductor Process Architecture expert. "
        "Extract JSON with keys: device (one of GaN, SiC, SJ-MOS, SGT), bv (e.g. '650 V' or '-'), "
        "ron_sp (numeric string in mΩ·cm² or '-'), fom (short metric string), "
        "arch_ko (2-sentence Korean summary focusing on process architecture innovation), "
        "reliability (short Korean phrase or '-').\n"
        f"Title: {title}\nAbstract: {summary}"
    )
    parsed = call_gemini_json(prompt)
    if isinstance(parsed, dict) and parsed.get("arch_ko"):
        return (
            parsed.get("device", default_device),
            parsed.get("bv", default_bv),
            parsed.get("ron_sp", default_ron),
            parsed.get("fom", "AI 추출 요약"),
            parsed.get("arch_ko"),
            parsed.get("reliability", "-"),
        )
    return default_device, default_bv, default_ron, "자동 수집(요약 참조)", summary[:220] + ("..." if len(summary) > 220 else ""), "-"


def summarize_news_ko(title: str, summary: str, default_device: str):
    prompt = (
        "You are a Power Semiconductor Process Architecture expert. "
        "Translate/summarize into Korean JSON with keys: tag (GaN, SiC, SJ-MOS, or SGT), "
        "title_ko (concise Korean headline), desc_ko (2-sentence Korean summary), "
        "impact_ko (1-sentence Process Architecture implication in Korean).\n"
        f"Title: {title}\nSummary: {summary}"
    )
    parsed = call_gemini_json(prompt)
    if isinstance(parsed, dict) and parsed.get("title_ko"):
        return (
            parsed.get("tag", default_device),
            parsed.get("title_ko"),
            parsed.get("desc_ko", summary[:220]),
            parsed.get("impact_ko", "공정·소자 아키텍처 동향 트래킹"),
        )
    return default_device, title, summary[:240] + ("..." if len(summary) > 240 else ""), "공정·소자 아키텍처 동향 트래킹 필요"


def fetch_arxiv_papers(max_per_query=3):
    results = []
    for q in ARXIV_QUERIES:
        url = (
            "http://export.arxiv.org/api/query?"
            f"search_query=all:{urllib.parse.quote(q)}&start=0&max_results={max_per_query}"
            "&sortBy=submittedDate&sortOrder=descending"
        )
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                title = re.sub(r"\s+", " ", entry.find("atom:title", ns).text or "").strip()
                summary = re.sub(r"\s+", " ", entry.find("atom:summary", ns).text or "").strip()
                link = entry.find("atom:id", ns).text or ""
                authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)][:3]
                author_str = ", ".join(authors) + (" et al." if len(authors) == 3 else "")
                dev0 = classify_device(title + " " + summary)
                bv0, ron0 = extract_metrics(title + " " + summary)
                dev, bv, ron, fom, arch_ko, rel = summarize_paper_ko(title, summary, dev0, bv0, ron0)
                results.append({
                    "device": dev,
                    "conference": "arXiv Preprint",
                    "title": title,
                    "authors": author_str or "arXiv",
                    "bv": bv,
                    "ron_sp": ron,
                    "fom": fom,
                    "arch": arch_ko,
                    "reliability": rel,
                    "link": link
                })
        except Exception as e:
            print(f"[WARN] arXiv fetch failed for {q}: {e}")
    return results


def fetch_rss_news(max_per_feed=4):
    if feedparser is None:
        print("[WARN] feedparser not installed, skipping RSS.")
        return []
    results = []
    all_kws = [kw for kws in KEYWORDS_MAP.values() for kw in kws] + [
        "infineon", "onsemi", "stmicro", "rohm", "navitas", "innoscience", "wolfspeed", "power"
    ]
    for source_name, feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            count = 0
            for entry in feed.entries:
                title = entry.get("title", "").strip()
                summary = re.sub(r"<[^>]+>", "", entry.get("summary", "")).strip()
                combined = (title + " " + summary).lower()
                if any(kw in combined for kw in all_kws):
                    dev0 = classify_device(combined)
                    tag, title_ko, desc_ko, impact_ko = summarize_news_ko(title, summary, dev0)
                    results.append({
                        "company": source_name,
                        "tag": tag,
                        "title": title_ko,
                        "app": "전력변환 · 전장 · AI 서버",
                        "desc": desc_ko,
                        "impact": impact_ko,
                        "url": entry.get("link", "")
                    })
                    count += 1
                if count >= max_per_feed:
                    break
        except Exception as e:
            print(f"[WARN] RSS fetch failed for {source_name}: {e}")
    return results


def main():
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Missing data file: {DATA_PATH}")

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    week_code, week_label, today_str = get_iso_week()
    if not any(w["code"] == week_code for w in data.get("weeks", [])):
        data["weeks"].insert(0, {"code": week_code, "label": week_label})
    data["currentWeek"] = week_code
    data["lastUpdated"] = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()

    existing_news_titles = {n["title"] for n in data.get("news", [])}
    existing_paper_titles = {p["title"] for p in data.get("papers", [])}

    new_news = fetch_rss_news()
    added_news = 0
    for item in new_news:
        if item["title"] not in existing_news_titles:
            item["id"] = int(datetime.datetime.now().timestamp() * 1000) + added_news
            item["week"] = week_code
            item["date"] = today_str
            data["news"].insert(0, item)
            existing_news_titles.add(item["title"])
            added_news += 1

    new_papers = fetch_arxiv_papers()
    added_papers = 0
    for item in new_papers:
        if item["title"] not in existing_paper_titles:
            item["id"] = f"P_{week_code}_{added_papers + 1}"
            item["week"] = week_code
            data["papers"].insert(0, item)
            existing_paper_titles.add(item["title"])
            added_papers += 1

    if week_code not in data.get("weeklyThemes", {}):
        ai_mode = "Gemini AI 한국어 요약" if GEMINI_API_KEY else "기본 키워드 파서"
        data.setdefault("weeklyThemes", {})[week_code] = [
            {
                "icon": "fa-robot",
                "color": "text-blue-400",
                "title": f"1. {week_label} 자동 수집 완료 ({ai_mode})",
                "desc": f"신규 선진사/산업 뉴스 {added_news}건과 arXiv 최신 논문 {added_papers}건이 자동으로 아카이브되었습니다."
            },
            {
                "icon": "fa-microchip",
                "color": "text-indigo-400",
                "title": "2. 소자별 핵심 검토 포인트",
                "desc": "선진사 동향 및 논문 탭에서 이번 주 태그(GaN/SiC/SJ-MOS/SGT)별 신규 항목을 필터링해 팀 미팅 안건으로 활용하세요."
            },
            {
                "icon": "fa-chart-line",
                "color": "text-emerald-400",
                "title": "3. 재무·시장 지표 점검",
                "desc": "분기 실적 발표 시즌에는 data/dashboard_data.json의 financials 및 quarterlySeries 항목을 함께 업데이트할 수 있습니다."
            }
        ]

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[OK] Updated {week_code} (Gemini={'ON' if GEMINI_API_KEY else 'OFF'}): +{added_news} news, +{added_papers} papers.")


if __name__ == "__main__":
    main()
