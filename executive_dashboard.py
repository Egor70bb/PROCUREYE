from datetime import datetime, timezone

import streamlit as st


def _price(value):
    try:
        if value is None:
            return "N/A"
        return f"${float(value):.2f}"
    except Exception:
        return "N/A"


def _percent(value):
    try:
        if value is None:
            return None
        return f"{float(value):+.2f}%"
    except Exception:
        return None


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
    updated = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    st.markdown(
        """
        <div class="pe-section">
            <strong>Executive Dashboard</strong>
            <span>Current market state · no duplicated metrics</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.caption(f"Updated {updated}")

    c1, c2, c3, c4, c5, c6 = st.columns(6)

    with c1:
        st.metric(
            "Brent",
            _price(brent.get("price")),
            _percent(brent.get("change")),
        )

    with c2:
        st.metric(
            "WTI",
            _price(wti.get("price")),
            _percent(wti.get("change")),
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
            _price(spread),
        )
