# -*- coding: utf-8 -*-
"""PROCUREYE 42.1B — Driver Intelligence Engine."""

from typing import Any

import pandas as pd


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


def _number(value: Any, default: float = 0.0) -> float:
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

        impact = _number(
            item.get("Impact", 0.0)
        )

        confidence = _number(
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
            * _source_quality(source_name)
            * max(
                0.25,
                min(1.0, confidence / 100)
            )
        )

        evidence.append({
            "Driver": driver,
            "Source": source_name,
            "Score": weighted_score,
            "Confidence": confidence,
        })

    frame = pd.DataFrame(evidence)

    if frame.empty:
        return empty

    rows = []

    for driver, group in frame.groupby("Driver"):
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

        strength = int(min(
            100,
            abs(net_score)
            + evidence_count * 8
            + source_count * 6
        ))

        confidence_score = int(min(
            98,
            average_confidence * 0.70
            + min(28, source_count * 9)
        ))

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
