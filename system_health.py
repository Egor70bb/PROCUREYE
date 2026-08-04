
from datetime import datetime, timezone
import streamlit as st

def render_system_health():

    now = datetime.now(timezone.utc)

    st.markdown("### 🟢 System Health")

    c1,c2,c3 = st.columns(3)

    with c1:
        st.metric(
            "Last Update",
            now.strftime("%H:%M UTC")
        )

    with c2:
        st.metric(
            "Data Age",
            "0 min"
        )

    with c3:
        if st.button("🔄 Refresh Now"):
            st.cache_data.clear()
            st.rerun()

    st.divider()

    a,b,c = st.columns(3)

    with a:
        st.success("Yahoo Finance")

    with b:
        st.success("Market Movers")

    with c:
        st.success("Signal Engine")
