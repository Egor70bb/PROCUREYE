
import json
from pathlib import Path
import streamlit as st

FILE=Path("data/last_snapshot.json")

def render_market_delta(brent,wti,signal,score,confidence):

    FILE.parent.mkdir(exist_ok=True)

    cur={
        "brent":float(brent["price"]),
        "wti":float(wti["price"]),
        "signal":str(signal),
        "score":int(score),
        "confidence":str(confidence)
    }

    if FILE.exists():

        old=json.loads(FILE.read_text())

        st.markdown("### 📈 Since Last Refresh")

        a,b,c,d,e=st.columns(5)

        a.metric("Brent",
                 f"${cur['brent']:.2f}",
                 f"{cur['brent']-old['brent']:+.2f}")

        b.metric("WTI",
                 f"${cur['wti']:.2f}",
                 f"{cur['wti']-old['wti']:+.2f}")

        c.metric("Signal",
                 cur["signal"],
                 old["signal"])

        d.metric("Score",
                 cur["score"],
                 cur["score"]-old["score"])

        e.metric("Confidence",
                 cur["confidence"],
                 old["confidence"])

    FILE.write_text(json.dumps(cur,indent=2))
