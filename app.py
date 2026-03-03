import random
import pandas as pd
import streamlit as st

st.set_page_config(page_title="KSGS Board Game Picker", layout="wide")

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
# Header
# ---------------------------
st.title("🎲 KSGS Board Game Picker")
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

    if st.button("🎲 Random Game", use_container_width=True):
        if len(df) > 0:
            st.session_state["random_pick_id"] = random.choice(df["objectid"].dropna().tolist())

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

# Sorting
if sort_display == "BBG Score":
    filtered = filtered.sort_values("baverage", ascending=False, na_position="last")
elif sort_display == "Weight":
    filtered = filtered.sort_values("avgweight", ascending=False, na_position="last")
else:
    filtered = filtered.sort_values("objectname", ascending=True, na_position="last")

# Round numbers
filtered["avgweight"] = filtered["avgweight"].round(2)
filtered["baverage"] = filtered["baverage"].round(2)

filtered = filtered.reset_index(drop=True)

# ---------------------------
# Random Pick Display
# ---------------------------
if "random_pick_id" in st.session_state:
    rid = st.session_state["random_pick_id"]
    match = filtered[filtered["objectid"] == rid]
    if not match.empty:
        row = match.iloc[0]
        st.markdown(
            f"""
            <div class="card">
              <div style="font-size:1.6rem; font-weight:800;">
                🎲 Tonight’s Random Pick: {row['objectname']}
              </div>
              <div style="margin-top:8px;">
                👥 {int(row['minplayers'])}–{int(row['maxplayers']) if pd.notna(row['maxplayers']) else "+"} |
                🧠 Weight {row['avgweight']:.2f} |
                ⭐ BBG {row['baverage']:.2f}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

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

    return f"background-color: rgb({r},{g},{b}); color: white; font-weight: bold;"

# ---------------------------
# Display Table
# ---------------------------
with right:
    st.write(f"### {len(filtered)} games available for {players} players")

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
            "🔗": st.column_config.LinkColumn(
                "BGG",
                display_text="🔗"
            )
        },
    )
