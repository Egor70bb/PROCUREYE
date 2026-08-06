"""PROCUREYE Release 42.0 — market_movers.py."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
import html
import re

import feedparser
import pandas as pd
import requests
import streamlit as st


NEWS_FEEDS = [
    (
        "Oil Market",
        "https://news.google.com/rss/search?q="
        + quote_plus(
            '("crude oil" OR Brent OR WTI) '
            '(Reuters OR Bloomberg OR CNBC OR FT) when:2d'
        )
        + "&hl=en-US&gl=US&ceid=US:en"
    ),
    (
        "OPEC",
        "https://news.google.com/rss/search?q="
        + quote_plus(
            '(OPEC OR OPEC+) '
            '("production cut" OR output OR quota) when:3d'
        )
        + "&hl=en-US&gl=US&ceid=US:en"
    ),
    (
        "Inventories",
        "https://news.google.com/rss/search?q="
        + quote_plus(
            '("crude inventories" OR "oil inventories" OR EIA OR API) '
            'when:3d'
        )
        + "&hl=en-US&gl=US&ceid=US:en"
    ),
    (
        "Geopolitics",
        "https://news.google.com/rss/search?q="
        + quote_plus(
            '(Iran OR Russia OR Ukraine OR "Middle East" OR sanctions) '
            '("oil supply" OR crude OR tanker OR pipeline) when:3d'
        )
        + "&hl=en-US&gl=US&ceid=US:en"
    ),
    (
        "Demand",
        "https://news.google.com/rss/search?q="
        + quote_plus(
            '("oil demand" OR "China demand" OR refinery OR recession) '
            'when:3d'
        )
        + "&hl=en-US&gl=US&ceid=US:en"
    ),
    (
        "Macro",
        "https://news.google.com/rss/search?q="
        + quote_plus(
            '("US dollar" OR Federal Reserve OR interest rates) '
            '(oil OR crude) when:3d'
        )
        + "&hl=en-US&gl=US&ceid=US:en"
    ),
    (
        "EIA",
        "https://www.eia.gov/rss/todayinenergy.xml"
    ),
]


SOURCE_WEIGHTS = {
    "reuters": 24,
    "bloomberg": 22,
    "eia": 24,
    "opec": 22,
    "iea": 22,
    "financial times": 19,
    "wall street journal": 18,
    "associated press": 15,
    "cnbc": 14,
    "marketwatch": 11,
    "oilprice": 11,
}


DRIVER_RULES = {
    "OPEC / PRODUCTION": [
        "opec",
        "production cut",
        "output cut",
        "quota",
        "barrels per day",
        "production increase",
        "output increase",
    ],
    "US INVENTORIES": [
        "inventory",
        "inventories",
        "stockpile",
        "stockpiles",
        "eia",
        "api",
        "crude stocks",
    ],
    "GEOPOLITICS": [
        "iran",
        "russia",
        "ukraine",
        "middle east",
        "sanction",
        "attack",
        "war",
        "tanker",
        "red sea",
        "strait of hormuz",
    ],
    "GLOBAL DEMAND": [
        "demand",
        "china",
        "recession",
        "economic growth",
        "consumption",
        "refinery runs",
    ],
    "DOLLAR / FED": [
        "dollar",
        "federal reserve",
        "fed",
        "interest rate",
        "rates",
        "inflation",
    ],
    "SUPPLY DISRUPTION": [
        "pipeline",
        "outage",
        "shutdown",
        "export halt",
        "supply disruption",
        "force majeure",
        "port closure",
    ],
}


BULLISH_RULES = {
    "production cut": 28,
    "output cut": 28,
    "deeper cuts": 30,
    "inventory draw": 26,
    "inventories fall": 25,
    "stockpiles fall": 24,
    "supply disruption": 27,
    "pipeline outage": 28,
    "export halt": 27,
    "force majeure": 27,
    "sanctions tighten": 22,
    "attack": 17,
    "escalation": 18,
    "demand rises": 22,
    "demand growth": 18,
    "refinery runs increase": 16,
    "dollar falls": 14,
    "rate cut": 12,
}


BEARISH_RULES = {
    "production increase": 27,
    "output increase": 27,
    "raises production": 27,
    "inventory build": 26,
    "inventories rise": 25,
    "stockpiles rise": 24,
    "oversupply": 26,
    "weak demand": 24,
    "demand falls": 25,
    "demand slowdown": 22,
    "recession": 17,
    "exports resume": 21,
    "pipeline resumes": 20,
    "ceasefire": 12,
    "dollar rises": 14,
    "rate hike": 13,
}


OIL_RELEVANCE = {
    "crude oil": 20,
    "brent": 22,
    "wti": 22,
    "oil price": 15,
    "opec": 20,
    "eia": 15,
    "api": 13,
    "barrel": 10,
    "production": 11,
    "supply": 10,
    "demand": 10,
    "inventory": 14,
    "inventories": 14,
    "refinery": 9,
    "pipeline": 10,
    "tanker": 9,
    "sanction": 10,
}


def _plain_text(value):
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _published_utc(entry):
    raw = (
        entry.get("published")
        or entry.get("updated")
        or entry.get("created")
        or ""
    )

    try:
        value = parsedate_to_datetime(raw)

        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    except Exception:
        return datetime.now(timezone.utc)


def _extract_source(entry, default_source):
    source = entry.get("source", {})

    if isinstance(source, dict):
        title = _plain_text(source.get("title"))

        if title:
            return title

    title = _plain_text(entry.get("title"))

    if " - " in title:
        possible_source = title.rsplit(" - ", 1)[-1].strip()

        if 2 <= len(possible_source) <= 60:
            return possible_source

    return default_source


def _clean_title(entry_title, source):
    title = _plain_text(entry_title)
    suffix = f" - {source}"

    if title.lower().endswith(suffix.lower()):
        title = title[:-len(suffix)].strip()

    return title


def _driver(text):
    scores = {}

    for driver_name, terms in DRIVER_RULES.items():
        scores[driver_name] = sum(
            1 for term in terms if term in text
        )

    best_driver = max(scores, key=scores.get)

    if scores[best_driver] == 0:
        return "OIL MARKET"

    return best_driver


def _term_score(text, rules):
    return sum(
        weight
        for phrase, weight in rules.items()
        if phrase in text
    )


def _source_score(source):
    source_lower = source.lower()

    return max(
        [
            weight
            for name, weight in SOURCE_WEIGHTS.items()
            if name in source_lower
        ]
        or [5]
    )


def _build_reason(driver, bias):
    explanations = {
        "OPEC / PRODUCTION": {
            "BULLISH": "Potential reduction in global crude supply.",
            "BEARISH": "Potential increase in global crude supply.",
            "NEUTRAL": "OPEC or production development without a clear direction.",
        },
        "US INVENTORIES": {
            "BULLISH": "Lower inventories may indicate tighter US supply.",
            "BEARISH": "Higher inventories may indicate excess US supply.",
            "NEUTRAL": "Inventory information without a clear directional surprise.",
        },
        "GEOPOLITICS": {
            "BULLISH": "Geopolitical risk may threaten production or transport.",
            "BEARISH": "Lower geopolitical tension may reduce the supply-risk premium.",
            "NEUTRAL": "Geopolitical development with uncertain oil-market consequences.",
        },
        "GLOBAL DEMAND": {
            "BULLISH": "Stronger expected consumption may support oil prices.",
            "BEARISH": "Weaker expected consumption may pressure oil prices.",
            "NEUTRAL": "Demand outlook remains mixed.",
        },
        "DOLLAR / FED": {
            "BULLISH": "A weaker dollar or easier policy may support commodity prices.",
            "BEARISH": "A stronger dollar or tighter policy may pressure oil prices.",
            "NEUTRAL": "Macro implications for oil remain unclear.",
        },
        "SUPPLY DISRUPTION": {
            "BULLISH": "Operational disruption may reduce available crude supply.",
            "BEARISH": "Restored operations may increase available crude supply.",
            "NEUTRAL": "Operational event with uncertain net supply impact.",
        },
        "OIL MARKET": {
            "BULLISH": "The event contains evidence supportive of oil prices.",
            "BEARISH": "The event contains evidence negative for oil prices.",
            "NEUTRAL": "The event is relevant but lacks a clear directional signal.",
        },
    }

    return explanations.get(
        driver,
        explanations["OIL MARKET"]
    ).get(
        bias,
        explanations["OIL MARKET"]["NEUTRAL"]
    )


def _analyse(title, summary, source, published):
    text = f"{title} {summary}".lower()

    relevance = _term_score(text, OIL_RELEVANCE)
    bullish_score = _term_score(text, BULLISH_RULES)
    bearish_score = _term_score(text, BEARISH_RULES)
    source_quality = _source_score(source)

    age_hours = max(
        0,
        (
            datetime.now(timezone.utc) - published
        ).total_seconds() / 3600
    )

    freshness = max(0, 24 - age_hours / 2)
    driver = _driver(text)

    directional_difference = bullish_score - bearish_score

    if directional_difference >= 6:
        bias = "BULLISH"
    elif directional_difference <= -6:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    raw_importance = (
        relevance
        + max(bullish_score, bearish_score)
        + source_quality
        + freshness
    )

    importance = round(
        min(100, max(0, raw_importance)),
        1
    )

    if bias == "BULLISH":
        impact = importance
    elif bias == "BEARISH":
        impact = -importance
    else:
        impact = 0.0

    confidence = int(
        min(
            96,
            max(
                25,
                38
                + relevance * 0.45
                + abs(directional_difference) * 0.8
                + source_quality * 0.45
            )
        )
    )

    reason = _build_reason(driver, bias)

    return {
        "Driver": driver,
        "Bias": bias,
        "Impact": round(impact, 1),
        "Importance": importance,
        "Confidence": confidence,
        "Reason": reason,
        "AgeHours": round(age_hours, 1),
    }


def _dedup_key(title):
    words = re.sub(
        r"[^a-z0-9 ]",
        " ",
        title.lower()
    ).split()

    stop_words = {
        "the", "a", "an", "to", "of", "for",
        "and", "in", "on", "as", "with", "at"
    }

    useful = [
        word for word in words
        if word not in stop_words
    ]

    return " ".join(useful[:12])


@st.cache_data(ttl=900, show_spinner=False)
def get_market_movers(limit=3):
    rows = []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/124 Safari/537.36"
        ),
        "Accept": (
            "application/rss+xml, application/xml, "
            "text/xml, */*"
        ),
    }

    for feed_name, feed_url in NEWS_FEEDS:
        try:
            response = requests.get(
                feed_url,
                headers=headers,
                timeout=15
            )
            response.raise_for_status()

            parsed = feedparser.parse(response.content)

        except Exception:
            continue

        for entry in parsed.entries[:30]:
            source = _extract_source(entry, feed_name)
            title = _clean_title(
                entry.get("title", ""),
                source
            )
            summary = _plain_text(
                entry.get("summary", "")
            )
            published = _published_utc(entry)
            url = str(entry.get("link", "")).strip()

            if not title or not url:
                continue

            analysis = _analyse(
                title=title,
                summary=summary,
                source=source,
                published=published
            )

            if analysis["Importance"] < 25:
                continue

            rows.append({
                "Title": title,
                "Source": source,
                "PublishedUTC": published,
                "Published": published.strftime(
                    "%d %b %Y · %H:%M UTC"
                ),
                "Driver": analysis["Driver"],
                "Bias": analysis["Bias"],
                "Impact": analysis["Impact"],
                "Importance": analysis["Importance"],
                "Confidence": analysis["Confidence"],
                "Reason": analysis["Reason"],
                "URL": url,
                "AgeHours": analysis["AgeHours"],
                "Dedup": _dedup_key(title),
            })

    if not rows:
        return pd.DataFrame([{
            "Title": "Live market news temporarily unavailable",
            "Source": "PROCUREYE",
            "PublishedUTC": datetime.now(timezone.utc),
            "Published": datetime.now(timezone.utc).strftime(
                "%d %b %Y · %H:%M UTC"
            ),
            "Driver": "DATA AVAILABILITY",
            "Bias": "NEUTRAL",
            "Impact": 0.0,
            "Importance": 0.0,
            "Confidence": 0,
            "Reason": (
                "No live RSS source responded successfully. "
                "The signal should use reduced confidence."
            ),
            "URL": "",
            "AgeHours": 0.0,
        }])

    frame = pd.DataFrame(rows)

    frame = (
        frame.sort_values(
            [
                "Importance",
                "Confidence",
                "PublishedUTC"
            ],
            ascending=[False, False, False]
        )
        .drop_duplicates("Dedup")
    )

    selected = []
    used_drivers = set()

    for _, row in frame.iterrows():
        driver = row["Driver"]

        if driver not in used_drivers or len(selected) >= limit:
            selected.append(row)
            used_drivers.add(driver)

        if len(selected) == limit:
            break

    if len(selected) < limit:
        selected_titles = {
            item["Title"] for item in selected
        }

        for _, row in frame.iterrows():
            if row["Title"] in selected_titles:
                continue

            selected.append(row)

            if len(selected) == limit:
                break

    result = pd.DataFrame(selected).drop(
        columns=["Dedup"],
        errors="ignore"
    )

    return result.reset_index(drop=True)
