
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import feedparser
import pandas as pd
import requests
import streamlit as st


FEEDS = [
    (
        "Oil Market",
        "https://news.google.com/rss/search?q="
        + quote_plus("crude oil Brent WTI when:2d")
        + "&hl=en-US&gl=US&ceid=US:en"
    ),
    (
        "OPEC",
        "https://news.google.com/rss/search?q="
        + quote_plus("OPEC oil production cuts when:3d")
        + "&hl=en-US&gl=US&ceid=US:en"
    ),
    (
        "Inventories",
        "https://news.google.com/rss/search?q="
        + quote_plus("EIA API US crude oil inventories when:3d")
        + "&hl=en-US&gl=US&ceid=US:en"
    ),
    (
        "Geopolitics",
        "https://news.google.com/rss/search?q="
        + quote_plus("Middle East oil supply sanctions Iran Russia when:3d")
        + "&hl=en-US&gl=US&ceid=US:en"
    ),
    (
        "EIA",
        "https://www.eia.gov/rss/todayinenergy.xml"
    ),
]


OIL_TERMS = {
    "oil": 12, "crude": 14, "brent": 18, "wti": 18,
    "opec": 18, "eia": 12, "api": 10, "barrel": 9,
    "inventory": 13, "inventories": 13, "refinery": 8,
    "production": 10, "supply": 9, "demand": 9,
    "sanction": 10, "pipeline": 8, "tanker": 8,
    "middle east": 12, "iran": 10, "russia": 9
}

BULLISH_TERMS = {
    "production cut": 20, "output cut": 20, "supply disruption": 18,
    "inventory draw": 18, "inventories fall": 17,
    "sanctions": 11, "attack": 13, "escalation": 12,
    "demand rises": 13, "demand growth": 11,
    "pipeline outage": 18, "export halt": 18
}

BEARISH_TERMS = {
    "production increase": 18, "output increase": 18,
    "inventory build": 18, "inventories rise": 17,
    "demand falls": 15, "demand slowdown": 14,
    "ceasefire": 9, "oversupply": 17,
    "weak demand": 15, "recession": 11,
    "exports resume": 14, "supply increases": 14
}

SOURCE_BONUS = {
    "reuters": 18, "bloomberg": 17, "eia": 18,
    "opec": 17, "iea": 17, "financial times": 14,
    "wall street journal": 14, "cnbc": 11,
    "associated press": 10
}


def _published(entry):
    raw = entry.get("published") or entry.get("updated") or ""

    try:
        value = parsedate_to_datetime(raw)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _source(entry, feed_name):
    source = entry.get("source", {})
    if isinstance(source, dict) and source.get("title"):
        return str(source["title"])

    title = str(entry.get("title", ""))
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()

    return feed_name


def _clean_title(title, source):
    title = str(title).strip()
    suffix = f" - {source}"

    if title.lower().endswith(suffix.lower()):
        title = title[:-len(suffix)].strip()

    return title


def _score(title, summary, source, published):
    text = f"{title} {summary}".lower()

    relevance = sum(
        weight for term, weight in OIL_TERMS.items()
        if term in text
    )

    bullish = sum(
        weight for term, weight in BULLISH_TERMS.items()
        if term in text
    )

    bearish = sum(
        weight for term, weight in BEARISH_TERMS.items()
        if term in text
    )

    source_score = sum(
        weight for term, weight in SOURCE_BONUS.items()
        if term in source.lower()
    )

    age_hours = max(
        0,
        (datetime.now(timezone.utc) - published).total_seconds() / 3600
    )

    freshness = max(0, 20 - age_hours / 3)
    importance = min(100, relevance + max(bullish, bearish) + source_score + freshness)

    if bullish > bearish:
        bias = "BULLISH"
        signed_impact = round(importance, 1)
    elif bearish > bullish:
        bias = "BEARISH"
        signed_impact = round(-importance, 1)
    else:
        bias = "NEUTRAL"
        signed_impact = 0.0

    confidence = min(
        95,
        int(45 + relevance / 2 + abs(bullish - bearish) + source_score / 2)
    )

    return importance, signed_impact, bias, confidence


@st.cache_data(ttl=900, show_spinner=False)
def get_market_movers(limit=3):
    rows = []
    headers = {"User-Agent": "Mozilla/5.0 PROCUREYE/39.4"}

    for feed_name, url in FEEDS:
        try:
            response = requests.get(url, headers=headers, timeout=12)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
        except Exception:
            continue

        for entry in feed.entries[:25]:
            source = _source(entry, feed_name)
            title = _clean_title(entry.get("title", ""), source)
            summary = str(entry.get("summary", ""))
            published = _published(entry)
            link = str(entry.get("link", "")).strip()

            if not title or not link:
                continue

            importance, impact, bias, confidence = _score(
                title, summary, source, published
            )

            if importance < 18:
                continue

            rows.append({
                "Title": title,
                "Source": source,
                "PublishedUTC": published,
                "Published": published.strftime("%d %b %Y · %H:%M UTC"),
                "Bias": bias,
                "Impact": impact,
                "Importance": round(importance, 1),
                "Confidence": confidence,
                "URL": link
            })

    if not rows:
        return pd.DataFrame([{
            "Title": "Live market news temporarily unavailable",
            "Source": "PROCUREYE",
            "PublishedUTC": datetime.now(timezone.utc),
            "Published": datetime.now(timezone.utc).strftime(
                "%d %b %Y · %H:%M UTC"
            ),
            "Bias": "NEUTRAL",
            "Impact": 0.0,
            "Importance": 0.0,
            "Confidence": 0,
            "URL": ""
        }])

    frame = pd.DataFrame(rows)
    frame["Dedup"] = (
        frame["Title"]
        .str.lower()
        .str.replace(r"[^a-z0-9 ]", "", regex=True)
        .str.split()
        .str[:10]
        .str.join(" ")
    )

    frame = (
        frame.sort_values(
            ["Importance", "PublishedUTC"],
            ascending=[False, False]
        )
        .drop_duplicates("Dedup")
        .head(limit)
        .drop(columns=["Dedup"])
        .reset_index(drop=True)
    )

    return frame
