# -*- coding: utf-8 -*-
# PROCUREYE RELEASE 40.3 — COMPACT DELTA MONITOR

# ===== EMBEDDED MODULE: professional_chart.py =====

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def render_professional_chart(df, title, symbol):
    if df is None or df.empty:
        st.warning(f"{title}: dati non disponibili.")
        return

    data = df.copy()
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data["Close"] = pd.to_numeric(data["Close"], errors="coerce")
    data = data.dropna(subset=["Date", "Close"]).sort_values("Date")

    if data.empty:
        st.warning(f"{title}: dati non validi.")
        return

    data["MA20"] = data["Close"].rolling(20).mean()
    data["MA50"] = data["Close"].rolling(50).mean()

    last_price = float(data["Close"].iloc[-1])
    period_high = float(data["Close"].max())
    period_low = float(data["Close"].min())

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=data["Date"],
        y=data["Close"],
        mode="lines",
        name=symbol,
        line=dict(width=2.5),
        hovertemplate="%{x|%d %b %Y}<br>Close: $%{y:.2f}<extra></extra>"
    ))

    fig.add_trace(go.Scatter(
        x=data["Date"],
        y=data["MA20"],
        mode="lines",
        name="MA 20",
        line=dict(width=1.3, dash="dot"),
        hovertemplate="MA20: $%{y:.2f}<extra></extra>"
    ))

    fig.add_trace(go.Scatter(
        x=data["Date"],
        y=data["MA50"],
        mode="lines",
        name="MA 50",
        line=dict(width=1.3, dash="dash"),
        hovertemplate="MA50: $%{y:.2f}<extra></extra>"
    ))

    fig.add_hline(
        y=last_price,
        line_width=1,
        line_dash="dot",
        annotation_text=f"Last ${last_price:.2f}",
        annotation_position="top right"
    )

    fig.update_layout(
        title=dict(
            text=(
                f"{title}"
                f"<br><sup>High ${period_high:.2f} · "
                f"Low ${period_low:.2f} · Last ${last_price:.2f}</sup>"
            ),
            x=0.02
        ),
        height=470,
        margin=dict(l=20, r=20, t=85, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#dceaf1"),
        hovermode="x unified",
        dragmode="zoom",
        legend=dict(
            orientation="h",
            y=1.03,
            x=1,
            xanchor="right"
        ),
        xaxis=dict(
            gridcolor="rgba(140,180,205,.10)",
            showspikes=True,
            spikemode="across",
            spikesnap="cursor",
            spikedash="dot",
            rangeselector=dict(
                buttons=[
                    dict(count=1, label="1M", step="month", stepmode="backward"),
                    dict(count=3, label="3M", step="month", stepmode="backward"),
                    dict(count=6, label="6M", step="month", stepmode="backward"),
                    dict(count=1, label="YTD", step="year", stepmode="todate"),
                    dict(count=1, label="1Y", step="year", stepmode="backward"),
                    dict(label="ALL", step="all")
                ]
            )
        ),
        yaxis=dict(
            title="USD per barrel",
            gridcolor="rgba(140,180,205,.10)",
            showspikes=True,
            spikedash="dot",
            fixedrange=False
        )
    )

    st.plotly_chart(
        fig,
        width="stretch",
        config={
            "displaylogo": False,
            "scrollZoom": True,
            "responsive": True,
            "modeBarButtonsToRemove": ["lasso2d", "select2d"]
        },
        key=f"professional_{symbol.lower()}"
    )



# ===== EMBEDDED MODULE: market_movers.py =====

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


# ===== EMBEDDED MODULE: market_drivers.py =====

import pandas as pd


def build_market_drivers(brent, wti, news, risk):
    rows = []

    def add(name, direction, strength, evidence):
        rows.append({
            "Driver": name,
            "Direction": direction,
            "Strength": int(max(0, min(100, strength))),
            "Evidence": evidence
        })

    add(
        "Brent Trend",
        brent["trend"],
        abs(brent["momentum"]) * 10 + 40,
        f"10-day momentum {brent['momentum']:+.2f}%"
    )

    add(
        "WTI Trend",
        wti["trend"],
        abs(wti["momentum"]) * 10 + 40,
        f"10-day momentum {wti['momentum']:+.2f}%"
    )

    groups = {
        "OPEC / Production": ["opec", "production", "output", "cut"],
        "US Inventories": ["inventory", "inventories", "eia", "api"],
        "Geopolitics": ["iran", "russia", "middle east", "sanction", "attack"],
        "Global Demand": ["demand", "china", "economy", "recession"],
        "Dollar / Fed": ["dollar", "fed", "rates", "interest"]
    }

    if news is not None and not news.empty:
        for driver, terms in groups.items():
            selected = news[
                news["Title"].astype(str).str.lower().apply(
                    lambda title: any(term in title for term in terms)
                )
            ]

            if selected.empty:
                add(driver, "NEUTRAL", 20, "No dominant live evidence")
                continue

            impact = float(selected["Impact"].sum())

            direction = (
                "BULLISH" if impact > 0
                else "BEARISH" if impact < 0
                else "NEUTRAL"
            )

            add(
                driver,
                direction,
                abs(impact),
                f"{len(selected)} relevant market-moving item(s)"
            )
    else:
        for driver in groups:
            add(driver, "NEUTRAL", 20, "Live news unavailable")

    volatility = max(brent["volatility"], wti["volatility"])

    add(
        "Volatility",
        risk,
        volatility,
        f"{volatility:.1f}% annualized"
    )

    return pd.DataFrame(rows)


# ===== EMBEDDED MODULE: why_signal.py =====

def build_why_signal(signal, score, confidence, risk, regime, brent, wti, news):
    reasons = []

    reasons.append(
        "Brent trades above its 20-day moving average."
        if brent["trend"] == "BULLISH"
        else "Brent trades below its 20-day moving average."
    )

    reasons.append(
        "WTI trend is bullish."
        if wti["trend"] == "BULLISH"
        else "WTI trend is bearish."
    )

    reasons.append(
        f"Brent 10-day momentum is "
        f"{'positive' if brent['momentum'] > 0 else 'negative'} "
        f"at {brent['momentum']:+.2f}%."
    )

    reasons.append(
        "Market volatility is elevated."
        if risk == "HIGH"
        else "Market volatility is moderate."
        if risk == "MEDIUM"
        else "Market volatility is contained."
    )

    if news is not None and not news.empty:
        bullish = int((news["Bias"] == "BULLISH").sum())
        bearish = int((news["Bias"] == "BEARISH").sum())

        if bullish > bearish:
            reasons.append("News flow is predominantly bullish.")
        elif bearish > bullish:
            reasons.append("News flow is predominantly bearish.")
        else:
            reasons.append("News flow is mixed or neutral.")

    clean_signal = (
        str(signal)
        .replace("🟢", "")
        .replace("🔴", "")
        .replace("🟡", "")
        .strip()
    )

    if "LONG" in str(signal):
        action = "Current evidence favours upward oil exposure."
    elif "SHORT" in str(signal):
        action = "Current evidence favours downward oil exposure."
    else:
        action = "Wait for stronger directional confirmation before acting."

    return {
        "title": f"Why {clean_signal}?",
        "score": score,
        "confidence": confidence,
        "regime": regime,
        "reasons": reasons,
        "action": action
    }


# ===== EMBEDDED MODULE: market_delta.py =====

import json
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st


SNAPSHOT_FILE = Path("data/last_snapshot.json")


def _safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _clean_signal(value):
    return (
        str(value)
        .replace("🟢", "")
        .replace("🔴", "")
        .replace("🟡", "")
        .strip()
    )


def render_market_delta(brent, wti, signal, score, confidence):
    SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)

    current = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "brent": _safe_float(brent.get("price")),
        "wti": _safe_float(wti.get("price")),
        "signal": str(signal),
        "score": int(score),
        "confidence": str(confidence),
    }

    previous = None

    if SNAPSHOT_FILE.exists():
        try:
            previous = json.loads(
                SNAPSHOT_FILE.read_text(encoding="utf-8")
            )
        except Exception:
            previous = None

    st.markdown("### 📈 Since Last Refresh")

    if not previous:
        st.caption(
            "Baseline created. Changes will appear after the next refresh."
        )
    else:
        old_brent = _safe_float(previous.get("brent"))
        old_wti = _safe_float(previous.get("wti"))

        delta_brent = (
            current["brent"] - old_brent
            if current["brent"] is not None and old_brent is not None
            else None
        )

        delta_wti = (
            current["wti"] - old_wti
            if current["wti"] is not None and old_wti is not None
            else None
        )

        delta_score = current["score"] - int(previous.get("score", current["score"]))

        old_signal = str(previous.get("signal", current["signal"]))
        old_confidence = str(
            previous.get("confidence", current["confidence"])
        )

        c1, c2, c3, c4, c5 = st.columns(5)

        with c1:
            st.metric(
                "Δ Brent",
                f"{delta_brent:+.2f}" if delta_brent is not None else "N/A",
                help="Price change in USD since the previous refresh."
            )

        with c2:
            st.metric(
                "Δ WTI",
                f"{delta_wti:+.2f}" if delta_wti is not None else "N/A",
                help="Price change in USD since the previous refresh."
            )

        with c3:
            if old_signal != current["signal"]:
                pe_metric(
                    "pe_signal_change",
                    "Signal Change",
                    _clean_signal(current["signal"]),
                    f"{_clean_signal(old_signal)} → {_clean_signal(current['signal'])}"
                )
            else:
                pe_metric(
                    "pe_signal_change",
                    "Signal Change",
                    "UNCHANGED",
                    _clean_signal(current["signal"]),
                    delta_color="off"
                )

        with c4:
            st.metric(
                "Δ Market Score",
                f"{delta_score:+d}",
                f"{previous.get('score', current['score'])} → {current['score']}"
                if delta_score != 0 else "UNCHANGED",
                delta_color="normal" if delta_score != 0 else "off"
            )

        with c5:
            if old_confidence != current["confidence"]:
                st.metric(
                    "Confidence Change",
                    current["confidence"],
                    f"{old_confidence} → {current['confidence']}"
                )
            else:
                st.metric(
                    "Confidence Change",
                    "UNCHANGED",
                    current["confidence"],
                    delta_color="off"
                )

    SNAPSHOT_FILE.write_text(
        json.dumps(current, indent=2),
        encoding="utf-8"
    )


# ===== EMBEDDED MODULE: system_health.py =====

from datetime import datetime, timezone
import streamlit as st


def render_system_health(brent_df, wti_df, news_df):
    now = datetime.now(timezone.utc)

    def latest_market_time(df):
        if df is None or df.empty or "Date" not in df.columns:
            return None

        value = pd.to_datetime(
            df["Date"],
            errors="coerce",
            utc=True
        ).max()

        if pd.isna(value):
            return None

        return value.to_pydatetime()

    def latest_news_time(df):
        if (
            df is None
            or df.empty
            or "PublishedUTC" not in df.columns
        ):
            return None

        value = pd.to_datetime(
            df["PublishedUTC"],
            errors="coerce",
            utc=True
        ).max()

        if pd.isna(value):
            return None

        return value.to_pydatetime()

    brent_time = latest_market_time(brent_df)
    wti_time = latest_market_time(wti_df)
    news_time = latest_news_time(news_df)

    valid_times = [
        value for value in (brent_time, wti_time, news_time)
        if value is not None
    ]

    freshest = max(valid_times) if valid_times else None

    age_minutes = (
        max(0, int((now - freshest).total_seconds() / 60))
        if freshest else None
    )

    if age_minutes is None:
        freshness_state = "UNAVAILABLE"
    elif age_minutes <= 20:
        freshness_state = "LIVE"
    elif age_minutes <= 90:
        freshness_state = "STALE"
    else:
        freshness_state = "BACKUP DATA"

    st.markdown("### 🟢 System Health")

    h1, h2, h3, h4 = st.columns(4)

    with h1:
        st.metric(
            "Page Update",
            now.strftime("%H:%M UTC")
        )

    with h2:
        st.metric(
            "Data Age",
            f"{age_minutes} min"
            if age_minutes is not None
            else "N/A"
        )

    with h3:
        st.metric(
            "Freshness",
            freshness_state
        )

    with h4:
        if st.button(
            "🔄 Refresh Now",
            key="global_refresh"
        ):
            st.cache_data.clear()
            st.rerun()

    s1, s2, s3 = st.columns(3)

    with s1:
        if brent_df is not None and not brent_df.empty:
            st.success("Brent source: ONLINE")
        else:
            st.error("Brent source: UNAVAILABLE")

    with s2:
        if wti_df is not None and not wti_df.empty:
            st.success("WTI source: ONLINE")
        else:
            st.error("WTI source: UNAVAILABLE")

    with s3:
        live_news = (
            news_df is not None
            and not news_df.empty
            and not (
                len(news_df) == 1
                and str(
                    news_df.iloc[0].get("Source", "")
                ).upper() == "PROCUREYE"
            )
        )

        if live_news:
            st.success("News sources: ONLINE")
        else:
            st.warning("News sources: BACKUP")

    st.caption(
        "Prices refresh every 5 minutes; "
        "news refresh every 15 minutes."
    )

# ===== MAIN APPLICATION =====

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path
from datetime import datetime, timezone
import inspect






def render_executive_dashboard(
    brent,
    wti,
    signal,
    score,
    confidence,
    risk,
    regime,
    spread,
):
    def price(value):
        try:
            if value is None:
                return "N/A"
            return f"${float(value):.2f}"
        except Exception:
            return "N/A"

    def percent(value):
        try:
            if value is None:
                return None
            return f"{float(value):+.2f}%"
        except Exception:
            return None

    updated = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    st.markdown(
        """
        <div class="pe-section">
            <strong>Executive Dashboard</strong>
            <span>Current market state</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.caption(f"Updated {updated}")

    c1, c2, c3, c4, c5, c6 = st.columns(6)

    with c1:
        st.metric(
            "Brent",
            price(brent.get("price")),
            percent(brent.get("change")),
        )

    with c2:
        st.metric(
            "WTI",
            price(wti.get("price")),
            percent(wti.get("change")),
        )

    with c3:
        st.metric(
            "Signal",
            str(signal),
        )

    with c4:
        st.metric(
            "Market Score",
            f"{int(score)}/100",
        )

    with c5:
        st.metric(
            "Confidence",
            str(confidence),
        )

    with c6:
        st.metric(
            "Risk",
            str(risk),
        )

    d1, d2, d3, d4 = st.columns(4)

    with d1:
        st.metric(
            "Market Regime",
            str(regime),
        )

    with d2:
        st.metric(
            "Brent Trend",
            str(brent.get("trend", "UNKNOWN")),
        )

    with d3:
        st.metric(
            "WTI Trend",
            str(wti.get("trend", "UNKNOWN")),
        )

    with d4:
        st.metric(
            "Brent-WTI Spread",
            price(spread),
        )



# PROCUREYE RELEASE 41.1 — DECISION JOURNAL FOUNDATION

def _decision_journal_connection():
    import sqlite3

    db_path = Path("/tmp/procureye_decision_journal.db")
    connection = sqlite3.connect(db_path)

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS decision_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_utc TEXT NOT NULL,
            brent REAL,
            wti REAL,
            signal TEXT,
            market_score INTEGER,
            confidence TEXT,
            risk TEXT,
            regime TEXT,
            news_score REAL,
            news_count INTEGER
        )
        """
    )

    connection.commit()
    return connection


def _safe_journal_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def record_decision_journal(
    brent,
    wti,
    signal,
    score,
    confidence,
    risk,
    regime,
    news
):
    from datetime import datetime, timezone

    connection = _decision_journal_connection()

    brent_price = _safe_journal_float(
        brent.get("price") if isinstance(brent, dict) else None
    )

    wti_price = _safe_journal_float(
        wti.get("price") if isinstance(wti, dict) else None
    )

    news_count = 0
    news_score = 0.0

    if news is not None and not news.empty:
        news_count = int(len(news))

        if "Impact" in news.columns:
            news_score = float(
                pd.to_numeric(
                    news["Impact"],
                    errors="coerce"
                )
                .fillna(0)
                .mean()
            )

    now = datetime.now(timezone.utc)

    previous = connection.execute(
        """
        SELECT
            timestamp_utc,
            brent,
            wti,
            signal,
            market_score,
            confidence,
            news_score,
            news_count
        FROM decision_journal
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    should_insert = previous is None

    if previous is not None:
        try:
            previous_time = datetime.fromisoformat(previous[0])
            elapsed_minutes = (
                now - previous_time
            ).total_seconds() / 60
        except Exception:
            elapsed_minutes = 999

        previous_brent = _safe_journal_float(previous[1])
        previous_wti = _safe_journal_float(previous[2])

        brent_changed = (
            brent_price is not None
            and previous_brent is not None
            and abs(brent_price - previous_brent) >= 0.05
        )

        wti_changed = (
            wti_price is not None
            and previous_wti is not None
            and abs(wti_price - previous_wti) >= 0.05
        )

        state_changed = any([
            str(signal) != str(previous[3]),
            int(score) != int(previous[4]),
            str(confidence) != str(previous[5]),
            abs(float(news_score) - float(previous[6] or 0)) >= 1,
            int(news_count) != int(previous[7] or 0),
        ])

        should_insert = (
            elapsed_minutes >= 15
            or brent_changed
            or wti_changed
            or state_changed
        )

    if should_insert:
        connection.execute(
            """
            INSERT INTO decision_journal (
                timestamp_utc,
                brent,
                wti,
                signal,
                market_score,
                confidence,
                risk,
                regime,
                news_score,
                news_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now.isoformat(),
                brent_price,
                wti_price,
                str(signal),
                int(score),
                str(confidence),
                str(risk),
                str(regime),
                round(news_score, 2),
                news_count,
            )
        )

        connection.commit()

    connection.close()


def render_decision_journal():
    connection = _decision_journal_connection()

    frame = pd.read_sql_query(
        """
        SELECT
            timestamp_utc AS "Timestamp UTC",
            brent AS "Brent",
            wti AS "WTI",
            signal AS "Signal",
            market_score AS "Score",
            confidence AS "Confidence",
            risk AS "Risk",
            regime AS "Regime",
            news_score AS "News Score",
            news_count AS "News Count"
        FROM decision_journal
        ORDER BY id DESC
        LIMIT 50
        """,
        connection
    )

    total_rows = connection.execute(
        "SELECT COUNT(*) FROM decision_journal"
    ).fetchone()[0]

    connection.close()

    if frame.empty:
        st.info("Decision Journal baseline awaiting first record.")
        return

    frame["Timestamp UTC"] = pd.to_datetime(
        frame["Timestamp UTC"],
        errors="coerce",
        utc=True
    ).dt.strftime("%d %b %Y · %H:%M UTC")

    j1, j2, j3, j4 = st.columns(4)

    with j1:
        st.metric(
            "Recorded Decisions",
            int(total_rows)
        )

    with j2:
        st.metric(
            "Latest Signal",
            str(frame.iloc[0]["Signal"])
        )

    with j3:
        st.metric(
            "Latest Score",
            f"{int(frame.iloc[0]['Score'])}/100"
        )

    with j4:
        st.metric(
            "Latest Confidence",
            str(frame.iloc[0]["Confidence"])
        )

    st.dataframe(
        frame.head(20),
        width="stretch",
        hide_index=True
    )

    csv_data = frame.to_csv(
        index=False
    ).encode("utf-8")

    st.download_button(
        "Download Decision Journal CSV",
        data=csv_data,
        file_name="procureye_decision_journal.csv",
        mime="text/csv",
        key="download_decision_journal"
    )



# PROCUREYE RELEASE 41.4 — ADAPTIVE NEWS WEIGHT

def calculate_adaptive_news_weight(
    news,
    risk,
    regime,
    confidence
):
    result = {
        "raw_score": 0.0,
        "effective_score": 0.0,
        "weight": 0.0,
        "quality": 0.0,
        "diversity": 0.0,
        "dominant_driver": "NONE",
        "direction": "NEUTRAL",
        "sample_size": 0,
        "explanation": "No live news evidence is available."
    }

    if news is None or news.empty:
        return result

    if "Impact" not in news.columns:
        return result

    frame = news.copy()

    frame["Impact"] = pd.to_numeric(
        frame["Impact"],
        errors="coerce"
    ).fillna(0.0)

    if "Confidence" in frame.columns:
        frame["Confidence"] = pd.to_numeric(
            frame["Confidence"],
            errors="coerce"
        ).fillna(40.0).clip(0, 100)
    else:
        frame["Confidence"] = 40.0

    frame = frame[
        frame["Impact"].notna()
    ].copy()

    if frame.empty:
        return result

    confidence_weights = (
        frame["Confidence"]
        .clip(lower=10)
        / 100
    )

    weighted_denominator = confidence_weights.sum()

    if weighted_denominator > 0:
        raw_score = float(
            (
                frame["Impact"]
                * confidence_weights
            ).sum()
            / weighted_denominator
        )
    else:
        raw_score = float(
            frame["Impact"].mean()
        )

    sample_size = int(len(frame))

    average_confidence = float(
        frame["Confidence"].mean()
    )

    quality = max(
        0.25,
        min(1.0, average_confidence / 100)
    )

    if "Driver" in frame.columns:
        valid_drivers = (
            frame["Driver"]
            .fillna("UNKNOWN")
            .astype(str)
        )

        unique_drivers = int(
            valid_drivers.nunique()
        )

        dominant_driver = str(
            valid_drivers.value_counts().index[0]
        )

        diversity = min(
            1.0,
            unique_drivers / 3
        )
    else:
        unique_drivers = 1
        dominant_driver = "OIL MARKET"
        diversity = 0.35

    sample_factor = min(
        1.0,
        sample_size / 3
    )

    regime_text = str(regime).upper()
    risk_text = str(risk).upper()
    confidence_text = str(confidence).upper()

    regime_factor = {
        "BULLISH": 1.00,
        "BEARISH": 1.00,
        "TRANSITION": 0.75,
        "UNKNOWN": 0.55
    }.get(regime_text, 0.70)

    risk_factor = {
        "LOW": 1.00,
        "MEDIUM": 0.90,
        "HIGH": 0.72
    }.get(risk_text, 0.80)

    system_confidence_factor = {
        "HIGH": 1.00,
        "MEDIUM": 0.85,
        "LOW": 0.65
    }.get(confidence_text, 0.70)

    weight = (
        quality * 0.35
        + diversity * 0.20
        + sample_factor * 0.15
        + regime_factor * 0.10
        + risk_factor * 0.10
        + system_confidence_factor * 0.10
    )

    weight = max(
        0.20,
        min(1.0, weight)
    )

    effective_score = raw_score * weight

    effective_score = max(
        -100.0,
        min(100.0, effective_score)
    )

    if effective_score >= 8:
        direction = "BULLISH"
    elif effective_score <= -8:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    explanation = (
        f"{sample_size} market-moving item(s), "
        f"{unique_drivers} distinct driver(s), "
        f"average source confidence {average_confidence:.0f}%. "
        f"Adaptive news weight {weight:.2f}."
    )

    result.update({
        "raw_score": round(raw_score, 2),
        "effective_score": round(effective_score, 2),
        "weight": round(weight, 3),
        "quality": round(quality, 3),
        "diversity": round(diversity, 3),
        "dominant_driver": dominant_driver,
        "direction": direction,
        "sample_size": sample_size,
        "explanation": explanation
    })

    return result


def render_adaptive_news_weight(
    adaptive_news
):
    n1, n2, n3, n4 = st.columns(4)

    with n1:
        st.metric(
            "Raw News Score",
            f"{adaptive_news['raw_score']:+.1f}"
        )

    with n2:
        st.metric(
            "Effective News Score",
            f"{adaptive_news['effective_score']:+.1f}"
        )

    with n3:
        st.metric(
            "Adaptive Weight",
            f"{adaptive_news['weight']:.2f}"
        )

    with n4:
        st.metric(
            "News Direction",
            adaptive_news["direction"]
        )

    st.progress(
        int(
            max(
                0,
                min(
                    100,
                    adaptive_news["weight"] * 100
                )
            )
        )
    )

    st.caption(
        f"Dominant driver: "
        f"{adaptive_news['dominant_driver']} · "
        f"{adaptive_news['explanation']}"
    )



# ======================================================================
# PROCUREYE RELEASE 41.5
# CONFIDENCE ENGINE
# ======================================================================

def calculate_confidence_engine(
    brent,
    wti,
    adaptive_news,
    similar_cases=None,
    validation=None
):

    trend = 50
    momentum = 50
    volatility = 50
    news = 50
    history = 50
    validation_score = 50

    try:

        if brent.get("trend") == "BULLISH":
            trend += 20
        elif brent.get("trend") == "BEARISH":
            trend += 20

        if wti.get("trend") == brent.get("trend"):
            trend += 15

    except:
        pass

    try:

        bm = abs(float(brent.get("momentum",0)))
        wm = abs(float(wti.get("momentum",0)))

        momentum += min(25,(bm+wm)/2)

    except:
        pass

    try:

        vol=max(
            float(brent.get("volatility",50)),
            float(wti.get("volatility",50))
        )

        if vol<20:
            volatility=95
        elif vol<30:
            volatility=85
        elif vol<40:
            volatility=70
        elif vol<55:
            volatility=55
        else:
            volatility=35

    except:
        pass

    try:

        news=round(
            adaptive_news["weight"]*100
        )

    except:
        pass

    try:

        if similar_cases is not None:

            history=min(
                100,
                max(
                    40,
                    float(similar_cases)
                )
            )

    except:
        pass

    try:

        if validation is not None:

            validation_score=min(
                100,
                max(
                    40,
                    float(validation)
                )
            )

    except:
        pass

    final_score=round(

        trend*0.20+
        momentum*0.15+
        volatility*0.15+
        news*0.20+
        history*0.15+
        validation_score*0.15

    )

    if final_score>=85:
        label="VERY HIGH"

    elif final_score>=70:
        label="HIGH"

    elif final_score>=55:
        label="MEDIUM"

    elif final_score>=40:
        label="LOW"

    else:
        label="VERY LOW"

    return {

        "score":final_score,
        "label":label,

        "Trend":round(trend),
        "Momentum":round(momentum),
        "Volatility":round(volatility),
        "News":round(news),
        "History":round(history),
        "Validation":round(validation_score)

    }


def render_confidence_engine(result):

    section(
        "Confidence Engine",
        "Explainable confidence decomposition"
    )

    c1,c2=st.columns([1,2])

    with c1:

        st.metric(
            "Overall Confidence",
            f'{result["score"]}%'
        )

        st.metric(
            "Level",
            result["label"]
        )

    with c2:

        breakdown=pd.DataFrame({

            "Component":[
                "Trend",
                "Momentum",
                "Volatility",
                "News",
                "History",
                "Validation"
            ],

            "Score":[
                result["Trend"],
                result["Momentum"],
                result["Volatility"],
                result["News"],
                result["History"],
                result["Validation"]
            ]

        })

        st.dataframe(
            breakdown,
            width="stretch",
            hide_index=True,
            column_config={
                "Score":st.column_config.ProgressColumn(
                    "Score",
                    min_value=0,
                    max_value=100
                )
            }
        )



# PROCUREYE RELEASE 41.8.1 — DAILY MARKET BRIEF

def build_daily_market_brief(
    brent,
    wti,
    signal,
    score,
    confidence,
    risk,
    regime,
    adaptive_news,
    confidence_engine,
    news
):
    def format_price(value):
        try:
            return f"${float(value):.2f}"
        except Exception:
            return "N/A"

    def format_percent(value):
        try:
            return f"{float(value):+.2f}%"
        except Exception:
            return "N/A"

    clean_signal = (
        str(signal)
        .replace("🟢", "")
        .replace("🔴", "")
        .replace("🟡", "")
        .strip()
    )

    news_direction = str(
        adaptive_news.get("direction", "NEUTRAL")
    )

    dominant_driver = str(
        adaptive_news.get("dominant_driver", "NONE")
    )

    effective_news_score = float(
        adaptive_news.get("effective_score", 0.0)
    )

    confidence_score = int(
        confidence_engine.get("score", 0)
    )

    confidence_label = str(
        confidence_engine.get("label", confidence)
    )

    news_count = 0
    top_headline = "No dominant live headline."

    if news is not None and not news.empty:
        news_count = int(len(news))

        if "Title" in news.columns:
            top_headline = str(
                news.iloc[0].get(
                    "Title",
                    top_headline
                )
            )

    structure = (
        f"Brent is {format_price(brent.get('price'))} "
        f"({format_percent(brent.get('change'))}) with a "
        f"{str(brent.get('trend', 'UNKNOWN')).lower()} trend. "
        f"WTI is {format_price(wti.get('price'))} "
        f"({format_percent(wti.get('change'))}) with a "
        f"{str(wti.get('trend', 'UNKNOWN')).lower()} trend."
    )

    momentum = (
        f"Brent 10-day momentum is "
        f"{float(brent.get('momentum', 0)):+.2f}% and "
        f"WTI momentum is "
        f"{float(wti.get('momentum', 0)):+.2f}%."
    )

    news_summary = (
        f"News pressure is {news_direction.lower()} with "
        f"effective score {effective_news_score:+.1f}. "
        f"The dominant driver is {dominant_driver}. "
        f"{news_count} market-moving item(s) are ranked. "
        f"Top headline: {top_headline}"
    )

    decision = (
        f"PROCUREYE indicates {clean_signal} with "
        f"Market Score {int(score)}/100, "
        f"Confidence Engine {confidence_score}% "
        f"({confidence_label}), risk {risk}, "
        f"and regime {regime}."
    )

    if "LONG" in clean_signal.upper():
        action = (
            "Upward evidence dominates. Confirm persistence in price, "
            "momentum and news before taking exposure."
        )
    elif "SHORT" in clean_signal.upper():
        action = (
            "Downward evidence dominates. Confirm persistence in price, "
            "momentum and news before taking exposure."
        )
    else:
        action = (
            "Directional confirmation remains insufficient. "
            "Maintain WAIT until stronger evidence emerges."
        )

    return {
        "structure": structure,
        "momentum": momentum,
        "news": news_summary,
        "decision": decision,
        "action": action,
    }


def render_daily_market_brief(brief):
    section(
        "Daily Market Brief",
        "One-minute executive market summary"
    )

    st.markdown(
        f"""
**Market structure**  
{brief["structure"]}

**Momentum**  
{brief["momentum"]}

**News intelligence**  
{brief["news"]}

**Decision**  
{brief["decision"]}
"""
    )

    st.info(brief["action"])



def render_driver_intelligence_panel(report):
    section(
        "Driver Intelligence",
        "Structured evidence behind market direction"
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            "Dominant Driver",
            report.get("dominant_driver", "NONE")
        )

    with c2:
        st.metric(
            "Direction",
            report.get("direction", "NEUTRAL")
        )

    with c3:
        st.metric(
            "Strength",
            f"{int(report.get('strength', 0))}/100"
        )

    with c4:
        st.metric(
            "Confidence",
            f"{int(report.get('confidence', 0))}%"
        )

    drivers = report.get("drivers")

    if (
        isinstance(drivers, pd.DataFrame)
        and not drivers.empty
    ):
        st.dataframe(
            drivers,
            width="stretch",
            hide_index=True,
            column_config={
                "Strength": st.column_config.ProgressColumn(
                    "Strength",
                    min_value=0,
                    max_value=100,
                    format="%d"
                ),
                "Confidence": st.column_config.ProgressColumn(
                    "Confidence",
                    min_value=0,
                    max_value=100,
                    format="%d%%"
                ),
            }
        )
    else:
        st.info(
            "Driver Intelligence awaits live evidence."
        )

    st.caption(
        report.get("reason", "")
    )



# ============================================================
# PROCUREYE RELEASE 42.1 DEV — DRIVER INTELLIGENCE
# ============================================================

def _di_number(value, default=0.0):
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _di_source_quality(source):
    source = str(source or "").lower()

    quality = {
        "reuters": 1.00,
        "bloomberg": 0.98,
        "eia": 1.00,
        "opec": 0.96,
        "iea": 0.96,
        "financial times": 0.92,
        "wall street journal": 0.90,
        "associated press": 0.86,
        "cnbc": 0.82,
        "marketwatch": 0.74,
        "oilprice": 0.72,
    }

    matches = [
        score
        for name, score in quality.items()
        if name in source
    ]

    return max(matches) if matches else 0.60


def analyze_driver_intelligence(news):
    columns = [
        "Driver",
        "Direction",
        "Net Score",
        "Strength",
        "Confidence",
        "Evidence",
        "Sources",
    ]

    empty = {
        "dominant_driver": "NONE",
        "direction": "NEUTRAL",
        "strength": 0,
        "confidence": 0,
        "evidence_count": 0,
        "independent_sources": 0,
        "reason": "No live driver evidence is available.",
        "drivers": pd.DataFrame(columns=columns),
    }

    if news is None or news.empty:
        return empty

    evidence = []

    for _, item in news.iterrows():
        driver = str(
            item.get("Driver", "OIL MARKET")
        ).strip() or "OIL MARKET"

        source_name = str(
            item.get("Source", "UNKNOWN")
        )

        bias = str(
            item.get("Bias", "NEUTRAL")
        ).upper()

        impact = _di_number(
            item.get("Impact", 0.0)
        )

        item_confidence = _di_number(
            item.get("Confidence", 50.0),
            50.0
        )

        directional_impact = (
            abs(impact)
            if bias == "BULLISH"
            else -abs(impact)
            if bias == "BEARISH"
            else impact
        )

        weighted_score = (
            directional_impact
            * _di_source_quality(source_name)
            * max(
                0.25,
                min(1.0, item_confidence / 100)
            )
        )

        evidence.append({
            "Driver": driver,
            "Source": source_name,
            "Score": weighted_score,
            "Confidence": item_confidence,
        })

    evidence_frame = pd.DataFrame(evidence)

    if evidence_frame.empty:
        return empty

    rows = []

    for driver, group in evidence_frame.groupby("Driver"):
        net_score = float(group["Score"].sum())
        evidence_count = int(len(group))
        source_count = int(group["Source"].nunique())

        average_confidence = float(
            group["Confidence"].mean()
        )

        direction = (
            "BULLISH"
            if net_score >= 8
            else "BEARISH"
            if net_score <= -8
            else "NEUTRAL"
        )

        strength = int(
            min(
                100,
                abs(net_score)
                + evidence_count * 8
                + source_count * 6
            )
        )

        confidence_score = int(
            min(
                98,
                average_confidence * 0.70
                + min(28, source_count * 9)
            )
        )

        rows.append({
            "Driver": driver,
            "Direction": direction,
            "Net Score": round(net_score, 1),
            "Strength": strength,
            "Confidence": confidence_score,
            "Evidence": evidence_count,
            "Sources": source_count,
        })

    drivers = (
        pd.DataFrame(rows)
        .sort_values(
            ["Strength", "Confidence", "Evidence"],
            ascending=False
        )
        .reset_index(drop=True)
    )

    dominant = drivers.iloc[0]

    return {
        "dominant_driver": str(dominant["Driver"]),
        "direction": str(dominant["Direction"]),
        "strength": int(dominant["Strength"]),
        "confidence": int(dominant["Confidence"]),
        "evidence_count": int(dominant["Evidence"]),
        "independent_sources": int(dominant["Sources"]),
        "reason": (
            f"{dominant['Driver']} is the strongest current driver: "
            f"{dominant['Direction']}, supported by "
            f"{int(dominant['Evidence'])} evidence item(s) from "
            f"{int(dominant['Sources'])} independent source(s)."
        ),
        "drivers": drivers,
    }


def render_driver_intelligence_panel(report):
    section(
        "Driver Intelligence",
        "Structured evidence behind market direction"
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            "Dominant Driver",
            report.get("dominant_driver", "NONE")
        )

    with c2:
        st.metric(
            "Direction",
            report.get("direction", "NEUTRAL")
        )

    with c3:
        st.metric(
            "Strength",
            f"{int(report.get('strength', 0))}/100"
        )

    with c4:
        st.metric(
            "Confidence",
            f"{int(report.get('confidence', 0))}%"
        )

    drivers = report.get("drivers")

    if isinstance(drivers, pd.DataFrame) and not drivers.empty:
        st.dataframe(
            drivers,
            width="stretch",
            hide_index=True,
            column_config={
                "Strength": st.column_config.ProgressColumn(
                    "Strength",
                    min_value=0,
                    max_value=100,
                    format="%d"
                ),
                "Confidence": st.column_config.ProgressColumn(
                    "Confidence",
                    min_value=0,
                    max_value=100,
                    format="%d%%"
                ),
            }
        )
    else:
        st.info(
            "Driver Intelligence awaits live evidence."
        )

    st.caption(report.get("reason", ""))




# PROCUREYE RELEASE 42.2 DEV — MARKET MOVERS RANKING PRO

def build_market_movers_ranking(news, limit=10):
    columns = [
        "Rank",
        "Headline",
        "Driver",
        "Direction",
        "Impact",
        "Confidence",
        "Importance",
        "Source",
        "Published",
    ]

    if news is None or news.empty:
        return pd.DataFrame(columns=columns)

    frame = news.copy()

    defaults = {
        "Title": "Untitled market event",
        "Driver": "OIL MARKET",
        "Bias": "NEUTRAL",
        "Impact": 0.0,
        "Confidence": 0.0,
        "Importance": 0.0,
        "Source": "UNKNOWN",
        "Published": "N/A",
        "AgeHours": 999.0,
    }

    for column, default in defaults.items():
        if column not in frame.columns:
            frame[column] = default

    for column in [
        "Impact",
        "Confidence",
        "Importance",
        "AgeHours",
    ]:
        frame[column] = pd.to_numeric(
            frame[column],
            errors="coerce"
        ).fillna(defaults[column])

    frame["Freshness Score"] = (
        100 - frame["AgeHours"].clip(0, 100)
    )

    frame["Ranking Score"] = (
        frame["Impact"].abs() * 0.40
        + frame["Confidence"] * 0.25
        + frame["Importance"] * 0.25
        + frame["Freshness Score"] * 0.10
    ).clip(0, 100)

    frame["Direction"] = (
        frame["Bias"]
        .fillna("NEUTRAL")
        .astype(str)
        .str.upper()
    )

    frame = (
        frame.sort_values(
            [
                "Ranking Score",
                "Confidence",
                "Importance",
            ],
            ascending=False
        )
        .drop_duplicates(
            subset=["Title"],
            keep="first"
        )
        .head(int(limit))
        .reset_index(drop=True)
    )

    frame.insert(
        0,
        "Rank",
        range(1, len(frame) + 1)
    )

    result = frame.rename(
        columns={
            "Title": "Headline",
        }
    )

    result["Impact"] = result["Impact"].round(1)
    result["Confidence"] = result["Confidence"].round(0).astype(int)
    result["Importance"] = result["Importance"].round(1)
    result["Ranking Score"] = result["Ranking Score"].round(1)

    return result[
        [
            "Rank",
            "Headline",
            "Driver",
            "Direction",
            "Ranking Score",
            "Impact",
            "Confidence",
            "Importance",
            "Source",
            "Published",
        ]
    ]


def render_market_movers_ranking(ranking):
    section(
        "Market Movers Ranking Pro",
        "Top live events ranked by impact, confidence, importance and freshness"
    )

    if ranking is None or ranking.empty:
        st.info(
            "Market Movers Ranking awaits live news evidence."
        )
        return

    leader = ranking.iloc[0]

    r1, r2, r3, r4 = st.columns(4)

    with r1:
        st.metric(
            "Leading Driver",
            str(leader["Driver"])
        )

    with r2:
        st.metric(
            "Direction",
            str(leader["Direction"])
        )

    with r3:
        st.metric(
            "Ranking Score",
            f"{float(leader['Ranking Score']):.1f}/100"
        )

    with r4:
        st.metric(
            "Events Ranked",
            int(len(ranking))
        )

    st.dataframe(
        ranking,
        width="stretch",
        hide_index=True,
        column_config={
            "Ranking Score": st.column_config.ProgressColumn(
                "Ranking Score",
                min_value=0,
                max_value=100,
                format="%.1f"
            ),
            "Confidence": st.column_config.ProgressColumn(
                "Confidence",
                min_value=0,
                max_value=100,
                format="%d%%"
            ),
            "Impact": st.column_config.NumberColumn(
                "Impact",
                format="%+.1f"
            ),
        }
    )

    st.caption(
        "Ranking Score = 40% absolute impact + 25% confidence "
        "+ 25% importance + 10% freshness."
    )

# END PROCUREYE RELEASE 42.2 DEV



# PROCUREYE RELEASE 42.3 DEV — DRIVER CORRELATION ENGINE

DRIVER_FAMILIES = {
    "SUPPLY TIGHTENING": {
        "OPEC / PRODUCTION",
        "SUPPLY DISRUPTION",
        "GEOPOLITICS",
    },
    "DEMAND SUPPORT": {
        "GLOBAL DEMAND",
        "DOLLAR / FED",
    },
    "INVENTORY PRESSURE": {
        "US INVENTORIES",
    },
}


def calculate_driver_correlation(driver_report):
    empty = {
        "state": "INSUFFICIENT DATA",
        "direction": "NEUTRAL",
        "score": 0,
        "confidence": 0,
        "alignment": 0,
        "contradictions": 0,
        "active_drivers": 0,
        "summary": "Insufficient structured driver evidence.",
        "details": pd.DataFrame(
            columns=[
                "Driver",
                "Direction",
                "Strength",
                "Confidence",
                "Contribution",
            ]
        ),
    }

    if not isinstance(driver_report, dict):
        return empty

    drivers = driver_report.get("drivers")

    if not isinstance(drivers, pd.DataFrame) or drivers.empty:
        return empty

    frame = drivers.copy()

    required = {
        "Driver": "OIL MARKET",
        "Direction": "NEUTRAL",
        "Strength": 0,
        "Confidence": 0,
    }

    for column, default in required.items():
        if column not in frame.columns:
            frame[column] = default

    frame["Strength"] = pd.to_numeric(
        frame["Strength"],
        errors="coerce"
    ).fillna(0).clip(0, 100)

    frame["Confidence"] = pd.to_numeric(
        frame["Confidence"],
        errors="coerce"
    ).fillna(0).clip(0, 100)

    frame["Direction"] = (
        frame["Direction"]
        .fillna("NEUTRAL")
        .astype(str)
        .str.upper()
    )

    direction_value = {
        "BULLISH": 1,
        "BEARISH": -1,
        "NEUTRAL": 0,
    }

    frame["Direction Value"] = frame["Direction"].map(
        direction_value
    ).fillna(0)

    frame["Contribution"] = (
        frame["Direction Value"]
        * frame["Strength"]
        * frame["Confidence"]
        / 100
    ).round(1)

    active = frame[
        frame["Direction"].isin(["BULLISH", "BEARISH"])
    ].copy()

    if active.empty:
        return empty

    bullish = int((active["Direction"] == "BULLISH").sum())
    bearish = int((active["Direction"] == "BEARISH").sum())

    net_score = float(active["Contribution"].sum())
    total_absolute = float(active["Contribution"].abs().sum())

    alignment = (
        abs(net_score) / total_absolute * 100
        if total_absolute > 0
        else 0
    )

    contradictions = min(bullish, bearish)

    average_confidence = float(
        active["Confidence"].mean()
    )

    evidence_factor = min(
        1.0,
        len(active) / 3
    )

    confidence = int(min(
        98,
        average_confidence * 0.60
        + alignment * 0.25
        + evidence_factor * 15
    ))

    normalized_score = int(max(
        -100,
        min(100, net_score)
    ))

    if normalized_score >= 15:
        direction = "BULLISH"
    elif normalized_score <= -15:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    if alignment >= 75 and len(active) >= 2:
        state = "STRONG ALIGNMENT"
    elif alignment >= 50:
        state = "MODERATE ALIGNMENT"
    elif contradictions > 0:
        state = "CONFLICTING DRIVERS"
    else:
        state = "WEAK ALIGNMENT"

    top = (
        active.assign(
            AbsoluteContribution=active["Contribution"].abs()
        )
        .sort_values(
            "AbsoluteContribution",
            ascending=False
        )
        .head(3)
    )

    driver_names = ", ".join(
        top["Driver"].astype(str).tolist()
    )

    summary = (
        f"{state}: {direction} pressure with "
        f"{alignment:.0f}% driver alignment. "
        f"Main contributors: {driver_names}. "
        f"{contradictions} opposing driver(s) detected."
    )

    details = frame[
        [
            "Driver",
            "Direction",
            "Strength",
            "Confidence",
            "Contribution",
        ]
    ].sort_values(
        "Contribution",
        key=lambda values: values.abs(),
        ascending=False
    ).reset_index(drop=True)

    return {
        "state": state,
        "direction": direction,
        "score": normalized_score,
        "confidence": confidence,
        "alignment": int(round(alignment)),
        "contradictions": contradictions,
        "active_drivers": int(len(active)),
        "summary": summary,
        "details": details,
    }


def render_driver_correlation(report):
    section(
        "Driver Correlation Engine",
        "Alignment and conflict among current market drivers"
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        pe_metric(
            "pe_correlation_state",
            "Correlation State",
            report.get("state", "UNKNOWN")
        )

    with c2:
        st.metric(
            "Combined Direction",
            report.get("direction", "NEUTRAL")
        )

    with c3:
        st.metric(
            "Driver Alignment",
            f"{int(report.get('alignment', 0))}%"
        )

    with c4:
        st.metric(
            "Correlation Confidence",
            f"{int(report.get('confidence', 0))}%"
        )

    details = report.get("details")

    if isinstance(details, pd.DataFrame) and not details.empty:
        st.dataframe(
            details,
            width="stretch",
            hide_index=True,
            column_config={
                "Strength": st.column_config.ProgressColumn(
                    "Strength",
                    min_value=0,
                    max_value=100,
                    format="%d"
                ),
                "Confidence": st.column_config.ProgressColumn(
                    "Confidence",
                    min_value=0,
                    max_value=100,
                    format="%d%%"
                ),
                "Contribution": st.column_config.NumberColumn(
                    "Contribution",
                    format="%+.1f"
                ),
            }
        )
    else:
        st.info(
            "Driver Correlation awaits sufficient evidence."
        )

    if report.get("state") == "CONFLICTING DRIVERS":
        st.warning(report.get("summary", ""))
    else:
        st.info(report.get("summary", ""))

# END PROCUREYE RELEASE 42.3 DEV



# PROCUREYE RELEASE 42.4 DEV — HISTORICAL DRIVER MEMORY

def _driver_memory_connection():
    import sqlite3
    from pathlib import Path

    database = Path(
        "/tmp/procureye_driver_memory.db"
    )

    connection = sqlite3.connect(database)

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS driver_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_utc TEXT NOT NULL,
            dominant_driver TEXT NOT NULL,
            driver_direction TEXT NOT NULL,
            driver_strength INTEGER NOT NULL,
            driver_confidence INTEGER NOT NULL,
            correlation_state TEXT NOT NULL,
            correlation_direction TEXT NOT NULL,
            correlation_alignment INTEGER NOT NULL,
            market_signal TEXT NOT NULL,
            market_score INTEGER NOT NULL,
            brent REAL,
            wti REAL
        )
        """
    )

    connection.commit()
    return connection


def _driver_memory_float(value):
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def record_historical_driver_memory(
    driver_report,
    correlation_report,
    signal,
    score,
    brent,
    wti
):
    from datetime import datetime, timezone

    if not isinstance(driver_report, dict):
        return

    if not isinstance(correlation_report, dict):
        return

    now = datetime.now(timezone.utc)

    dominant_driver = str(
        driver_report.get("dominant_driver", "NONE")
    )

    driver_direction = str(
        driver_report.get("direction", "NEUTRAL")
    )

    driver_strength = int(
        driver_report.get("strength", 0)
    )

    driver_confidence = int(
        driver_report.get("confidence", 0)
    )

    correlation_state = str(
        correlation_report.get("state", "UNKNOWN")
    )

    correlation_direction = str(
        correlation_report.get("direction", "NEUTRAL")
    )

    correlation_alignment = int(
        correlation_report.get("alignment", 0)
    )

    clean_signal = (
        str(signal)
        .replace("🟢", "")
        .replace("🔴", "")
        .replace("🟡", "")
        .strip()
    )

    brent_price = _driver_memory_float(
        brent.get("price")
        if isinstance(brent, dict)
        else None
    )

    wti_price = _driver_memory_float(
        wti.get("price")
        if isinstance(wti, dict)
        else None
    )

    connection = _driver_memory_connection()

    previous = connection.execute(
        """
        SELECT
            timestamp_utc,
            dominant_driver,
            driver_direction,
            correlation_state,
            correlation_direction,
            market_signal,
            market_score
        FROM driver_memory
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    should_insert = previous is None

    if previous is not None:
        try:
            previous_time = datetime.fromisoformat(
                previous[0]
            )
            elapsed_minutes = (
                now - previous_time
            ).total_seconds() / 60
        except Exception:
            elapsed_minutes = 999

        state_changed = any([
            dominant_driver != str(previous[1]),
            driver_direction != str(previous[2]),
            correlation_state != str(previous[3]),
            correlation_direction != str(previous[4]),
            clean_signal != str(previous[5]),
            int(score) != int(previous[6]),
        ])

        should_insert = (
            elapsed_minutes >= 15
            or state_changed
        )

    if should_insert:
        connection.execute(
            """
            INSERT INTO driver_memory (
                timestamp_utc,
                dominant_driver,
                driver_direction,
                driver_strength,
                driver_confidence,
                correlation_state,
                correlation_direction,
                correlation_alignment,
                market_signal,
                market_score,
                brent,
                wti
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now.isoformat(),
                dominant_driver,
                driver_direction,
                driver_strength,
                driver_confidence,
                correlation_state,
                correlation_direction,
                correlation_alignment,
                clean_signal,
                int(score),
                brent_price,
                wti_price,
            )
        )

        connection.commit()

    connection.close()


def build_historical_driver_memory():
    connection = _driver_memory_connection()

    history = pd.read_sql_query(
        """
        SELECT
            timestamp_utc AS "Timestamp UTC",
            dominant_driver AS "Dominant Driver",
            driver_direction AS "Driver Direction",
            driver_strength AS "Strength",
            driver_confidence AS "Driver Confidence",
            correlation_state AS "Correlation State",
            correlation_direction AS "Combined Direction",
            correlation_alignment AS "Alignment",
            market_signal AS "Signal",
            market_score AS "Market Score",
            brent AS "Brent",
            wti AS "WTI"
        FROM driver_memory
        ORDER BY id DESC
        LIMIT 200
        """,
        connection
    )

    frequency = pd.read_sql_query(
        """
        SELECT
            dominant_driver AS "Driver",
            COUNT(*) AS "Observations",
            ROUND(AVG(driver_strength), 1)
                AS "Average Strength",
            ROUND(AVG(driver_confidence), 1)
                AS "Average Confidence",
            ROUND(AVG(correlation_alignment), 1)
                AS "Average Alignment"
        FROM driver_memory
        GROUP BY dominant_driver
        ORDER BY Observations DESC
        LIMIT 10
        """,
        connection
    )

    total = connection.execute(
        "SELECT COUNT(*) FROM driver_memory"
    ).fetchone()[0]

    connection.close()

    if history.empty:
        return {
            "total": 0,
            "main_driver": "NONE",
            "latest_direction": "NEUTRAL",
            "average_alignment": 0,
            "frequency": frequency,
            "history": history,
        }

    main_driver = str(
        history["Dominant Driver"]
        .value_counts()
        .index[0]
    )

    latest_direction = str(
        history.iloc[0]["Combined Direction"]
    )

    average_alignment = int(round(
        pd.to_numeric(
            history["Alignment"],
            errors="coerce"
        ).fillna(0).mean()
    ))

    history["Timestamp UTC"] = pd.to_datetime(
        history["Timestamp UTC"],
        errors="coerce",
        utc=True
    ).dt.strftime(
        "%d %b %Y · %H:%M UTC"
    )

    return {
        "total": int(total),
        "main_driver": main_driver,
        "latest_direction": latest_direction,
        "average_alignment": average_alignment,
        "frequency": frequency,
        "history": history,
    }


def render_historical_driver_memory(memory):
    section(
        "Historical Driver Memory",
        "Observed driver combinations and market states"
    )

    m1, m2, m3, m4 = st.columns(4)

    with m1:
        st.metric(
            "Stored Observations",
            int(memory.get("total", 0))
        )

    with m2:
        st.metric(
            "Historical Main Driver",
            memory.get("main_driver", "NONE")
        )

    with m3:
        st.metric(
            "Latest Direction",
            memory.get(
                "latest_direction",
                "NEUTRAL"
            )
        )

    with m4:
        st.metric(
            "Average Alignment",
            f"{int(memory.get('average_alignment', 0))}%"
        )

    frequency = memory.get("frequency")

    if isinstance(frequency, pd.DataFrame) and not frequency.empty:
        st.dataframe(
            frequency,
            width="stretch",
            hide_index=True
        )

    history = memory.get("history")

    if isinstance(history, pd.DataFrame) and not history.empty:
        with st.expander(
            "Recent driver-memory observations"
        ):
            st.dataframe(
                history.head(25),
                width="stretch",
                hide_index=True
            )
    else:
        st.info(
            "Historical baseline created. "
            "Observations will accumulate after refreshes."
        )

    st.caption(
        "DEV memory uses the current Streamlit runtime "
        "and may reset after a cloud restart."
    )

# END PROCUREYE RELEASE 42.4 DEV



# PROCUREYE RELEASE 42.5 DEV — CONFIDENCE INTELLIGENCE V2

def calculate_confidence_intelligence_v2(
    base_confidence,
    driver_report,
    correlation_report,
    historical_memory,
    brent,
    wti,
    risk
):
    def numeric(value, default=0.0):
        try:
            if value is None or pd.isna(value):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    if isinstance(base_confidence, dict):
        base_score = numeric(
            base_confidence.get("score", 0)
        )
    else:
        base_score = numeric(base_confidence)

    driver_score = numeric(
        driver_report.get("confidence", 0)
        if isinstance(driver_report, dict)
        else 0
    )

    driver_strength = numeric(
        driver_report.get("strength", 0)
        if isinstance(driver_report, dict)
        else 0
    )

    correlation_confidence = numeric(
        correlation_report.get("confidence", 0)
        if isinstance(correlation_report, dict)
        else 0
    )

    alignment = numeric(
        correlation_report.get("alignment", 0)
        if isinstance(correlation_report, dict)
        else 0
    )

    contradictions = int(
        correlation_report.get("contradictions", 0)
        if isinstance(correlation_report, dict)
        else 0
    )

    observations = int(
        historical_memory.get("total", 0)
        if isinstance(historical_memory, dict)
        else 0
    )

    historical_alignment = numeric(
        historical_memory.get(
            "average_alignment",
            0
        )
        if isinstance(historical_memory, dict)
        else 0
    )

    brent_trend = str(
        brent.get("trend", "UNKNOWN")
        if isinstance(brent, dict)
        else "UNKNOWN"
    ).upper()

    wti_trend = str(
        wti.get("trend", "UNKNOWN")
        if isinstance(wti, dict)
        else "UNKNOWN"
    ).upper()

    trend_agreement = (
        100
        if brent_trend == wti_trend
        and brent_trend not in {
            "UNKNOWN",
            "NEUTRAL",
        }
        else 55
        if brent_trend == wti_trend
        else 25
    )

    risk_text = str(risk).upper()

    risk_penalty = {
        "LOW": 0,
        "MEDIUM": 5,
        "HIGH": 12,
    }.get(risk_text, 7)

    contradiction_penalty = min(
        24,
        contradictions * 12
    )

    historical_reliability = min(
        100,
        observations * 8
    )

    components = {
        "Base Confidence": round(base_score, 1),
        "Driver Confidence": round(driver_score, 1),
        "Driver Strength": round(driver_strength, 1),
        "Correlation Confidence": round(
            correlation_confidence,
            1
        ),
        "Driver Alignment": round(alignment, 1),
        "Trend Agreement": round(
            trend_agreement,
            1
        ),
        "Historical Reliability": round(
            historical_reliability,
            1
        ),
        "Historical Alignment": round(
            historical_alignment,
            1
        ),
    }

    weighted_score = (
        base_score * 0.24
        + driver_score * 0.15
        + driver_strength * 0.10
        + correlation_confidence * 0.15
        + alignment * 0.14
        + trend_agreement * 0.10
        + historical_reliability * 0.07
        + historical_alignment * 0.05
        - risk_penalty
        - contradiction_penalty
    )

    score = int(
        max(
            0,
            min(100, round(weighted_score))
        )
    )

    if score >= 80:
        level = "VERY HIGH"
    elif score >= 65:
        level = "HIGH"
    elif score >= 50:
        level = "MEDIUM"
    elif score >= 35:
        level = "LOW"
    else:
        level = "VERY LOW"

    strongest_component = max(
        components,
        key=components.get
    )

    weakest_component = min(
        components,
        key=components.get
    )

    penalties = []

    if risk_penalty:
        penalties.append(
            f"market risk -{risk_penalty}"
        )

    if contradiction_penalty:
        penalties.append(
            f"driver contradiction -{contradiction_penalty}"
        )

    penalty_text = (
        ", ".join(penalties)
        if penalties
        else "no material penalties"
    )

    explanation = (
        f"Confidence {score}% ({level}). "
        f"Strongest component: {strongest_component} "
        f"at {components[strongest_component]:.0f}%. "
        f"Weakest component: {weakest_component} "
        f"at {components[weakest_component]:.0f}%. "
        f"Adjustments: {penalty_text}."
    )

    breakdown = pd.DataFrame([
        {
            "Component": component,
            "Score": value,
        }
        for component, value
        in components.items()
    ])

    return {
        "score": score,
        "level": level,
        "risk_penalty": risk_penalty,
        "contradiction_penalty":
            contradiction_penalty,
        "observations": observations,
        "strongest_component":
            strongest_component,
        "weakest_component":
            weakest_component,
        "explanation": explanation,
        "breakdown": breakdown,
    }


def render_confidence_intelligence_v2(report):
    section(
        "Confidence Intelligence v2",
        "Multi-factor reliability of the current market decision"
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            "Confidence v2",
            f"{int(report.get('score', 0))}%"
        )

    with c2:
        st.metric(
            "Confidence Level",
            report.get("level", "UNKNOWN")
        )

    with c3:
        st.metric(
            "Historical Samples",
            int(report.get("observations", 0))
        )

    with c4:
        total_penalty = (
            int(report.get("risk_penalty", 0))
            + int(
                report.get(
                    "contradiction_penalty",
                    0
                )
            )
        )

        st.metric(
            "Total Penalty",
            f"-{total_penalty}"
        )

    breakdown = report.get("breakdown")

    if (
        isinstance(breakdown, pd.DataFrame)
        and not breakdown.empty
    ):
        st.dataframe(
            breakdown,
            width="stretch",
            hide_index=True,
            column_config={
                "Score":
                    st.column_config.ProgressColumn(
                        "Score",
                        min_value=0,
                        max_value=100,
                        format="%.1f"
                    )
            }
        )

    st.info(
        report.get(
            "explanation",
            "Confidence explanation unavailable."
        )
    )

    st.caption(
        "Confidence v2 combines market confidence, "
        "driver evidence, correlation, trend agreement, "
        "historical memory, risk and contradictions."
    )

# END PROCUREYE RELEASE 42.5 DEV



# PROCUREYE RELEASE 42.6 DEV — EXPLAINABLE DECISION INTELLIGENCE 2.0

def build_explainable_decision_v2(
    signal,
    score,
    risk,
    regime,
    brent,
    wti,
    driver_report,
    correlation_report,
    historical_memory,
    confidence_v2,
    ranking
):
    def numeric(value, default=0.0):
        try:
            if value is None or pd.isna(value):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    clean_signal = (
        str(signal)
        .replace("🟢", "")
        .replace("🔴", "")
        .replace("🟡", "")
        .strip()
        .upper()
    )

    brent_trend = str(
        brent.get("trend", "UNKNOWN")
        if isinstance(brent, dict)
        else "UNKNOWN"
    ).upper()

    wti_trend = str(
        wti.get("trend", "UNKNOWN")
        if isinstance(wti, dict)
        else "UNKNOWN"
    ).upper()

    brent_momentum = numeric(
        brent.get("momentum", 0)
        if isinstance(brent, dict)
        else 0
    )

    wti_momentum = numeric(
        wti.get("momentum", 0)
        if isinstance(wti, dict)
        else 0
    )

    dominant_driver = str(
        driver_report.get(
            "dominant_driver",
            "NONE"
        )
        if isinstance(driver_report, dict)
        else "NONE"
    )

    driver_direction = str(
        driver_report.get(
            "direction",
            "NEUTRAL"
        )
        if isinstance(driver_report, dict)
        else "NEUTRAL"
    ).upper()

    driver_strength = int(
        driver_report.get("strength", 0)
        if isinstance(driver_report, dict)
        else 0
    )

    driver_confidence = int(
        driver_report.get("confidence", 0)
        if isinstance(driver_report, dict)
        else 0
    )

    correlation_state = str(
        correlation_report.get(
            "state",
            "UNKNOWN"
        )
        if isinstance(correlation_report, dict)
        else "UNKNOWN"
    )

    combined_direction = str(
        correlation_report.get(
            "direction",
            "NEUTRAL"
        )
        if isinstance(correlation_report, dict)
        else "NEUTRAL"
    ).upper()

    alignment = int(
        correlation_report.get(
            "alignment",
            0
        )
        if isinstance(correlation_report, dict)
        else 0
    )

    contradictions = int(
        correlation_report.get(
            "contradictions",
            0
        )
        if isinstance(correlation_report, dict)
        else 0
    )

    historical_samples = int(
        historical_memory.get("total", 0)
        if isinstance(historical_memory, dict)
        else 0
    )

    historical_driver = str(
        historical_memory.get(
            "main_driver",
            "NONE"
        )
        if isinstance(historical_memory, dict)
        else "NONE"
    )

    historical_alignment = int(
        historical_memory.get(
            "average_alignment",
            0
        )
        if isinstance(historical_memory, dict)
        else 0
    )

    confidence_score = int(
        confidence_v2.get("score", 0)
        if isinstance(confidence_v2, dict)
        else 0
    )

    confidence_level = str(
        confidence_v2.get(
            "level",
            "UNKNOWN"
        )
        if isinstance(confidence_v2, dict)
        else "UNKNOWN"
    )

    evidence = []
    risks = []
    invalidation = []

    if brent_trend not in {"UNKNOWN", "NEUTRAL"}:
        evidence.append({
            "Factor": "Brent trend",
            "Direction": brent_trend,
            "Evidence": (
                f"Brent trend is {brent_trend.lower()}."
            ),
            "Weight": 18,
        })

    if wti_trend not in {"UNKNOWN", "NEUTRAL"}:
        evidence.append({
            "Factor": "WTI trend",
            "Direction": wti_trend,
            "Evidence": (
                f"WTI trend is {wti_trend.lower()}."
            ),
            "Weight": 16,
        })

    momentum_direction = (
        "BULLISH"
        if brent_momentum > 0
        and wti_momentum > 0
        else "BEARISH"
        if brent_momentum < 0
        and wti_momentum < 0
        else "MIXED"
    )

    evidence.append({
        "Factor": "Momentum",
        "Direction": momentum_direction,
        "Evidence": (
            f"Brent momentum {brent_momentum:+.2f}% · "
            f"WTI momentum {wti_momentum:+.2f}%."
        ),
        "Weight": 18,
    })

    evidence.append({
        "Factor": dominant_driver,
        "Direction": driver_direction,
        "Evidence": (
            f"Dominant driver strength {driver_strength}/100 "
            f"with confidence {driver_confidence}%."
        ),
        "Weight": 20,
    })

    evidence.append({
        "Factor": "Driver correlation",
        "Direction": combined_direction,
        "Evidence": (
            f"{correlation_state}; alignment {alignment}%."
        ),
        "Weight": 16,
    })

    if historical_samples > 0:
        evidence.append({
            "Factor": "Historical memory",
            "Direction": combined_direction,
            "Evidence": (
                f"{historical_samples} observations; "
                f"main driver {historical_driver}; "
                f"average alignment {historical_alignment}%."
            ),
            "Weight": 12,
        })

    top_headline = "No ranked headline available."
    top_direction = "NEUTRAL"

    if (
        isinstance(ranking, pd.DataFrame)
        and not ranking.empty
    ):
        leader = ranking.iloc[0]

        top_headline = str(
            leader.get(
                "Headline",
                top_headline
            )
        )

        top_direction = str(
            leader.get(
                "Direction",
                "NEUTRAL"
            )
        ).upper()

        evidence.append({
            "Factor": "Top market mover",
            "Direction": top_direction,
            "Evidence": top_headline,
            "Weight": 14,
        })

    if str(risk).upper() == "HIGH":
        risks.append(
            "Market volatility and risk conditions are high."
        )

    if contradictions > 0:
        risks.append(
            f"{contradictions} opposing driver(s) reduce signal reliability."
        )

    if alignment < 50:
        risks.append(
            "Driver alignment is below 50%."
        )

    if confidence_score < 50:
        risks.append(
            "Confidence Intelligence v2 is below 50%."
        )

    if brent_trend != wti_trend:
        risks.append(
            "Brent and WTI trends are not fully aligned."
        )

    if historical_samples < 5:
        risks.append(
            "Historical driver memory is still limited."
        )

    if clean_signal == "LONG":
        invalidation.extend([
            "Brent and WTI momentum turning negative.",
            "Dominant driver changing to BEARISH.",
            "Driver alignment falling below 45%.",
        ])
    elif clean_signal == "SHORT":
        invalidation.extend([
            "Brent and WTI momentum turning positive.",
            "Dominant driver changing to BULLISH.",
            "Driver alignment falling below 45%.",
        ])
    else:
        invalidation.extend([
            "Trend, momentum and drivers becoming strongly aligned.",
            "Confidence Intelligence rising above 65%.",
        ])

    matching_direction = {
        "LONG": "BULLISH",
        "SHORT": "BEARISH",
        "WAIT": "NEUTRAL",
    }.get(clean_signal, "NEUTRAL")

    supportive = sum(
        1
        for item in evidence
        if item["Direction"] == matching_direction
    )

    opposing = sum(
        1
        for item in evidence
        if (
            item["Direction"]
            not in {
                matching_direction,
                "NEUTRAL",
                "MIXED",
                "UNKNOWN",
            }
        )
    )

    weighted_support = sum(
        item["Weight"]
        for item in evidence
        if item["Direction"] == matching_direction
    )

    weighted_opposition = sum(
        item["Weight"]
        for item in evidence
        if (
            item["Direction"]
            not in {
                matching_direction,
                "NEUTRAL",
                "MIXED",
                "UNKNOWN",
            }
        )
    )

    net_explanation_score = int(
        max(
            0,
            min(
                100,
                50
                + weighted_support
                - weighted_opposition
                + (confidence_score - 50) * 0.30
            )
        )
    )

    if clean_signal == "WAIT":
        executive_summary = (
            f"PROCUREYE maintains WAIT with Market Score "
            f"{int(score)}/100. Evidence is not sufficiently "
            f"aligned for a directional position."
        )
    else:
        executive_summary = (
            f"PROCUREYE indicates {clean_signal} with Market Score "
            f"{int(score)}/100 and Confidence v2 "
            f"{confidence_score}% ({confidence_level}). "
            f"The dominant driver is {dominant_driver} "
            f"({driver_direction}) and combined driver alignment "
            f"is {alignment}%."
        )

    evidence_table = pd.DataFrame(evidence)

    return {
        "signal": clean_signal,
        "executive_summary": executive_summary,
        "confidence_score": confidence_score,
        "confidence_level": confidence_level,
        "explanation_score": net_explanation_score,
        "supportive_factors": supportive,
        "opposing_factors": opposing,
        "evidence": evidence_table,
        "risks": risks,
        "invalidation": invalidation,
        "top_headline": top_headline,
        "regime": str(regime),
        "risk": str(risk),
    }


def render_explainable_decision_v2(report):
    section(
        "Explainable Decision Intelligence 2.0",
        "Why the signal exists, what supports it and what could invalidate it"
    )

    x1, x2, x3, x4 = st.columns(4)

    with x1:
        st.metric(
            "Decision",
            report.get("signal", "WAIT")
        )

    with x2:
        st.metric(
            "Confidence v2",
            f"{int(report.get('confidence_score', 0))}%"
        )

    with x3:
        st.metric(
            "Explanation Score",
            f"{int(report.get('explanation_score', 0))}/100"
        )

    with x4:
        st.metric(
            "Support / Opposition",
            (
                f"{int(report.get('supportive_factors', 0))}"
                f" / "
                f"{int(report.get('opposing_factors', 0))}"
            )
        )

    st.info(
        report.get(
            "executive_summary",
            "Decision explanation unavailable."
        )
    )

    evidence = report.get("evidence")

    if (
        isinstance(evidence, pd.DataFrame)
        and not evidence.empty
    ):
        st.markdown("#### Decision evidence")

        st.dataframe(
            evidence,
            width="stretch",
            hide_index=True,
            column_config={
                "Weight":
                    st.column_config.ProgressColumn(
                        "Weight",
                        min_value=0,
                        max_value=25,
                        format="%d"
                    )
            }
        )

    risks = report.get("risks", [])

    st.markdown("#### Principal risks")

    if risks:
        for item in risks:
            st.warning(item)
    else:
        st.success(
            "No material contradiction or reliability warning detected."
        )

    invalidation = report.get(
        "invalidation",
        []
    )

    with st.expander(
        "Signal invalidation conditions"
    ):
        for item in invalidation:
            st.markdown(f"- {item}")

    st.caption(
        "Decision-support explanation only. "
        "PROCUREYE does not execute trades."
    )

# END PROCUREYE RELEASE 42.6 DEV



# PROCUREYE RELEASE 43.0 DEV — PREDICTIVE INTELLIGENCE

def calculate_predictive_intelligence(
    signal, score, brent, wti, risk,
    adaptive_news, driver_report,
    correlation_report, confidence_v2
):
    import math

    def n(v, default=0.0):
        try:
            if v is None or pd.isna(v):
                return default
            return float(v)
        except Exception:
            return default

    def d(v):
        v = str(v).upper()
        if v in ("BULLISH", "LONG"):
            return 1.0
        if v in ("BEARISH", "SHORT"):
            return -1.0
        return 0.0

    clean_signal = (
        str(signal)
        .replace("🟢", "")
        .replace("🔴", "")
        .replace("🟡", "")
        .strip()
        .upper()
    )

    market_score = n(score, 50)

    bt = d(brent.get("trend", "UNKNOWN"))
    wt = d(wti.get("trend", "UNKNOWN"))

    bm = n(brent.get("momentum", 0))
    wm = n(wti.get("momentum", 0))

    dd = d(driver_report.get("direction", "NEUTRAL"))
    ds = n(driver_report.get("strength", 0))
    dc = n(driver_report.get("confidence", 0))

    cd = d(correlation_report.get("direction", "NEUTRAL"))
    align = n(correlation_report.get("alignment", 0))
    cc = n(correlation_report.get("confidence", 0))
    contradictions = n(correlation_report.get("contradictions", 0))

    news = n(adaptive_news.get("effective_score", 0))
    confidence = n(confidence_v2.get("score", 0))

    score_p = max(-1, min(1, (market_score - 50) / 50))
    trend_p = (bt + wt) / 2
    momentum_p = max(-1, min(1, (bm + wm) / 20))
    driver_p = dd * ds * dc / 10000
    correlation_p = cd * align * cc / 10000
    news_p = max(-1, min(1, news / 50))

    pressure = (
        score_p * 0.28 +
        trend_p * 0.19 +
        momentum_p * 0.17 +
        driver_p * 0.15 +
        correlation_p * 0.12 +
        news_p * 0.09
    )

    pressure += {
        "LONG": 0.06,
        "SHORT": -0.06,
        "WAIT": 0.0
    }.get(clean_signal, 0.0)

    risk_p = {
        "LOW": 0.03,
        "MEDIUM": 0.08,
        "HIGH": 0.15
    }.get(str(risk).upper(), 0.08)

    uncertainty = (
        ((100 - confidence) / 100) * 0.38 +
        ((100 - align) / 100) * 0.27 +
        min(1, contradictions / 3) * 0.20 +
        risk_p
    )

    logits = {
        "LONG": pressure * 3.4,
        "WAIT": uncertainty * 2.5 - abs(pressure) * 1.4,
        "SHORT": -pressure * 3.4
    }

    maximum = max(logits.values())

    raw = {
        k: math.exp(v - maximum)
        for k, v in logits.items()
    }

    total = sum(raw.values())

    probs = {
        k: 100 * v / total
        for k, v in raw.items()
    }

    prediction = max(probs, key=probs.get)

    ordered = sorted(probs.values(), reverse=True)
    spread = ordered[0] - ordered[1]
    probability = probs[prediction]

    conviction = (
        "HIGH"
        if probability >= 65 and spread >= 15
        else "MEDIUM"
        if probability >= 50 and spread >= 8
        else "LOW"
    )

    table = pd.DataFrame([
        {"State": k, "Probability": round(v, 1)}
        for k, v in probs.items()
    ]).sort_values(
        "Probability",
        ascending=False
    ).reset_index(drop=True)

    return {
        "prediction": prediction,
        "probability": round(probability, 1),
        "long": round(probs["LONG"], 1),
        "wait": round(probs["WAIT"], 1),
        "short": round(probs["SHORT"], 1),
        "spread": round(spread, 1),
        "conviction": conviction,
        "pressure": round(pressure, 3),
        "uncertainty": round(uncertainty, 3),
        "table": table
    }


def render_predictive_intelligence(report):

    section(
        "Predictive Intelligence",
        "Live probability distribution for LONG, WAIT and SHORT"
    )

    a, b, c, d = st.columns(4)

    with a:
        st.metric("Prediction", report["prediction"])

    with b:
        st.metric(
            "Leading Probability",
            f"{report['probability']:.1f}%"
        )

    with c:
        st.metric("Conviction", report["conviction"])

    with d:
        st.metric(
            "Probability Spread",
            f"{report['spread']:.1f} pt"
        )

    st.dataframe(
        report["table"],
        width="stretch",
        hide_index=True,
        column_config={
            "Probability": st.column_config.ProgressColumn(
                "Probability",
                min_value=0,
                max_value=100,
                format="%.1f%%"
            )
        }
    )

    st.info(
        f"LONG {report['long']:.1f}% · "
        f"WAIT {report['wait']:.1f}% · "
        f"SHORT {report['short']:.1f}%"
    )

    st.caption(
        "Recalculated on every refresh from market price, "
        "trend, momentum, current news, drivers, "
        "correlation, risk and Confidence v2."
    )

# END PROCUREYE RELEASE 43.0 DEV


# ============================================================
# PROCUREYE RELEASE 44.0 DEV — SCENARIO ENGINE
# ============================================================

def build_scenario_engine(
    predictive,
    brent,
    wti,
    driver_report,
    correlation_report,
    risk
):
    import math

    def num(value, default=0.0):
        try:
            if value is None or pd.isna(value):
                return default
            return float(value)
        except Exception:
            return default

    def price_band(price, volatility, scenario):

        if not price or price <= 0:
            return "N/A"

        volatility = max(
            10,
            min(120, volatility)
        )

        sigma = (
            volatility / 100
            / math.sqrt(252)
            * math.sqrt(3)
        )

        sigma = max(
            0.012,
            min(0.10, sigma)
        )

        if scenario == "BULL":

            low = price * (
                1 + sigma * 0.30
            )

            high = price * (
                1 + sigma
            )

        elif scenario == "BEAR":

            low = price * (
                1 - sigma
            )

            high = price * (
                1 - sigma * 0.30
            )

        else:

            low = price * (
                1 - sigma * 0.30
            )

            high = price * (
                1 + sigma * 0.30
            )

        return f"${low:.2f} - ${high:.2f}"


    brent_price = num(
        brent.get("price")
        if isinstance(brent, dict)
        else None
    )

    wti_price = num(
        wti.get("price")
        if isinstance(wti, dict)
        else None
    )

    brent_vol = num(
        brent.get("volatility", 40)
        if isinstance(brent, dict)
        else 40,
        40
    )

    wti_vol = num(
        wti.get("volatility", brent_vol)
        if isinstance(wti, dict)
        else brent_vol,
        brent_vol
    )

    long_p = num(
        predictive.get("long", 0)
    )

    wait_p = num(
        predictive.get("wait", 0)
    )

    short_p = num(
        predictive.get("short", 0)
    )

    dominant_driver = str(
        driver_report.get(
            "dominant_driver",
            "NONE"
        )
    )

    driver_direction = str(
        driver_report.get(
            "direction",
            "NEUTRAL"
        )
    ).upper()

    alignment = int(
        correlation_report.get(
            "alignment",
            0
        )
    )

    correlation_direction = str(
        correlation_report.get(
            "direction",
            "NEUTRAL"
        )
    ).upper()

    bull_trigger = (
        "Positive momentum + bullish news + "
        "increasing driver alignment."
    )

    bear_trigger = (
        "Negative momentum + bearish news + "
        "persistent negative driver alignment."
    )

    base_trigger = (
        "Mixed evidence or insufficient "
        "directional confirmation."
    )

    if driver_direction == "BULLISH":
        bull_trigger += (
            f" Current driver: {dominant_driver}."
        )

    if driver_direction == "BEARISH":
        bear_trigger += (
            f" Current driver: {dominant_driver}."
        )

    scenarios = pd.DataFrame([
        {
            "Scenario": "BULL",
            "Probability": round(long_p, 1),
            "Signal": "LONG",
            "Brent 24-72h": price_band(
                brent_price,
                brent_vol,
                "BULL"
            ),
            "WTI 24-72h": price_band(
                wti_price,
                wti_vol,
                "BULL"
            ),
            "Trigger": bull_trigger
        },
        {
            "Scenario": "BASE",
            "Probability": round(wait_p, 1),
            "Signal": "WAIT",
            "Brent 24-72h": price_band(
                brent_price,
                brent_vol,
                "BASE"
            ),
            "WTI 24-72h": price_band(
                wti_price,
                wti_vol,
                "BASE"
            ),
            "Trigger": base_trigger
        },
        {
            "Scenario": "BEAR",
            "Probability": round(short_p, 1),
            "Signal": "SHORT",
            "Brent 24-72h": price_band(
                brent_price,
                brent_vol,
                "BEAR"
            ),
            "WTI 24-72h": price_band(
                wti_price,
                wti_vol,
                "BEAR"
            ),
            "Trigger": bear_trigger
        }
    ])

    scenarios = scenarios.sort_values(
        "Probability",
        ascending=False
    ).reset_index(drop=True)

    leader = scenarios.iloc[0]

    return {
        "leading_scenario":
            str(leader["Scenario"]),
        "leading_signal":
            str(leader["Signal"]),
        "probability":
            float(leader["Probability"]),
        "dominant_driver":
            dominant_driver,
        "driver_direction":
            driver_direction,
        "alignment":
            alignment,
        "correlation_direction":
            correlation_direction,
        "risk":
            str(risk),
        "scenarios":
            scenarios
    }


def render_scenario_engine(report):

    section(
        "Scenario Engine",
        "BULL, BASE and BEAR scenarios for the next 24-72 hours"
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            "Leading Scenario",
            report.get(
                "leading_scenario",
                "BASE"
            )
        )

    with c2:
        st.metric(
            "Expected Signal",
            report.get(
                "leading_signal",
                "WAIT"
            )
        )

    with c3:
        st.metric(
            "Probability",
            f"{report.get('probability', 0):.1f}%"
        )

    with c4:
        st.metric(
            "Driver Alignment",
            f"{report.get('alignment', 0)}%"
        )

    scenarios = report.get(
        "scenarios"
    )

    if (
        isinstance(scenarios, pd.DataFrame)
        and not scenarios.empty
    ):

        st.dataframe(
            scenarios,
            width="stretch",
            hide_index=True,
            column_config={
                "Probability":
                    st.column_config.ProgressColumn(
                        "Probability",
                        min_value=0,
                        max_value=100,
                        format="%.1f%%"
                    )
            }
        )

    st.info(
        f"Dominant driver: "
        f"{report.get('dominant_driver', 'NONE')} · "
        f"{report.get('driver_direction', 'NEUTRAL')} · "
        f"Correlation: "
        f"{report.get('correlation_direction', 'NEUTRAL')}"
    )

    st.caption(
        "Probabilities recalculate at every refresh. "
        "Price bands are volatility-based scenarios, "
        "not guaranteed targets."
    )

# END PROCUREYE RELEASE 44.0 DEV


# ============================================================
# PROCUREYE RELEASE 45.0 DEV — DRIVER FORECAST ENGINE
# ============================================================

def build_driver_forecast(
    ranking,
    driver_report,
    correlation_report,
    predictive
):
    def num(v, default=0.0):
        try:
            if v is None or pd.isna(v):
                return default
            return float(v)
        except Exception:
            return default

    empty = {
        "forecast_driver": "NONE",
        "direction": "NEUTRAL",
        "probability": 0.0,
        "current_driver": "NONE",
        "horizon": "24-72h",
        "drivers": pd.DataFrame()
    }

    if not isinstance(ranking, pd.DataFrame) or ranking.empty:
        return empty

    frame = ranking.copy()

    defaults = {
        "Driver": "OIL MARKET",
        "Direction": "NEUTRAL",
        "Ranking Score": 0,
        "Confidence": 50
    }

    for col, default in defaults.items():
        if col not in frame.columns:
            frame[col] = default

    frame["Ranking Score"] = pd.to_numeric(
        frame["Ranking Score"],
        errors="coerce"
    ).fillna(0)

    frame["Confidence"] = pd.to_numeric(
        frame["Confidence"],
        errors="coerce"
    ).fillna(50)

    frame["Direction"] = (
        frame["Direction"]
        .astype(str)
        .str.upper()
    )

    frame["Forecast Weight"] = (
        frame["Ranking Score"] * 0.65
        + frame["Confidence"] * 0.35
    )

    grouped = (
        frame.groupby(
            ["Driver", "Direction"],
            as_index=False
        )
        .agg(
            Evidence=("Driver", "size"),
            Forecast_Score=("Forecast Weight", "sum"),
            Avg_Confidence=("Confidence", "mean")
        )
    )

    current_driver = str(
        driver_report.get(
            "dominant_driver",
            "NONE"
        )
        if isinstance(driver_report, dict)
        else "NONE"
    )

    current_direction = str(
        driver_report.get(
            "direction",
            "NEUTRAL"
        )
        if isinstance(driver_report, dict)
        else "NEUTRAL"
    ).upper()

    correlation_direction = str(
        correlation_report.get(
            "direction",
            "NEUTRAL"
        )
        if isinstance(correlation_report, dict)
        else "NEUTRAL"
    ).upper()

    alignment = num(
        correlation_report.get(
            "alignment",
            0
        )
        if isinstance(correlation_report, dict)
        else 0
    )

    prediction = str(
        predictive.get(
            "prediction",
            "WAIT"
        )
        if isinstance(predictive, dict)
        else "WAIT"
    ).upper()

    predictive_direction = {
        "LONG": "BULLISH",
        "SHORT": "BEARISH",
        "WAIT": "NEUTRAL"
    }.get(prediction, "NEUTRAL")

    def bonus(row):
        value = 0.0

        if str(row["Driver"]) == current_driver:
            value += 12.0

        if str(row["Direction"]) == current_direction:
            value += 6.0

        if str(row["Direction"]) == correlation_direction:
            value += alignment * 0.10

        if str(row["Direction"]) == predictive_direction:
            value += 8.0

        return value

    grouped["Context Bonus"] = grouped.apply(
        bonus,
        axis=1
    )

    grouped["Forecast Score"] = (
        grouped["Forecast_Score"]
        + grouped["Context Bonus"]
    )

    grouped = grouped.sort_values(
        ["Forecast Score", "Evidence"],
        ascending=False
    ).reset_index(drop=True)

    total = grouped["Forecast Score"].clip(
        lower=0
    ).sum()

    if total > 0:
        grouped["Probability"] = (
            grouped["Forecast Score"]
            .clip(lower=0)
            / total
            * 100
        )
    else:
        grouped["Probability"] = 0.0

    grouped["Probability"] = grouped[
        "Probability"
    ].round(1)

    grouped["Avg Confidence"] = grouped[
        "Avg_Confidence"
    ].round(0).astype(int)

    grouped = grouped.rename(
        columns={
            "Forecast_Score": "Raw Evidence Score"
        }
    )

    leader = grouped.iloc[0]

    return {
        "forecast_driver":
            str(leader["Driver"]),
        "direction":
            str(leader["Direction"]),
        "probability":
            float(leader["Probability"]),
        "current_driver":
            current_driver,
        "horizon":
            "24-72h",
        "drivers":
            grouped[
                [
                    "Driver",
                    "Direction",
                    "Probability",
                    "Evidence",
                    "Avg Confidence"
                ]
            ].head(8)
    }


def render_driver_forecast(report):

    section(
        "Driver Forecast",
        "Most likely dominant market driver over the next 24-72 hours"
    )

    f1, f2, f3, f4 = st.columns(4)

    with f1:
        st.metric(
            "Likely Next Driver",
            report.get(
                "forecast_driver",
                "NONE"
            )
        )

    with f2:
        st.metric(
            "Expected Direction",
            report.get(
                "direction",
                "NEUTRAL"
            )
        )

    with f3:
        st.metric(
            "Driver Probability",
            f"{report.get('probability', 0):.1f}%"
        )

    with f4:
        st.metric(
            "Forecast Horizon",
            report.get(
                "horizon",
                "24-72h"
            )
        )

    drivers = report.get("drivers")

    if isinstance(drivers, pd.DataFrame) and not drivers.empty:
        st.dataframe(
            drivers,
            width="stretch",
            hide_index=True,
            column_config={
                "Probability":
                    st.column_config.ProgressColumn(
                        "Probability",
                        min_value=0,
                        max_value=100,
                        format="%.1f%%"
                    ),
                "Avg Confidence":
                    st.column_config.ProgressColumn(
                        "Avg Confidence",
                        min_value=0,
                        max_value=100,
                        format="%d%%"
                    )
            }
        )

    st.info(
        f"Current driver: "
        f"{report.get('current_driver', 'NONE')} · "
        f"Likely next dominant driver: "
        f"{report.get('forecast_driver', 'NONE')}."
    )

    st.caption(
        "Forecast recalculates at every refresh from current "
        "market-moving news, ranking, driver strength, "
        "correlation and Predictive Intelligence."
    )

# END PROCUREYE RELEASE 45.0 DEV


# ============================================================
# PROCUREYE RELEASE 46.0 DEV — PREDICTION ARCHIVE
# ============================================================

def record_prediction_archive(
    predictive,
    scenario,
    forecast,
    driver_report,
    signal,
    score,
    confidence,
    risk,
    regime,
    brent,
    wti
):
    from pathlib import Path
    from datetime import datetime, timezone

    file = Path(
        "/tmp/procureye_prediction_history.csv"
    )

    now = datetime.now(timezone.utc)

    def num(value, default=0.0):
        try:
            if value is None or pd.isna(value):
                return default
            return float(value)
        except Exception:
            return default

    def clean(value):
        return (
            str(value)
            .replace("🟢", "")
            .replace("🔴", "")
            .replace("🟡", "")
            .strip()
            .upper()
        )

    row = {
        "timestamp_utc": now.isoformat(),
        "release": "46.0",

        "signal": clean(signal),
        "market_score": int(num(score)),

        "confidence_v2": num(
            confidence.get("score", 0)
            if isinstance(confidence, dict)
            else 0
        ),

        "risk": str(risk),
        "regime": str(regime),

        "prediction": str(
            predictive.get("prediction", "WAIT")
        ),

        "long_probability": num(
            predictive.get("long", 0)
        ),

        "wait_probability": num(
            predictive.get("wait", 0)
        ),

        "short_probability": num(
            predictive.get("short", 0)
        ),

        "prediction_probability": num(
            predictive.get("probability", 0)
        ),

        "scenario": str(
            scenario.get(
                "leading_scenario",
                "BASE"
            )
        ),

        "scenario_probability": num(
            scenario.get("probability", 0)
        ),

        "dominant_driver": str(
            driver_report.get(
                "dominant_driver",
                "NONE"
            )
        ),

        "driver_direction": str(
            driver_report.get(
                "direction",
                "NEUTRAL"
            )
        ),

        "forecast_driver": str(
            forecast.get(
                "forecast_driver",
                "NONE"
            )
        ),

        "forecast_direction": str(
            forecast.get(
                "direction",
                "NEUTRAL"
            )
        ),

        "forecast_probability": num(
            forecast.get(
                "probability",
                0
            )
        ),

        "brent": num(
            brent.get("price")
            if isinstance(brent, dict)
            else None
        ),

        "wti": num(
            wti.get("price")
            if isinstance(wti, dict)
            else None
        )
    }

    if file.exists():
        try:
            history = pd.read_csv(file)
        except Exception:
            history = pd.DataFrame()
    else:
        history = pd.DataFrame()

    store = True

    if not history.empty:

        try:
            last = history.iloc[-1]

            last_time = pd.to_datetime(
                last["timestamp_utc"],
                utc=True
            )

            elapsed = (
                now
                - last_time.to_pydatetime()
            ).total_seconds() / 60

            changed = any([
                str(last.get("prediction"))
                    != row["prediction"],

                str(last.get("scenario"))
                    != row["scenario"],

                str(last.get("dominant_driver"))
                    != row["dominant_driver"],

                str(last.get("forecast_driver"))
                    != row["forecast_driver"],

                int(num(last.get("market_score")))
                    != row["market_score"]
            ])

            store = (
                elapsed >= 15
                or changed
            )

        except Exception:
            store = True

    if store:

        history = pd.concat(
            [
                history,
                pd.DataFrame([row])
            ],
            ignore_index=True
        )

        history.to_csv(
            file,
            index=False
        )

    return {
        "stored": store,
        "rows": len(history),
        "file": str(file)
    }

# END PROCUREYE RELEASE 46.0 DEV


# ============================================================
# PROCUREYE RELEASE 46.1 DEV — OUTCOME VALIDATION
# ============================================================

def validate_prediction_outcomes(
    brent,
    wti,
    minimum_age_hours=24
):
    from pathlib import Path
    from datetime import datetime, timezone

    file = Path("/tmp/procureye_prediction_history.csv")

    result = {
        "validated_now": 0,
        "total_validated": 0,
        "total_predictions": 0,
        "accuracy": 0.0,
        "latest_result": "WAITING"
    }

    if not file.exists():
        return result

    try:
        history = pd.read_csv(file)
    except Exception:
        return result

    if history.empty:
        return result

    result["total_predictions"] = len(history)

    required_columns = {
        "outcome_validated": False,
        "outcome_timestamp_utc": "",
        "brent_return_pct": None,
        "wti_return_pct": None,
        "market_return_pct": None,
        "realized_state": "",
        "prediction_correct": None,
        "brier_score": None
    }

    for col, default in required_columns.items():
        if col not in history.columns:
            history[col] = default

    def num(v, default=0.0):
        try:
            if v is None or pd.isna(v):
                return default
            return float(v)
        except Exception:
            return default

    current_brent = num(
        brent.get("price")
        if isinstance(brent, dict)
        else None
    )

    current_wti = num(
        wti.get("price")
        if isinstance(wti, dict)
        else None
    )

    if current_brent <= 0 or current_wti <= 0:
        return result

    now = datetime.now(timezone.utc)
    validated_now = 0

    for idx, row in history.iterrows():

        already_validated = str(
            row.get("outcome_validated", False)
        ).lower() in {"true", "1", "yes"}

        if already_validated:
            continue

        try:
            created = pd.to_datetime(
                row["timestamp_utc"],
                utc=True
            ).to_pydatetime()
        except Exception:
            continue

        age_hours = (
            now - created
        ).total_seconds() / 3600

        if age_hours < minimum_age_hours:
            continue

        entry_brent = num(row.get("brent"))
        entry_wti = num(row.get("wti"))

        if entry_brent <= 0 or entry_wti <= 0:
            continue

        brent_return = (
            current_brent / entry_brent - 1
        ) * 100

        wti_return = (
            current_wti / entry_wti - 1
        ) * 100

        market_return = (
            brent_return + wti_return
        ) / 2

        # Zona neutrale ±0.75%
        if market_return >= 0.75:
            realized = "LONG"
        elif market_return <= -0.75:
            realized = "SHORT"
        else:
            realized = "WAIT"

        prediction = str(
            row.get("prediction", "WAIT")
        ).upper()

        correct = prediction == realized

        long_p = num(
            row.get("long_probability")
        ) / 100

        wait_p = num(
            row.get("wait_probability")
        ) / 100

        short_p = num(
            row.get("short_probability")
        ) / 100

        actual = {
            "LONG": (1, 0, 0),
            "WAIT": (0, 1, 0),
            "SHORT": (0, 0, 1)
        }.get(
            realized,
            (0, 1, 0)
        )

        brier = (
            (long_p - actual[0]) ** 2
            + (wait_p - actual[1]) ** 2
            + (short_p - actual[2]) ** 2
        ) / 3

        history.at[idx, "outcome_validated"] = True
        history.at[idx, "outcome_timestamp_utc"] = now.isoformat()
        history.at[idx, "brent_return_pct"] = round(brent_return, 3)
        history.at[idx, "wti_return_pct"] = round(wti_return, 3)
        history.at[idx, "market_return_pct"] = round(market_return, 3)
        history.at[idx, "realized_state"] = realized
        history.at[idx, "prediction_correct"] = bool(correct)
        history.at[idx, "brier_score"] = round(brier, 4)

        validated_now += 1

    history.to_csv(
        file,
        index=False
    )

    validated = history[
        history["outcome_validated"]
        .astype(str)
        .str.lower()
        .isin(["true", "1", "yes"])
    ]

    result["validated_now"] = validated_now
    result["total_validated"] = len(validated)

    if not validated.empty:

        correct_series = (
            validated["prediction_correct"]
            .astype(str)
            .str.lower()
            .isin(["true", "1", "yes"])
        )

        result["accuracy"] = round(
            correct_series.mean() * 100,
            1
        )

        last = validated.iloc[-1]

        result["latest_result"] = (
            f"{last.get('prediction', 'WAIT')} → "
            f"{last.get('realized_state', 'WAIT')} · "
            f"{'CORRECT' if str(last.get('prediction_correct')).lower() in ['true','1','yes'] else 'WRONG'}"
        )

    return result


def render_outcome_validation(report):

    section(
        "Outcome Validation",
        "Automatic comparison between previous predictions and realized market direction"
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            "Predictions Stored",
            int(report.get("total_predictions", 0))
        )

    with c2:
        st.metric(
            "Validated",
            int(report.get("total_validated", 0))
        )

    with c3:
        st.metric(
            "Accuracy",
            f"{report.get('accuracy', 0):.1f}%"
        )

    with c4:
        st.metric(
            "Validated Now",
            int(report.get("validated_now", 0))
        )

    if report.get("total_validated", 0) == 0:
        st.info(
            "Outcome validation is active. "
            "The first prediction becomes eligible after 24 hours."
        )
    else:
        st.info(
            f"Latest validation: "
            f"{report.get('latest_result', 'N/A')}"
        )

    st.caption(
        "Realized state: LONG above +0.75%, "
        "SHORT below -0.75%, otherwise WAIT, "
        "using the average Brent/WTI return after at least 24 hours."
    )

# END PROCUREYE RELEASE 46.1 DEV


# ============================================================
# PROCUREYE RELEASE 46.2 DEV — LEARNING STATISTICS
# ============================================================

def build_learning_statistics():

    from pathlib import Path

    file = Path(
        "/tmp/procureye_prediction_history.csv"
    )

    empty = {
        "predictions": 0,
        "validated": 0,
        "accuracy": 0.0,
        "brier": 0.0,
        "recent_accuracy": 0.0,
        "by_signal": pd.DataFrame(),
        "by_driver": pd.DataFrame(),
        "by_scenario": pd.DataFrame(),
        "by_confidence": pd.DataFrame()
    }

    if not file.exists():
        return empty

    try:
        history = pd.read_csv(file)
    except Exception:
        return empty

    if history.empty:
        return empty

    result = empty.copy()
    result["predictions"] = len(history)

    if "outcome_validated" not in history.columns:
        return result

    valid = history[
        history["outcome_validated"]
        .astype(str)
        .str.lower()
        .isin(["true", "1", "yes"])
    ].copy()

    if valid.empty:
        return result

    valid["Correct"] = (
        valid["prediction_correct"]
        .astype(str)
        .str.lower()
        .isin(["true", "1", "yes"])
    )

    valid["CorrectInt"] = (
        valid["Correct"].astype(int)
    )

    result["validated"] = len(valid)

    result["accuracy"] = round(
        valid["CorrectInt"].mean() * 100,
        1
    )

    if "brier_score" in valid.columns:

        brier = pd.to_numeric(
            valid["brier_score"],
            errors="coerce"
        ).dropna()

        if not brier.empty:
            result["brier"] = round(
                brier.mean(),
                4
            )

    recent = valid.tail(30)

    if not recent.empty:
        result["recent_accuracy"] = round(
            recent["CorrectInt"].mean() * 100,
            1
        )

    # Accuracy per LONG / WAIT / SHORT
    if "prediction" in valid.columns:

        by_signal = (
            valid.groupby("prediction")
            .agg(
                Predictions=("CorrectInt", "size"),
                Correct=("CorrectInt", "sum"),
                Accuracy=("CorrectInt", "mean")
            )
            .reset_index()
            .rename(
                columns={"prediction": "Signal"}
            )
        )

        by_signal["Accuracy"] = (
            by_signal["Accuracy"] * 100
        ).round(1)

        result["by_signal"] = by_signal

    # Accuracy per driver
    if "dominant_driver" in valid.columns:

        by_driver = (
            valid.groupby("dominant_driver")
            .agg(
                Predictions=("CorrectInt", "size"),
                Correct=("CorrectInt", "sum"),
                Accuracy=("CorrectInt", "mean")
            )
            .reset_index()
            .rename(
                columns={
                    "dominant_driver": "Driver"
                }
            )
        )

        by_driver["Accuracy"] = (
            by_driver["Accuracy"] * 100
        ).round(1)

        result["by_driver"] = (
            by_driver.sort_values(
                ["Predictions", "Accuracy"],
                ascending=False
            )
        )

    # Accuracy per Scenario
    if "scenario" in valid.columns:

        by_scenario = (
            valid.groupby("scenario")
            .agg(
                Predictions=("CorrectInt", "size"),
                Correct=("CorrectInt", "sum"),
                Accuracy=("CorrectInt", "mean")
            )
            .reset_index()
            .rename(
                columns={"scenario": "Scenario"}
            )
        )

        by_scenario["Accuracy"] = (
            by_scenario["Accuracy"] * 100
        ).round(1)

        result["by_scenario"] = by_scenario

    # Accuracy per Confidence bucket
    if "confidence_v2" in valid.columns:

        confidence = pd.to_numeric(
            valid["confidence_v2"],
            errors="coerce"
        )

        valid["Confidence Bucket"] = pd.cut(
            confidence,
            bins=[-1, 39, 54, 69, 84, 100],
            labels=[
                "VERY LOW",
                "LOW",
                "MEDIUM",
                "HIGH",
                "VERY HIGH"
            ]
        )

        by_confidence = (
            valid.dropna(
                subset=["Confidence Bucket"]
            )
            .groupby(
                "Confidence Bucket",
                observed=True
            )
            .agg(
                Predictions=("CorrectInt", "size"),
                Correct=("CorrectInt", "sum"),
                Accuracy=("CorrectInt", "mean")
            )
            .reset_index()
        )

        by_confidence["Accuracy"] = (
            by_confidence["Accuracy"] * 100
        ).round(1)

        result["by_confidence"] = (
            by_confidence
        )

    return result


def render_learning_statistics(report):

    section(
        "Learning Statistics",
        "Observed predictive performance — no automatic weight changes"
    )

    a, b, c, d = st.columns(4)

    with a:
        st.metric(
            "Predictions",
            int(report.get("predictions", 0))
        )

    with b:
        st.metric(
            "Validated",
            int(report.get("validated", 0))
        )

    with c:
        st.metric(
            "Overall Accuracy",
            f"{report.get('accuracy', 0):.1f}%"
        )

    with d:
        st.metric(
            "Last 30 Accuracy",
            f"{report.get('recent_accuracy', 0):.1f}%"
        )

    if report.get("validated", 0) == 0:

        st.info(
            "Learning Statistics is active. "
            "Statistics will appear after the first "
            "24-hour outcomes are validated."
        )

        return

    st.metric(
        "Average Brier Score",
        f"{report.get('brier', 0):.4f}"
    )

    by_signal = report.get("by_signal")

    if isinstance(by_signal, pd.DataFrame) and not by_signal.empty:

        st.markdown("#### Accuracy by Signal")

        st.dataframe(
            by_signal,
            width="stretch",
            hide_index=True,
            column_config={
                "Accuracy":
                    st.column_config.ProgressColumn(
                        "Accuracy",
                        min_value=0,
                        max_value=100,
                        format="%.1f%%"
                    )
            }
        )

    by_driver = report.get("by_driver")

    if isinstance(by_driver, pd.DataFrame) and not by_driver.empty:

        st.markdown("#### Accuracy by Driver")

        st.dataframe(
            by_driver.head(10),
            width="stretch",
            hide_index=True,
            column_config={
                "Accuracy":
                    st.column_config.ProgressColumn(
                        "Accuracy",
                        min_value=0,
                        max_value=100,
                        format="%.1f%%"
                    )
            }
        )

    by_scenario = report.get("by_scenario")

    if isinstance(by_scenario, pd.DataFrame) and not by_scenario.empty:

        st.markdown("#### Accuracy by Scenario")

        st.dataframe(
            by_scenario,
            width="stretch",
            hide_index=True
        )

    by_confidence = report.get(
        "by_confidence"
    )

    if (
        isinstance(by_confidence, pd.DataFrame)
        and not by_confidence.empty
    ):

        st.markdown(
            "#### Accuracy by Confidence"
        )

        st.dataframe(
            by_confidence,
            width="stretch",
            hide_index=True
        )

    st.caption(
        "Learning Statistics measures historical performance only. "
        "Release 46.2 does not modify Predictive Intelligence weights."
    )

# END PROCUREYE RELEASE 46.2 DEV


def pe_metric(key, label, value, *args, **kwargs):
    with st.container(key=key):
        st.metric(label, value, *args, **kwargs)

st.set_page_config(
    page_title="PROCUREYE | Oil Market Intelligence",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>

/* Tutti i bottoni bianchi -> testo blu scuro */
div[data-testid="stButton"] button {
    color: #0B2D4D !important;
    font-weight: 600 !important;
}

div[data-testid="stButton"] button p {
    color: #0B2D4D !important;
}

/* Refresh Now -> blu scuro */
.st-key-global_refresh button {
    background-color: #0B2D4D !important;
    border-color: #0B2D4D !important;
    color: white !important;
    font-weight: 700 !important;
}

.st-key-global_refresh button p {
    color: white !important;
}

/* Plotly range selector */
.js-plotly-plot .rangeselector text {
    fill: #0B2D4D !important;
    font-weight: 600 !important;
}

/* Metriche con testo lungo */
.st-key-pe_signal_change [data-testid="stMetricValue"] {
    font-size: 1.20rem !important;
}

.st-key-pe_correlation_state [data-testid="stMetricValue"] {
    font-size: 1.20rem !important;
}

.st-key-pe_decision_mode [data-testid="stMetricValue"] {
    font-size: 1.20rem !important;
}

</style>
""", unsafe_allow_html=True)




import streamlit.components.v1 as components

components.html(
    """
    <script>
    setTimeout(function () {
        window.parent.location.reload();
    }, 300000);
    </script>
    """,
    height=0,
    width=0
)

st.markdown("""
<style>
:root {
    --bg:#071018;
    --panel:#0e1c27;
    --panel2:#122633;
    --border:rgba(140,180,205,.18);
    --text:#edf5f9;
    --muted:#91a8b7;
    --blue:#35a8d4;
    --green:#29c483;
    --red:#ff6472;
    --amber:#f4bd4b;
}
html,body,[data-testid="stAppViewContainer"] {
    background:linear-gradient(145deg,#071018,#0a1721);
    color:var(--text);
}
[data-testid="stHeader"] {
    background:rgba(7,16,24,.82);
}
[data-testid="stAppViewBlockContainer"] {
    max-width:1600px;
    padding-top:1.2rem;
    padding-bottom:4rem;
}
.pe-hero {
    padding:1.45rem 1.6rem;
    border:1px solid var(--border);
    border-radius:20px;
    background:linear-gradient(135deg,#122c3a,#09151e);
    margin-bottom:1rem;
    box-shadow:0 18px 45px rgba(0,0,0,.25);
}
.pe-top {
    display:flex;
    justify-content:space-between;
    gap:1rem;
    align-items:center;
}
.pe-brand {
    font-size:2rem;
    font-weight:800;
    letter-spacing:.04em;
}
.pe-release {
    border:1px solid rgba(53,168,212,.38);
    background:rgba(53,168,212,.12);
    color:#afe7fa;
    border-radius:999px;
    padding:.4rem .75rem;
    font-size:.75rem;
    font-weight:700;
}
.pe-title {
    margin-top:.8rem;
    font-size:1.35rem;
    font-weight:700;
}
.pe-copy {
    margin-top:.35rem;
    color:var(--muted);
    max-width:900px;
}
.pe-badges {
    margin-top:1rem;
    display:flex;
    flex-wrap:wrap;
    gap:.55rem;
}
.pe-badge {
    border:1px solid var(--border);
    border-radius:8px;
    padding:.38rem .65rem;
    color:#bdd0db;
    font-size:.72rem;
    font-weight:650;
}
.pe-section {
    margin-top:1.2rem;
    margin-bottom:.55rem;
    display:flex;
    justify-content:space-between;
    align-items:center;
}
.pe-section strong {
    font-size:.9rem;
    letter-spacing:.08em;
    text-transform:uppercase;
}
.pe-section span {
    color:var(--muted);
    font-size:.78rem;
}
[data-testid="stMetric"] {
    min-height:112px;
    padding:1rem;
    border:1px solid var(--border);
    border-radius:15px;
    background:linear-gradient(145deg,var(--panel2),var(--panel));
}
[data-testid="stMetricLabel"] {
    color:var(--muted);
    text-transform:uppercase;
    letter-spacing:.05em;
    font-size:.72rem;
}
[data-testid="stMetricValue"] {
    color:var(--text);
    font-weight:750;
}
[data-testid="stAlert"] {
    border-radius:13px;
}
[data-testid="stDataFrame"] {
    border:1px solid var(--border);
    border-radius:14px;
    overflow:hidden;
}
#MainMenu,footer {
    visibility:hidden;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<section class="pe-hero">
  <div class="pe-top">
    <div class="pe-brand">PROCUREYE</div>
    <div class="pe-release">Release 46.2 VISUAL DEV · Refinement 01
  </div>
  <div class="pe-title">Crude Oil Market Intelligence Platform</div>
  <div class="pe-copy">
    Decision-support intelligence for Brent and WTI using market structure,
    momentum, volatility, news, historical memory and explainable reasoning.
  </div>
  <div class="pe-badges">
    <span class="pe-badge">CONTROLLED LEARNING AGENT</span>
    <span class="pe-badge">ADVANCED MARKET INTELLIGENCE</span>
    <span class="pe-badge">DECISION SUPPORT ONLY</span>
    <span class="pe-badge">HUMAN OVERSIGHT REQUIRED</span>
  </div>
</section>
""", unsafe_allow_html=True)

def section(title, subtitle):
    st.markdown(
        f'<div class="pe-section"><strong>{title}</strong>'
        f'<span>{subtitle}</span></div>',
        unsafe_allow_html=True
    )



def load_price_series(csv_name, ticker):
    from urllib.parse import quote

    safe_name = (
        str(ticker)
        .replace("=", "_")
        .replace("^", "_")
        .replace("/", "_")
    )

    fallback_file = Path("/tmp") / f"procureye_{safe_name}_fallback.csv"

    def normalize(frame, date_col=None, close_col=None, source_name="UNKNOWN"):
        if frame is None or frame.empty:
            return pd.DataFrame(columns=["Date", "Close"])

        data = frame.copy()

        if date_col is None:
            date_col = next(
                (
                    column for column in data.columns
                    if str(column).lower()
                    in {"date", "datetime", "timestamp"}
                ),
                data.columns[0]
            )

        if close_col is None:
            close_col = next(
                (
                    column for column in data.columns
                    if str(column).lower()
                    in {"close", "adj close", "price"}
                ),
                None
            )

        if close_col is None:
            return pd.DataFrame(columns=["Date", "Close"])

        data = data[[date_col, close_col]].copy()
        data.columns = ["Date", "Close"]

        data["Date"] = pd.to_datetime(
            data["Date"],
            errors="coerce",
            utc=True
        ).dt.tz_localize(None)

        data["Close"] = pd.to_numeric(
            data["Close"],
            errors="coerce"
        )

        data = (
            data.dropna(subset=["Date", "Close"])
            .drop_duplicates("Date")
            .sort_values("Date")
            .reset_index(drop=True)
        )

        if not data.empty:
            data.attrs["source"] = source_name
            data.attrs["status"] = "LIVE"

        return data

    local_paths = [
        Path("/content") / csv_name,
        Path.cwd() / csv_name,
        Path.cwd() / "data" / csv_name
    ]

    for path in local_paths:
        if not path.exists():
            continue

        try:
            data = normalize(
                pd.read_csv(path),
                source_name=f"LOCAL:{path.name}"
            )

            if not data.empty:
                data.to_csv(fallback_file, index=False)
                return data
        except Exception:
            pass

    symbol = quote(str(ticker), safe="")

    yahoo_urls = [
        (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{symbol}?range=6mo&interval=1d"
        ),
        (
            "https://query2.finance.yahoo.com/v8/finance/chart/"
            f"{symbol}?range=6mo&interval=1d"
        )
    ]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/124 Safari/537.36"
        ),
        "Accept": "application/json"
    }

    for index, url in enumerate(yahoo_urls, start=1):
        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=20
            )
            response.raise_for_status()

            payload = response.json()
            results = payload.get("chart", {}).get("result")

            if not results:
                continue

            item = results[0]
            timestamps = item.get("timestamp", [])
            closes = (
                item.get("indicators", {})
                .get("quote", [{}])[0]
                .get("close", [])
            )

            length = min(len(timestamps), len(closes))

            if length == 0:
                continue

            raw = pd.DataFrame({
                "Date": pd.to_datetime(
                    timestamps[:length],
                    unit="s",
                    utc=True,
                    errors="coerce"
                ),
                "Close": closes[:length]
            })

            data = normalize(
                raw,
                date_col="Date",
                close_col="Close",
                source_name=f"YAHOO_QUERY_{index}"
            )

            if not data.empty:
                data.to_csv(fallback_file, index=False)
                return data

        except Exception:
            continue

    try:
        import yfinance as yf

        raw = yf.download(
            ticker,
            period="6mo",
            interval="1d",
            progress=False,
            auto_adjust=False,
            threads=False,
            timeout=20
        )

        if raw is not None and not raw.empty:
            if isinstance(raw.columns, pd.MultiIndex):
                close = raw["Close"].iloc[:, 0]
            else:
                close = raw["Close"]

            frame = pd.DataFrame({
                "Date": close.index,
                "Close": close.to_numpy()
            })

            data = normalize(
                frame,
                date_col="Date",
                close_col="Close",
                source_name="YFINANCE"
            )

            if not data.empty:
                data.to_csv(fallback_file, index=False)
                return data

    except Exception:
        pass

    if fallback_file.exists():
        try:
            data = normalize(
                pd.read_csv(fallback_file),
                source_name="LAST_VALID_SNAPSHOT"
            )

            if not data.empty:
                data.attrs["status"] = "FALLBACK"
                return data
        except Exception:
            pass

    unavailable = pd.DataFrame(columns=["Date", "Close"])
    unavailable.attrs["source"] = "NONE"
    unavailable.attrs["status"] = "UNAVAILABLE"
    return unavailable


@st.cache_data(ttl=300, show_spinner=False)
def get_market_data():
    return (
        load_price_series("brent.csv", "BZ=F"),
        load_price_series("wti.csv", "CL=F")
    )

def metrics(df):
    if df.empty:
        return {
            "price": None,
            "change": None,
            "trend": "UNKNOWN",
            "momentum": 0.0,
            "volatility": 0.0
        }

    close = df["Close"].dropna()
    price = float(close.iloc[-1])

    change = 0.0
    if len(close) > 1 and close.iloc[-2] != 0:
        change = float((close.iloc[-1] / close.iloc[-2] - 1) * 100)

    ma20 = close.rolling(20).mean().iloc[-1] if len(close) >= 20 else close.mean()
    trend = "BULLISH" if price > ma20 else "BEARISH"

    momentum = 0.0
    if len(close) >= 11 and close.iloc[-11] != 0:
        momentum = float((close.iloc[-1] / close.iloc[-11] - 1) * 100)

    returns = close.pct_change().dropna()
    volatility = float(returns.tail(20).std() * (252 ** 0.5) * 100) if len(returns) else 0.0

    return {
        "price": price,
        "change": change,
        "trend": trend,
        "momentum": momentum,
        "volatility": volatility
    }

def fallback_signal(brent, wti, news_score=0):
    score = 50

    for item in (brent, wti):
        if item["trend"] == "BULLISH":
            score += 8
        elif item["trend"] == "BEARISH":
            score -= 8

        score += max(-7, min(7, item["momentum"]))

    news_adjustment = max(
        -15,
        min(15, float(news_score) * 0.15)
    )

    score += news_adjustment
    score = int(max(0, min(100, round(score))))

    if score >= 62:
        signal = "🟢 LONG"
    elif score <= 38:
        signal = "🔴 SHORT"
    else:
        signal = "🟡 WAIT"

    confidence = "HIGH" if score >= 75 or score <= 25 else "MEDIUM" if score >= 62 or score <= 38 else "LOW"

    return signal, score, confidence

def existing_engine_signal(brent_df, wti_df, fallback, news_score=0):
    try:
        from procureye_signal_engine_v22 import calculate_signal

        signature = inspect.signature(calculate_signal)
        kwargs = {}

        values = {
            "brent": brent_df["Close"],
            "brent_close": brent_df["Close"],
            "wti": wti_df["Close"],
            "wti_close": wti_df["Close"],
            "news_score": news_score
        }

        for name in signature.parameters:
            if name in values:
                kwargs[name] = values[name]

        result = calculate_signal(**kwargs)

        if isinstance(result, dict):
            return (
                result.get("signal", fallback[0]),
                int(result.get("score", fallback[1])),
                result.get("confidence", fallback[2]),
                result
            )

    except Exception:
        pass

    return fallback[0], fallback[1], fallback[2], {}

def chart(df, title):
    if df.empty:
        st.warning(f"{title}: dati non disponibili.")
        return

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["Date"],
        y=df["Close"],
        mode="lines",
        name=title,
        line=dict(width=2)
    ))

    fig.update_layout(
        title=title,
        height=390,
        margin=dict(l=15, r=15, t=50, b=15),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#dceaf1"),
        hovermode="x unified",
        xaxis=dict(
            rangeslider=dict(visible=True),
            gridcolor="rgba(140,180,205,.10)"
        ),
        yaxis=dict(
            title="USD",
            gridcolor="rgba(140,180,205,.10)"
        )
    )

    st.plotly_chart(fig, width="stretch")

def load_news():
    candidates = [
        Path("/content/procureye_news_memory.csv"),
        Path("/content/procureye_daily_briefing.csv"),
        Path("/content/procureye_news_discovery_memory.csv")
    ]

    for path in candidates:
        if not path.exists():
            continue

        try:
            df = pd.read_csv(path)

            title_col = next(
                (c for c in df.columns if c.lower() in {"title","headline","news_title"}),
                None
            )

            source_col = next(
                (c for c in df.columns if c.lower() in {"source","publisher"}),
                None
            )

            impact_col = next(
                (c for c in df.columns if c.lower() in {"impact","impact_score","score"}),
                None
            )

            if title_col:
                result = pd.DataFrame()
                result["Title"] = df[title_col].astype(str)
                result["Source"] = df[source_col].astype(str) if source_col else "PROCUREYE"
                result["Impact"] = pd.to_numeric(df[impact_col], errors="coerce").fillna(0) if impact_col else 0
                result["Bias"] = result["Impact"].apply(
                    lambda x: "BULLISH" if x > 0 else "BEARISH" if x < 0 else "NEUTRAL"
                )

                return result.sort_values(
                    "Impact",
                    key=lambda x: x.abs(),
                    ascending=False
                ).head(3)

        except Exception:
            pass

    return pd.DataFrame([
        {
            "Title": "Oil market news feed awaiting live source refresh",
            "Source": "PROCUREYE",
            "Impact": 0,
            "Bias": "NEUTRAL"
        }
    ])

# ==============================================================
# PROCUREYE RELEASE 41.7 — CONTROLLED EXECUTION ARCHITECTURE
# ==============================================================

def run_procureye_dashboard():
    """Execute the complete dashboard in one controlled scope."""

    brent_df, wti_df = get_market_data()
    brent = metrics(brent_df)
    wti = metrics(wti_df)

    signal_news = get_market_movers(limit=3)

    if signal_news is not None and not signal_news.empty:
        news_score = float(
            pd.to_numeric(
                signal_news["Impact"],
                errors="coerce"
            )
            .fillna(0)
            .clip(-100, 100)
            .mean()
        )
    else:
        news_score = 0.0

    spread = None

    if (
        brent["price"] is not None
        and wti["price"] is not None
    ):
        spread = brent["price"] - wti["price"]

    market_volatility = max(
        float(brent.get("volatility", 0) or 0),
        float(wti.get("volatility", 0) or 0)
    )

    risk = (
        "HIGH"
        if market_volatility >= 45
        else "MEDIUM"
        if market_volatility >= 25
        else "LOW"
    )

    provisional_regime = "TRANSITION"

    provisional_fallback = fallback_signal(
        brent,
        wti,
        news_score=0.0
    )

    provisional_confidence = provisional_fallback[2]

    adaptive_news = calculate_adaptive_news_weight(
        news=signal_news,
        risk=risk,
        regime=provisional_regime,
        confidence=provisional_confidence
    )

    adaptive_news_score = float(
        adaptive_news.get("effective_score", 0.0)
    )

    fallback = fallback_signal(
        brent,
        wti,
        news_score=adaptive_news_score
    )

    signal, score, confidence, engine_result = existing_engine_signal(
        brent_df,
        wti_df,
        fallback,
        news_score=adaptive_news_score
    )

    regime = (
        engine_result
        .get("components", {})
        .get("regime", provisional_regime)
        if isinstance(engine_result, dict)
        else provisional_regime
    )

    confidence_engine = calculate_confidence_engine(
        brent=brent,
        wti=wti,
        adaptive_news=adaptive_news
    )

    section("Executive Dashboard", datetime.now(timezone.utc).strftime("Updated %Y-%m-%d %H:%M UTC"))
    render_system_health(brent_df, wti_df, signal_news)

    render_market_delta(
        brent,
        wti,
        signal,
        score,
        confidence
    )



    c1, c2, c3, c4, c5, c6 = st.columns(6)

    with c1:
        st.metric(
            "Brent",
            f"${brent['price']:.2f}" if brent["price"] is not None else "N/A",
            f"{brent['change']:+.2f}%" if brent["change"] is not None else None
        )

    with c2:
        st.metric(
            "WTI",
            f"${wti['price']:.2f}" if wti["price"] is not None else "N/A",
            f"{wti['change']:+.2f}%" if wti["change"] is not None else None
        )

    with c3:
        st.metric("Signal", signal)

    with c4:
        st.metric("Market Score", f"{score}/100")

    with c5:
        st.metric("Confidence", confidence)

    with c6:
        st.metric("Risk", risk)

    section("Market Intelligence", "Brent and WTI interactive history")

    left, right = st.columns(2, gap="large")

    with left:
        render_professional_chart(brent_df, "Brent Crude Oil", "BRENT")

    with right:
        render_professional_chart(wti_df, "WTI Crude Oil", "WTI")


    section("Why This Signal?", "Automatic explainable decision summary")

    _why_news = signal_news.copy()

    why = build_why_signal(
        signal=signal,
        score=score,
        confidence=confidence,
        risk=risk,
        regime=regime,
        brent=brent,
        wti=wti,
        news=_why_news
    )

    st.subheader(why["title"])

    for reason in why["reasons"]:
        st.write(f"✓ {reason}")

    st.info(why["action"])

    w1, w2, w3 = st.columns(3)

    with w1:
        st.metric("Market Score", f"{why['score']}/100")

    with w2:
        st.metric("Confidence", why["confidence"])

    with w3:
        st.metric("Market Regime", why["regime"])


    section(
        "Top Market-Moving News",
        "Three highest-impact live oil-market items"
    )

    refresh_news = st.button(
        "Refresh market data and news",
        key="refresh_market_news"
    )

    if refresh_news:
        st.cache_data.clear()
        st.rerun()

    news = get_market_movers(limit=3)


    for index, row in news.iterrows():
        icon = (
            "🟢" if row["Bias"] == "BULLISH"
            else "🔴" if row["Bias"] == "BEARISH"
            else "🟡"
        )

        with st.container(border=True):
            st.markdown(f"### {index + 1}. {icon} {row['Title']}")

            n1, n2, n3 = st.columns([2, 1, 1])

            with n1:
                st.caption(
                    f"{row['Source']} · {row['Published']}"
                )

            with n2:
                st.metric(
                    "Expected impact",
                    row["Bias"],
                    f"{row['Impact']:+.1f}"
                )

            with n3:
                st.metric(
                    "Confidence",
                    f"{int(row['Confidence'])}%"
                )

            if row.get("URL"):
                st.link_button(
                    "Read full article →",
                    row["URL"],
                    use_container_width=False
                )


    section("Market Drivers", "Current directional evidence")

    drivers = build_market_drivers(
        brent=brent,
        wti=wti,
        news=news,
        risk=risk
    )

    st.dataframe(
        drivers,
        width="stretch",
        hide_index=True,
        column_config={
            "Strength": st.column_config.ProgressColumn(
                "Strength",
                min_value=0,
                max_value=100,
                format="%d"
            )
        }
    )




    market_movers_ranking = build_market_movers_ranking(
        news=news,
        limit=10
    )

    render_market_movers_ranking(
        market_movers_ranking
    )

    driver_intelligence = analyze_driver_intelligence(news)


    driver_correlation = calculate_driver_correlation(
        driver_intelligence
    )
    render_driver_intelligence_panel(
        driver_intelligence
    )

    render_driver_correlation(
        driver_correlation
    )

    record_historical_driver_memory(
        driver_report=driver_intelligence,
        correlation_report=driver_correlation,
        signal=signal,
        score=score,
        brent=brent,
        wti=wti
    )

    historical_driver_memory = build_historical_driver_memory()

    render_historical_driver_memory(
        historical_driver_memory
    )

    confidence_intelligence_v2 = calculate_confidence_intelligence_v2(
        base_confidence=confidence_engine,
        driver_report=driver_intelligence,
        correlation_report=driver_correlation,
        historical_memory=historical_driver_memory,
        brent=brent,
        wti=wti,
        risk=risk
    )

    render_confidence_intelligence_v2(
        confidence_intelligence_v2
    )

    explainable_decision_v2 = build_explainable_decision_v2(
        signal=signal,
        score=score,
        risk=risk,
        regime=regime,
        brent=brent,
        wti=wti,
        driver_report=driver_intelligence,
        correlation_report=driver_correlation,
        historical_memory=historical_driver_memory,
        confidence_v2=confidence_intelligence_v2,
        ranking=market_movers_ranking
    )

    render_explainable_decision_v2(
        explainable_decision_v2
    )

    predictive_intelligence = calculate_predictive_intelligence(
        signal=signal,
        score=score,
        brent=brent,
        wti=wti,
        risk=risk,
        adaptive_news=adaptive_news,
        driver_report=driver_intelligence,
        correlation_report=driver_correlation,
        confidence_v2=confidence_intelligence_v2
    )

    render_predictive_intelligence(predictive_intelligence)

    scenario_engine = build_scenario_engine(
        predictive=predictive_intelligence,
        brent=brent,
        wti=wti,
        driver_report=driver_intelligence,
        correlation_report=driver_correlation,
        risk=risk
    )

    render_scenario_engine(
        scenario_engine
    )

    driver_forecast = build_driver_forecast(
        ranking=market_movers_ranking,
        driver_report=driver_intelligence,
        correlation_report=driver_correlation,
        predictive=predictive_intelligence
    )

    render_driver_forecast(driver_forecast)

    prediction_archive_status = record_prediction_archive(
        predictive=predictive_intelligence,
        scenario=scenario_engine,
        forecast=driver_forecast,
        driver_report=driver_intelligence,
        signal=signal,
        score=score,
        confidence=confidence_intelligence_v2,
        risk=risk,
        regime=regime,
        brent=brent,
        wti=wti
    )

    outcome_validation = validate_prediction_outcomes(
        brent=brent,
        wti=wti,
        minimum_age_hours=24
    )

    render_outcome_validation(outcome_validation)

    learning_statistics = build_learning_statistics()

    render_learning_statistics(learning_statistics)

    record_decision_journal(
        brent=brent,
        wti=wti,
        signal=signal,
        score=score,
        confidence=confidence,
        risk=risk,
        regime=regime,
        news=news
    )


    section(
        "Adaptive News Weight",
        "Controlled contribution of live news to the Market Score"
    )

    render_adaptive_news_weight(
        adaptive_news
    )


    section(
        "Decision Journal",
        "Recorded market decisions and changes"
    )

    render_decision_journal()




    render_confidence_engine(
        confidence_engine
    )

    daily_market_brief = build_daily_market_brief(
        brent=brent,
        wti=wti,
        signal=signal,
        score=score,
        confidence=confidence,
        risk=risk,
        regime=regime,
        adaptive_news=adaptive_news,
        confidence_engine=confidence_engine,
        news=news,
    )

    render_daily_market_brief(
        daily_market_brief
    )

    section("System State", "Release 39 operating status")

    s1, s2, s3, s4 = st.columns(4)

    with s1:
        st.metric("Agent State", "CONTROLLED")

    with s2:
        st.metric("Learning State", "ACTIVE")

    with s3:
        pe_metric(
            "pe_decision_mode",
            "Decision Mode",
            "SUPPORT ONLY"
        )

    with s4:
        st.metric("Human Oversight", "REQUIRED")

    st.caption(
        "PROCUREYE does not execute trades or orders. "
        "All outputs are decision-support information only."
    )


if __name__ == "__main__":
    run_procureye_dashboard()
