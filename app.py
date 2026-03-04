from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Board Game Picker", layout="wide")

RECENT_PATH = Path("recently_played.csv")
COLLECTION_PATH = Path("collection.csv")
HEAVY_CUTOFF = 3.25

# ---------------------------
# Styling
# ---------------------------
heavy_on = st.session_state.get("heavy_mode", False)
random_has_pick = st.session_state.get("random_pick_id") is not None

st.markdown(
f"""
<style>

.block-container {{
    padding-top: 1.2rem;
}}

.card {{
    border: 1px solid rgba(0,0,0,0.08);
    border-radius: 14px;
    padding: 14px 16px;
    background: rgba(255,255,255,0.88);
    box-shadow: 0 1px 6px rgba(0,0,0,0.05);
    margin-bottom: 12px;
}}

.pick-name {{
    font-size: 1.35rem;
    font-weight: 800;
}}

.pick-meta {{
    margin-top: 8px;
}}

button:has(span:contains("🔥 Heavy")) {{
    background-color: {"#d62828" if heavy_on else "#f0f2f6"} !important;
    color: {"white" if heavy_on else "black"} !important;
}}

button:has(span:contains("🎲 Random")) {{
    background-color: {"#2a9d8f" if random_has_pick else "#f0f2f6"} !important;
    color: {"white" if random_has_pick else "black"} !important;
}}

</style>
""",
unsafe_allow_html=True
)

# ---------------------------
# Recently played helpers
# ---------------------------

def load_recently_played():
    if RECENT_PATH.exists():
        rp = pd.read_csv(RECENT_PATH)
        rp["objectid"] = pd.to_numeric(rp["objectid"], errors="coerce")
        rp["last_played"] = pd.to_datetime(rp["last_played"]).dt.date
        return rp
    return pd.DataFrame(columns=["objectid","last_played"])


def save_recently_played(rp):
    rp.to_csv(RECENT_PATH,index=False)


def mark_played(oid):
    rp = load_recently_played()

    today=date.today()

    if oid in rp.objectid.values:
        rp.loc[rp.objectid==oid,"last_played"]=today
    else:
        rp=pd.concat([rp,pd.DataFrame([{"objectid":oid,"last_played":today}])])

    save_recently_played(rp)


def clear_played(oid):
    rp=load_recently_played()
    rp=rp[rp.objectid!=oid]
    save_recently_played(rp)


def days_ago(d):
    if pd.isna(d):
        return None
    return (date.today()-pd.to_datetime(d).date()).days

# ---------------------------
# Load collection CSV
# ---------------------------

@st.cache_data
def load_collection():
    if not COLLECTION_PATH.exists():
        return pd.DataFrame()

    df=pd.read_csv(COLLECTION_PATH)

    df["objectid"]=pd.to_numeric(df["objectid"],errors="coerce")
    df["minplayers"]=pd.to_numeric(df["minplayers"],errors="coerce")
    df["maxplayers"]=pd.to_numeric(df["maxplayers"],errors="coerce")
    df["avgweight"]=pd.to_numeric(df["avgweight"],errors="coerce")
    df["baverage"]=pd.to_numeric(df["baverage"],errors="coerce")

    df["itemtype"]=df["itemtype"].astype(str).str.lower()

    if "bgg_url" not in df.columns:
        df["bgg_url"]=""

    missing=df["bgg_url"].astype(str).str.strip()==""

    df.loc[missing,"bgg_url"]=df.loc[missing,"objectid"].apply(
        lambda x:f"https://boardgamegeek.com/boardgame/{int(x)}"
    )

    return df


df=load_collection()

# ---------------------------
# Session defaults
# ---------------------------

defaults=dict(
players=4,
hide_expansions=False,
heavy_mode=False,
search="",
random_pick_id=None,
last_random_pick_id=None,
trigger_random=False,
avoid_recent=True,
avoid_days=14,
confirm_played_pick=False
)

for k,v in defaults.items():
    if k not in st.session_state:
        st.session_state[k]=v

# ---------------------------
# Layout
# ---------------------------

st.title("🎲 Board Game Picker")

left,right=st.columns([1,3])

# ---------------------------
# LEFT PANEL
# ---------------------------

with left:

    st.slider("Players",1,10,key="players")

    st.text_input("Search",key="search")

    col1,col2,col3=st.columns(3)

    with col1:
        if st.button("🎲 Random"):
            st.session_state.last_random_pick_id=st.session_state.random_pick_id
            st.session_state.trigger_random=True

    with col2:
        if st.button("🔥 Heavy"):
            st.session_state.heavy_mode=not st.session_state.heavy_mode

    with col3:
        if st.button("Reset"):
            st.session_state.random_pick_id=None
            st.session_state.heavy_mode=False
            st.session_state.search=""

    pick_slot=st.empty()

    st.markdown(
        f"Heavy Mode filters to games with **Weight ≥ {HEAVY_CUTOFF}**"
    )

    st.toggle("Hide expansions",key="hide_expansions")

    st.toggle("Avoid recently played",key="avoid_recent")

    st.slider("Avoid window days",1,120,key="avoid_days")

# ---------------------------
# Filtering
# ---------------------------

filtered=df.copy()

if st.session_state.hide_expansions:
    filtered=filtered[filtered.itemtype!="expansion"]

players=st.session_state.players

filtered=filtered[
    (filtered.minplayers<=players)
    &
    ((filtered.maxplayers.isna())|(filtered.maxplayers>=players))
]

if st.session_state.search:
    filtered=filtered[
        filtered.objectname.str.contains(st.session_state.search,case=False)
    ]

if st.session_state.heavy_mode:
    filtered=filtered[filtered.avgweight>=HEAVY_CUTOFF]

rp=load_recently_played()

filtered=filtered.merge(rp,on="objectid",how="left")

filtered["days_ago"]=filtered.last_played.apply(days_ago)

# ---------------------------
# Random selection
# ---------------------------

if st.session_state.trigger_random:

    st.session_state.trigger_random=False

    pool=filtered.copy()

    pool=pool[pool.itemtype!="expansion"]

    if st.session_state.avoid_recent:
        pool=pool[(pool.days_ago.isna())|(pool.days_ago>=st.session_state.avoid_days)]

    if st.session_state.last_random_pick_id and len(pool)>1:
        pool=pool[pool.objectid!=st.session_state.last_random_pick_id]

    if len(pool)>0:
        st.session_state.random_pick_id=int(pool.sample(1).objectid.iloc[0])

# ---------------------------
# RANDOM PICK CARD
# ---------------------------

with pick_slot.container():

    if st.session_state.random_pick_id:

        row=filtered[filtered.objectid==st.session_state.random_pick_id].iloc[0]

        st.markdown(
        f"""
        <div class="card">
        <div class="pick-name">{row.objectname}</div>
        <div class="pick-meta">
        👥 {int(row.minplayers)}–{int(row.maxplayers)} |
        🧠 {row.avgweight:.2f} |
        ⭐ {row.baverage:.2f}
        <br>
        <a href="{row.bgg_url}" target="_blank">Open on BGG 🔗</a>
        </div>
        </div>
        """,
        unsafe_allow_html=True
        )

# ---------------------------
# TABLE
# ---------------------------

with right:

    table=pd.DataFrame({

        "Played Tonight":filtered.last_played==date.today(),

        "Game":filtered.objectname,

        "Players":filtered.apply(
            lambda r:f"👥 {int(r.minplayers)}–{int(r.maxplayers)}"
            if pd.notna(r.maxplayers)
            else f"👥 {int(r.minplayers)}+",
            axis=1
        ),

        "Weight":filtered.avgweight,

        "BGG Score":filtered.baverage.apply(
            lambda x:f"⭐ {x:.2f}" if pd.notna(x) else ""
        ),

        "BGG":filtered.bgg_url,

        "_oid":filtered.objectid
    })

    edited=st.data_editor(
        table.drop(columns="_oid"),
        hide_index=True,
        use_container_width=True,
        column_config={
            "BGG":st.column_config.LinkColumn("BGG",display_text="🔗")
        }
    )
