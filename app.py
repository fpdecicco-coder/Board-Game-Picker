import random
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Board Game Picker", layout="wide")

# ---------------------------
# Styling
# ---------------------------
st.markdown(
    """
    <style>
      .block-container { padding-top: 1.2rem; }
      h1 { margin-bottom: 0.2rem; }
      .subtitle { opacity: 0.85; margin-top: -0.4rem; margin-bottom: 1rem; }
      .card {
        border: 1px solid rgba(0,0,0,0.08);
        border-radius: 14px;
        padding: 14px 16px;
        background: rgba(255,255,255,0.85);
        box-shadow: 0 1px 6px rgba(0,0,0,0.05);
        margin-bottom: 12px;
      }
      .pick-title { font-size: 1.05rem; opacity: 0.8; margin-bottom: 4px; }
      .pick-name { font-size: 1.35rem; font-weight: 800; line-height: 1.15; }
      .pick-meta { margin-top: 8px; font-size: 0.95rem; opacity: 0.9; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------
# Load Data
# ---------------------------
@st.cache_data
def load_data():
    df = pd.read_csv("collection.csv")

    if "own" in df.columns:
        df = df[df["own"] == 1].copy()

    for col in ["objectid", "minplayers", "maxplayers", "avgweight", "baverage"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "maxplayers" in df.columns:
        df.loc[df["maxplayers"].isna() | (df["maxplayers"] <= 0), "maxplayers"] = pd.NA

    if "itemtype" in df.columns:
        df["itemtype"] = df["itemtype"].astype(str).str.strip().str.lower()

    # Create BGG link
    if "objectid" in df.columns:
        df["bgg_url"] = df["objectid"].apply(
            lambda x: f"https://boardgamegeek.com/boardgame/{int(x)}" if pd.notna(x) else ""
        )
    else:
        df["bgg_url"] = ""

    return df

df = load_data()

# ---------------------------
# Session state defaults
# ---------------------------
if "heavy_mode" not in st.session_state:
    st.session_state["heavy_mode"] = False
if "random_pick_id" not in st.session_state:
    st.session_state["random_pick_id"] = None

# ---------------------------
# Header
# ---------------------------
st.title("🎲 Board Game Picker")
st.markdown('<div class="subtitle">Pick player count → get the games that fit.</div>', unsafe_allow_html=True)

left, right = st.columns([1, 3], gap="large")

# ---------------------------
# Sidebar Controls
# ---------------------------
with left:
    st.markdown('<div class="card">', unsafe_allow_html=True)

    players = st.slider("How many players tonight?", 1, 10, 4)
    hide_expansions = st.toggle("Hide expansions", value=True)
    sort_display = st.selectbox("Sort by", ["BBG Score", "Weight", "Game Name"])

    # Buttons row
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🎲 Random Game", use_container_width=True):
            st.session_state["random_pick_id"] = None  # clear first; will set after filtering
            st.session_state["trigger_random"] = True
    with c2:
        heavy_label = "🔥 I Like It Heavy" if not st.session_state["heavy_mode"] else "🔥 Heavy Mode: ON"
        if st.button(heavy_label, use_container_width=True):
            st.session_state["heavy_mode"] = not st.session_state["heavy_mode"]
            st.session_state["random_pick_id"] = None  # reset pick when mode changes

    # Heavy cutoff info
    HEAVY_CUTOFF = 3.25
    st.caption(f"Heavy Mode filters to games with Weight ≥ {HEAVY_CUTOFF:.2f}")

    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------
# Filtering
# ---------------------------
filtered = df.copy()

if hide_expansions and "itemtype" in filtered.columns:
    filtered = filtered[filtered["itemtype"] != "expansion"]

filtered = filtered[
    (filtered["minplayers"].notna()) &
    (filtered["minplayers"] <= players) &
    ((filtered["maxplayers"].isna()) | (filtered["maxplayers"] >= players))
]

# Heavy mode filter
HEAVY_CUTOFF = 3.25
if st.session_state["heavy_mode"] and "avgweight" in filtered.columns:
    filtered = filtered[filtered["avgweight"].notna() & (filtered["avgweight"] >= HEAVY_CUTOFF)]

# Sorting
if sort_display == "BBG Score":
    filtered = filtered.sort_values("baverage", ascending=False, na_position="last")
elif sort_display == "Weight":
    filtered = filtered.sort_values("avgweight", ascending=False, na_position="last")
else:
    filtered = filtered.sort_values("objectname", ascending=True, na_position="last")

# Round numbers for display
filtered["avgweight"] = filtered["avgweight"].round(2)
filtered["baverage"] = filtered["baverage"].round(2)

filtered = filtered.reset_index(drop=True)

# ---------------------------
# Random pick selection (AFTER filtering)
# ---------------------------
if st.session_state.get("trigger_random", False):
    st.session_state["trigger_random"] = False
    if len(filtered) > 0 and "objectid" in filtered.columns:
        st.session_state["random_pick_id"] = int(filtered.sample(1)["objectid"].iloc[0])
    else:
        st.session_state["random_pick_id"] = None

# ---------------------------
# Show Random Pick directly under buttons (LEFT PANEL)
# ---------------------------
with left:
    if st.session_state["random_pick_id"] is not None and "objectid" in filtered.columns:
        match = filtered[filtered["objectid"] == st.session_state["random_pick_id"]]
        if not match.empty:
            row = match.iloc[0]
            mn = int(row["minplayers"]) if pd.notna(row["minplayers"]) else None
            mx = int(row["maxplayers"]) if pd.notna(row["maxplayers"]) else None
            players_txt = f"{mn}–{mx}" if (mn is not None and mx is not None) else (f"{mn}+" if mn is not None else "")
            w = row["avgweight"]
            s = row["baverage"]
            link = row.get("bgg_url", "")

            st.markdown(
                f"""
                <div class="card">
                  <div class="pick-title">Tonight’s pick</div>
                  <div class="pick-name">{row['objectname']}</div>
                  <div class="pick-meta">
                    👥 {players_txt} &nbsp;|&nbsp; 🧠 Weight {w:.2f} &nbsp;|&nbsp; ⭐ BBG {s:.2f}
                    <br/>
                    <a href="{link}" target="_blank" rel="noopener noreferrer">Open on BGG 🔗</a>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.info("Your random pick isn’t in the filtered list anymore. Try Random Game again.")

# ---------------------------
# Weight Coloring
# ---------------------------
def weight_color(val):
    try:
        x = float(val)
    except:
        return ""

    x = max(1.0, min(5.0, x))
    t = (x - 1.0) / 4.0

    r = int(40 + (220 - 40) * t)
    g = int(170 + (60 - 170) * t)
    b = 80

    return f"background-color: rgb({r},{g},{b}); color: white; font-weight: 700;"

# ---------------------------
# Display Table (RIGHT PANEL)
# ---------------------------
with right:
    extra = " (Heavy Mode)" if st.session_state["heavy_mode"] else ""
    st.write(f"### {len(filtered)} games available for {players} players{extra}")

    display = pd.DataFrame()
    display["Game"] = filtered["objectname"]

    display["Players"] = filtered.apply(
        lambda r: f"{int(r['minplayers'])}–{int(r['maxplayers'])}"
        if pd.notna(r["maxplayers"])
        else f"{int(r['minplayers'])}+",
        axis=1
    )

    display["Weight"] = filtered["avgweight"]
    display["BBG Score"] = filtered["baverage"]
    display["🔗"] = filtered["bgg_url"]

    styled = display.style.applymap(weight_color, subset=["Weight"]).format({
        "Weight": "{:.2f}",
        "BBG Score": "{:.2f}",
    })

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        column_config={
            "🔗": st.column_config.LinkColumn("BGG", display_text="🔗")
        },
    )
