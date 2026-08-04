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
    <div class="pe-release">Release 40.4 · Live Reliability</div>
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
    local_paths = [
        Path("/content") / csv_name,
        Path(__file__).resolve().parent / csv_name,
        Path(__file__).resolve().parent / "data" / csv_name,
    ]

    for path in local_paths:
        if not path.exists():
            continue

        try:
            df = pd.read_csv(path)

            date_col = next(
                (
                    c for c in df.columns
                    if c.lower() in {"date", "datetime", "timestamp"}
                ),
                df.columns[0]
            )

            close_col = next(
                (
                    c for c in df.columns
                    if c.lower() in {"close", "adj close", "price"}
                ),
                None
            )

            if close_col:
                result = df[[date_col, close_col]].copy()
                result.columns = ["Date", "Close"]
                result["Date"] = pd.to_datetime(
                    result["Date"],
                    errors="coerce"
                )
                result["Close"] = pd.to_numeric(
                    result["Close"],
                    errors="coerce"
                )
                result = result.dropna().sort_values("Date")

                if not result.empty:
                    return result

        except Exception:
            pass

    try:
        import requests
        from urllib.parse import quote

        symbol = quote(ticker, safe="")
        urls = [
            (
                "https://query1.finance.yahoo.com/v8/finance/chart/"
                f"{symbol}?range=6mo&interval=1d"
            ),
            (
                "https://query2.finance.yahoo.com/v8/finance/chart/"
                f"{symbol}?range=6mo&interval=1d"
            ),
        ]

        for url in urls:
            try:
                response = requests.get(
                    url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 Chrome/124 Safari/537.36"
                        ),
                        "Accept": "application/json",
                    },
                    timeout=20
                )
                response.raise_for_status()

                payload = response.json()
                chart_result = payload.get("chart", {}).get("result")

                if not chart_result:
                    continue

                item = chart_result[0]
                timestamps = item.get("timestamp", [])
                closes = (
                    item.get("indicators", {})
                    .get("quote", [{}])[0]
                    .get("close", [])
                )

                if not timestamps or not closes:
                    continue

                length = min(len(timestamps), len(closes))

                frame = pd.DataFrame({
                    "Date": pd.to_datetime(
                        timestamps[:length],
                        unit="s",
                        utc=True,
                        errors="coerce"
                    ).tz_localize(None),
                    "Close": pd.to_numeric(
                        closes[:length],
                        errors="coerce"
                    )
                }).dropna().sort_values("Date")

                if not frame.empty:
                    return frame

            except Exception:
                continue

    except Exception:
        pass

    try:
        import yfinance as yf

        result = yf.download(
            ticker,
            period="6mo",
            interval="1d",
            progress=False,
            auto_adjust=False,
            threads=False,
            timeout=20
        )

        if result is not None and not result.empty:
            if isinstance(result.columns, pd.MultiIndex):
                close = result["Close"].iloc[:, 0]
            else:
                close = result["Close"]

            frame = pd.DataFrame({
                "Date": pd.to_datetime(
                    close.index,
                    errors="coerce"
                ),
                "Close": pd.to_numeric(
                    close.to_numpy(),
                    errors="coerce"
                )
            }).dropna().sort_values("Date")

            if not frame.empty:
                return frame

    except Exception:
        pass

    return pd.DataFrame(columns=["Date", "Close"])


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

signal_news = signal_news.copy()

if signal_news is not None and not signal_news.empty:
    news_score = float(
        signal_news["Impact"]
        .fillna(0)
        .clip(-100, 100)
        .mean()
    )
else:
    news_score = 0.0

fallback = fallback_signal(
    brent,
    wti,
    news_score=news_score
)

signal, score, confidence, engine_result = existing_engine_signal(
    brent_df,
    wti_df,
    fallback,
    news_score=news_score
)

spread = None
if brent["price"] is not None and wti["price"] is not None:
    spread = brent["price"] - wti["price"]

risk = "HIGH" if max(brent["volatility"], wti["volatility"]) >= 45 else "MEDIUM" if max(brent["volatility"], wti["volatility"]) >= 25 else "LOW"
regime = engine_result.get("components", {}).get("regime", "TRANSITION") if isinstance(engine_result, dict) else "TRANSITION"

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
