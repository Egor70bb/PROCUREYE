
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
    <div class="pe-release">Release 39 · Product Engineering</div>
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
    path = Path("/content") / csv_name

    if path.exists():
        df = pd.read_csv(path)

        date_col = next(
            (c for c in df.columns if c.lower() in {"date","datetime","timestamp"}),
            df.columns[0]
        )

        close_col = next(
            (c for c in df.columns if c.lower() in {"close","adj close","price"}),
            None
        )

        if close_col:
            result = df[[date_col, close_col]].copy()
            result.columns = ["Date", "Close"]
            result["Date"] = pd.to_datetime(result["Date"], errors="coerce")
            result["Close"] = pd.to_numeric(result["Close"], errors="coerce")
            result = result.dropna().sort_values("Date")

            if not result.empty:
                return result

    try:
        import yfinance as yf

        result = yf.download(
            ticker,
            period="6mo",
            interval="1d",
            progress=False,
            auto_adjust=False
        )

        if not result.empty:
            if isinstance(result.columns, pd.MultiIndex):
                close = result["Close"].iloc[:, 0]
            else:
                close = result["Close"]

            return pd.DataFrame({
                "Date": pd.to_datetime(close.index),
                "Close": pd.to_numeric(close.values, errors="coerce")
            }).dropna()

    except Exception:
        pass

    return pd.DataFrame(columns=["Date", "Close"])

@st.cache_data(ttl=900)
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

def fallback_signal(brent, wti):
    score = 50

    for item in (brent, wti):
        if item["trend"] == "BULLISH":
            score += 8
        elif item["trend"] == "BEARISH":
            score -= 8

        score += max(-7, min(7, item["momentum"]))

    score = int(max(0, min(100, round(score))))

    if score >= 62:
        signal = "🟢 LONG"
    elif score <= 38:
        signal = "🔴 SHORT"
    else:
        signal = "🟡 WAIT"

    confidence = "HIGH" if score >= 75 or score <= 25 else "MEDIUM" if score >= 62 or score <= 38 else "LOW"

    return signal, score, confidence

def existing_engine_signal(brent_df, wti_df, fallback):
    try:
        from procureye_signal_engine_v22 import calculate_signal

        signature = inspect.signature(calculate_signal)
        kwargs = {}

        values = {
            "brent": brent_df["Close"],
            "brent_close": brent_df["Close"],
            "wti": wti_df["Close"],
            "wti_close": wti_df["Close"],
            "news_score": 0
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

fallback = fallback_signal(brent, wti)
signal, score, confidence, engine_result = existing_engine_signal(
    brent_df,
    wti_df,
    fallback
)

spread = None
if brent["price"] is not None and wti["price"] is not None:
    spread = brent["price"] - wti["price"]

risk = "HIGH" if max(brent["volatility"], wti["volatility"]) >= 45 else "MEDIUM" if max(brent["volatility"], wti["volatility"]) >= 25 else "LOW"
regime = engine_result.get("components", {}).get("regime", "TRANSITION") if isinstance(engine_result, dict) else "TRANSITION"

section("Executive Dashboard", datetime.now(timezone.utc).strftime("Updated %Y-%m-%d %H:%M UTC"))

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
    chart(brent_df, "Brent Crude Oil")

with right:
    chart(wti_df, "WTI Crude Oil")

section("Why This Signal?", "Automatic explainable decision summary")

reasons = []

if brent["trend"] == "BULLISH":
    reasons.append("Brent trades above its 20-day average.")
else:
    reasons.append("Brent trades below its 20-day average.")

if wti["trend"] == "BULLISH":
    reasons.append("WTI trend is positive.")
else:
    reasons.append("WTI trend remains weak.")

if brent["momentum"] > 0:
    reasons.append(f"Brent 10-day momentum is positive at {brent['momentum']:+.2f}%.")
else:
    reasons.append(f"Brent 10-day momentum is negative at {brent['momentum']:+.2f}%.")

reasons.append(
    f"Annualized market volatility is approximately "
    f"{max(brent['volatility'], wti['volatility']):.1f}%."
)

st.info(" ".join(reasons))

d1, d2, d3, d4 = st.columns(4)

with d1:
    st.metric("Market Regime", regime)

with d2:
    st.metric("Brent Trend", brent["trend"])

with d3:
    st.metric("WTI Trend", wti["trend"])

with d4:
    st.metric(
        "Brent-WTI Spread",
        f"${spread:.2f}" if spread is not None else "N/A"
    )

section("Top Market-Moving News", "Three highest-impact available items")

news = load_news()

for _, row in news.iterrows():
    icon = "🟢" if row["Bias"] == "BULLISH" else "🔴" if row["Bias"] == "BEARISH" else "🟡"

    st.markdown(
        f"### {icon} {row['Title']}\n"
        f"**Source:** {row['Source']}  \n"
        f"**Expected impact:** {row['Bias']} · Score {row['Impact']:+.1f}"
    )

section("Market Drivers", "Current directional evidence")

drivers = pd.DataFrame([
    ["OPEC / Production", "NEUTRAL", "No validated live production shock"],
    ["US Inventories", "NEUTRAL", "Awaiting latest EIA/API update"],
    ["US Dollar / Fed", "NEUTRAL", "No validated live macro shock"],
    ["Geopolitics", "NEUTRAL", "No validated high-confidence event"],
    ["Global Demand", "NEUTRAL", "Mixed demand evidence"],
    ["Volatility", risk, f"{max(brent['volatility'], wti['volatility']):.1f}% annualized"],
], columns=["Driver", "State", "Evidence"])

st.dataframe(
    drivers,
    width="stretch",
    hide_index=True
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
