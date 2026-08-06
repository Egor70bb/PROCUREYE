"""PROCUREYE Release 42.0 — professional_chart.py."""

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
