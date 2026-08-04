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
                st.metric(
                    "Signal Change",
                    _clean_signal(current["signal"]),
                    f"{_clean_signal(old_signal)} → {_clean_signal(current['signal'])}"
                )
            else:
                st.metric(
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
        freshness_state = "FALLBACK"

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
            st.warning("News sources: FALLBACK")

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


st.set_page_config(
    page_title="PROCUREYE | Oil Market Intelligence",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="collapsed"
)


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
    <div class="pe-release">Release 41.4.1 · Adaptive News Weight Fix</div>
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

brent_df, wti_df = get_market_data()
brent = metrics(brent_df)
wti = metrics(wti_df)

signal_news = get_market_movers(limit=3)

if signal_news is not None and not signal_news.empty:
    news_score = float(
        signal_news["Impact"]
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
    brent["volatility"],
    wti["volatility"]
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
    adaptive_news["effective_score"]
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


section("System State", "Release 39 operating status")

s1, s2, s3, s4 = st.columns(4)

with s1:
    st.metric("Agent State", "CONTROLLED")

with s2:
    st.metric("Learning State", "ACTIVE")

with s3:
    st.metric("Decision Mode", "SUPPORT ONLY")

with s4:
    st.metric("Human Oversight", "REQUIRED")

st.caption(
    "PROCUREYE does not execute trades or orders. "
    "All outputs are decision-support information only."
)
