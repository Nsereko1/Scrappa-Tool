# dashboard/app.py
import streamlit as st
import plotly.express as px
import pandas as pd
import requests

st.set_page_config(page_title="Best-Seller Intelligence", layout="wide")
API = "http://localhost:8000"

@st.cache_data(ttl=300)
def load_snapshot(date: str):
    return pd.read_json(f"{API}/bestsellers?snapshot_date={date}")

st.title("Cross-Platform Best-Seller Intelligence")

snapshot_date = st.sidebar.date_input("Snapshot date")
df = load_snapshot(str(snapshot_date))

if df.empty:
    st.warning("No snapshot for this date.")
    st.stop()

col1, col2, col3 = st.columns(3)
col1.metric("Platforms", df["platform"].nunique())
col2.metric("Products tracked", len(df))
col3.metric("High-confidence records", (df["confidence"] == "high").sum())

# Normalized score comparison — same axis across platforms
fig = px.bar(
    df.sort_values("normalized_score", ascending=False).head(30),
    x="normalized_score", y="title", color="platform", orientation="h",
    hover_data=["confidence", "rank_native", "price", "currency"],
    title="Top 30 by normalized score (color = platform)",
)
st.plotly_chart(fig, use_container_width=True)

# Confidence distribution — exposes proxy-heavy platforms
conf_fig = px.histogram(df, x="platform", color="confidence", barmode="group",
                        title="Signal confidence by platform")
st.plotly_chart(conf_fig, use_container_width=True)

# Price band per platform
price_df = df.dropna(subset=["price"])
if not price_df.empty:
    st.plotly_chart(
        px.box(price_df, x="platform", y="price", color="platform",
               title="Price distribution by platform (local currency — not FX-converted)"),
        use_container_width=True,
    )