"""PROCUREYE Release 42.1 — Driver Intelligence Engine."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st


SOURCE_QUALITY = {
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


def _safe_number(
    value: Any,
    default: float = 0.0
) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _source_quality(source: Any) -> float:
    text = str(source or "").lower()

    values = [
        score
        for name, score in SOURCE_QUALITY.items()
        if name in text
    ]

    return max(values) if values else 0.60


def analyze_driver_intelligence(
    news: pd.DataFrame | None
) -> dict[str, Any]:
    empty = {
        "dominant_driver": "NONE",
        "direction": "NEUTRAL",
        "strength": 0,
        "confidence": 0,
        "evidence_count": 0,
        "independent_sources": 0,
        "sources": [],
        "reason": "No live driver evidence is available.",
        "drivers": pd.DataFrame(
            columns=[
                "Driver",
                "Direction",
                "Net Score",
                "Strength",
                "Confidence",
                "Evidence",
                "Sources",
            ]
        ),
    }

    if news is None or news.empty:
        return empty

    rows = []

    for _, item in news.iterrows():
        driver = str(
            item.get("Driver", "OIL MARKET")
        ).strip() or "OIL MARKET"

        source = str(
            item.get("Source", "UNKNOWN")
        )

        bias = str(
            item.get("Bias", "NEUTRAL")
        ).upper()

        impact = _safe_number(
            item.get("Impact", 0.0)
        )

        confidence = _safe_number(
            item.get("Confidence", 50.0),
            50.0
        )

        source_factor = _source_quality(source)

        directional_score = (
            abs(impact)
            if bias == "BULLISH"
            else -abs(impact)
            if bias == "BEARISH"
            else impact
        )

        weighted_score = (
            directional_score
            * source_factor
            * max(
                0.25,
                min(1.0, confidence / 100)
            )
        )

        rows.append({
            "Driver": driver,
            "Source": source,
            "Weighted Score": weighted_score,
            "Confidence": confidence,
            "Source Quality": source_factor,
        })

    evidence = pd.DataFrame(rows)

    if evidence.empty:
        return empty

    grouped_rows = []

    for driver, group in evidence.groupby("Driver"):
        net_score = float(
            group["Weighted Score"].sum()
        )

        evidence_count = int(len(group))

        sources = sorted(
            set(
                group["Source"]
                .dropna()
                .astype(str)
            )
        )

        source_count = len(sources)

        average_confidence = float(
            group["Confidence"].mean()
        )

        average_quality = float(
            group["Source Quality"].mean()
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

        confidence = int(
            min(
                98,
                average_confidence * 0.55
                + average_quality * 100 * 0.25
                + min(20, source_count * 7)
            )
        )

        grouped_rows.append({
            "Driver": str(driver),
            "Direction": direction,
            "Net Score": round(net_score, 1),
            "Strength": strength,
            "Confidence": confidence,
            "Evidence": evidence_count,
            "Sources": source_count,
            "_source_names": sources,
        })

    drivers = pd.DataFrame(grouped_rows).sort_values(
        [
            "Strength",
            "Confidence",
            "Evidence",
        ],
        ascending=False
    ).reset_index(drop=True)

    dominant = drivers.iloc[0]

    dominant_sources = list(
        dominant["_source_names"]
    )

    public_table = drivers.drop(
        columns=["_source_names"],
        errors="ignore"
    )

    reason = (
        f"{dominant['Driver']} is the strongest current driver. "
        f"Direction {dominant['Direction']}, supported by "
        f"{int(dominant['Evidence'])} evidence item(s) from "
        f"{int(dominant['Sources'])} independent source(s)."
    )

    return {
        "dominant_driver": str(dominant["Driver"]),
        "direction": str(dominant["Direction"]),
        "strength": int(dominant["Strength"]),
        "confidence": int(dominant["Confidence"]),
        "evidence_count": int(dominant["Evidence"]),
        "independent_sources": int(dominant["Sources"]),
        "sources": dominant_sources,
        "reason": reason,
        "drivers": public_table,
    }


def render_driver_intelligence(
    report: dict[str, Any]
) -> None:
    st.markdown(
        """
        <div class="pe-section">
            <strong>Driver Intelligence</strong>
            <span>Structured evidence behind market direction</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    d1, d2, d3, d4 = st.columns(4)

    with d1:
        st.metric(
            "Dominant Driver",
            report.get("dominant_driver", "NONE")
        )

    with d2:
        st.metric(
            "Direction",
            report.get("direction", "NEUTRAL")
        )

    with d3:
        st.metric(
            "Strength",
            f"{int(report.get('strength', 0))}/100"
        )

    with d4:
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
        report.get(
            "reason",
            "No driver explanation available."
        )
    )
