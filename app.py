import random
import pandas as pd
import streamlit as st

# ---------------------------
# Page + light styling
# ---------------------------
st.set_page_config(page_title="KSGS Board Game Picker", layout="wide")

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
        background: rgba(255,255,255,0.75);
        box-shadow: 0 1px 6px rgba(0,0,0,0.04);
        margin-bottom: 12px;
      }
      .pill {
        display:inline-block;
        padding: 4px 10px;
        border-radius: 999px;
        border: 1px solid rgba(0,0,0,0.10);
        margin-right: 6px;
        font-size: 0.9rem;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------
# Load + clean data
# ---------------------------
@st.cache_data
def load_data():
    df = pd.read_csv("collection.csv")

    # Owned only (safe even if your export already filters)
    if "own" in df.columns:
        df = df[df["own"] == 1].copy()

    # Numeric conversions
    for col in ["minplayers", "maxplayers", "avgweight", "baverage", "rating", "minplaytime", "maxplaytime", "playingtime"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Treat maxplayers <= 0 as unknown
    if "maxplayers" in df.columns:
        df.loc[df["maxplayers"].isna() | (df["maxplayers"] <= 0), "maxplayers"] = pd.NA

    # Normalize itemtype if present
    if "itemtype" in df.columns:
        df["itemtype"] = df["itemtype"].astype(str).str.strip().str.lower()

    return df

df = load_data()

# ---------------------------
# Header
# ---------------------------
st.title("🎲 KSGS Board Game Picker")
st.markdown('<div class="subtitle">Pick player count → get the games that fit, sorted how you want.</div>', unsafe_allow_html=True)

# ---------------------------
# Sidebar controls
# ---------------------------
left, right = st.columns([1, 3], gap="large")

with left:
    st.markdown('<div class="card">', unsafe_allow_html=True)

    players = st.slider("How many players tonight?", 1, 10, 4)

    hide_expansions = st.toggle("Hide expansions", value=True)

    sort_display = st.selectbox(
        "Sort by",
        ["BBG Score", "Weight", "Game Name"]
    )

    st.markdown("---")
    st.caption("Tip: ‘BBG Score’ is BGG’s Bayesian score (more stable than raw averages).")

    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------
# Filtering
# ---------------------------
filtered = df.copy()

# Hide expansions toggle (your file has itemtype: standalone / expansion)
if hide_expansions and "itemtype" in filtered.columns:
    filtered = filtered[filtered["itemtype"] != "expansion"]

# Require minplayers
if "minplayers" in filtered.columns:
    filtered = filtered[filtered["minplayers"].notna()]

# Player-count filter
if "maxplayers" in filtered.columns:
    filtered = filtered[
        (filtered["minplayers"] <= players) &
        ((filtered["maxplayers"].isna()) | (filtered["maxplayers"] >= players))
    ]
else:
    filtered = filtered[filtered["minplayers"] <= players]

# ---------------------------
# Sorting
# ---------------------------
if sort_display == "BBG Score":
    sort_column = "baverage"
    descending = True
elif sort_display == "Weight":
    sort_column = "avgweight"
    descending = True
else:
    sort_column = "objectname"
    descending = False

if sort_column in filtered.columns:
    filtered = filtered.sort_values(by=sort_column, ascending=not descending, na_position="last")

# Round for display
for col in ["avgweight", "baverage"]:
    if col in filtered.columns:
        filtered[col] = filtered[col].round(2)

filtered = filtered.reset_index(drop=True)

# ---------------------------
# Random game button
# ---------------------------
with left:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    if st.button("🎲 Random Game", use_container_width=True):
        if len(filtered) > 0:
            st.session_state["random_pick_idx"] = random.randrange(len(filtered))
        else:
            st.session_state["random_pick_idx"] = None
    st.markdown('</div>', unsafe_allow_html=True)

# Show random pick (if chosen)
random_pick = None
if "random_pick_idx" in st.session_state and st.session_state["random_pick_idx"] is not None:
    idx = st.session_state["random_pick_idx"]
    if 0 <= idx < len(filtered):
        random_pick = filtered.iloc[idx]

# ---------------------------
# Weight coloring (green -> red)
# ---------------------------
def weight_bg(val):
    """
    avgweight is typically ~1.0 to ~5.0.
    We'll map 1 => green, 5 => red.
    """
    try:
        x = float(val)
    except Exception:
        return ""

    # clamp
    x = max(1.0, min(5.0, x))
    t = (x - 1.0) / 4.0  # 0..1

    # green -> red gradient
    r = int(46 + (220 - 46) * t)
    g = int(160 + (60 - 160) * t)
    b = int(90 + (60 - 90) * t)

    return f"background-color: rgb({r},{g},{b}); color: white; font-weight: 700;"

# ---------------------------
# Display
# ---------------------------
with right:
    # Highlight random pick
    if random_pick is not None:
        name = random_pick.get("objectname", "Random Pick")
        minp = random_pick.get("minplayers", "")
        maxp = random_pick.get("maxplayers", "")
        w = random_pick.get("avgweight", "")
        score = random_pick.get("baverage", "")
        year = random_pick.get("yearpublished", "")

        pills = []
        if pd.notna(minp) and pd.notna(maxp):
            pills.append(f'<span class="pill">👥 {int(minp)}–{int(maxp)} players</span>')
        elif pd.notna(minp):
            pills.append(f'<span class="pill">👥 {int(minp)}+ players</span>')
        if pd.notna(w):
            pills.append(f'<span class="pill">🧠 Weight {w:.2f}</span>')
        if pd.notna(score):
            pills.append(f'<span class="pill">⭐ BBG {score:.2f}</span>')
        if pd.notna(year):
            pills.append(f'<span class="pill">📅 {int(year)}</span>')

        st.markdown(
            f"""
            <div class="card">
              <div style="font-size:1.05rem; opacity:0.75;">Tonight’s random pick:</div>
              <div style="font-size:1.6rem; font-weight:800; margin-top: 2px;">{name}</div>
              <div style="margin-top:10px;">{''.join(pills)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write(f"### {len(filtered)} games available for {players} players")

    # Build a clean display table with renamed columns
    display = pd.DataFrame()
    display["Game"] = filtered["objectname"] if "objectname" in filtered.columns else ""

    # Players range
    if "minplayers" in filtered.columns and "maxplayers" in filtered.columns:
        def p_range(row):
            mn = row["minplayers"]
            mx = row["maxplayers"]
            if pd.isna(mn) and pd.isna(mx):
                return ""
            if pd.isna(mx):
                return f"{int(mn)}+"
            return f"{int(mn)}–{int(mx)}"
        display["Players"] = filtered.apply(p_range, axis=1)
    elif "minplayers" in filtered.columns:
        display["Players"] = filtered["minplayers"].apply(lambda x: f"{int(x)}+" if pd.notna(x) else "")

    # Weight + BBG score
    if "avgweight" in filtered.columns:
        display["Weight"] = filtered["avgweight"]
    if "baverage" in filtered.columns:
        display["BBG Score"] = filtered["baverage"]

    # Optional: your rating (kept, but you can remove if you want)
    if "rating" in filtered.columns:
        # show blanks instead of 0
        display["Your Rating"] = filtered["rating"].where(filtered["rating"].notna() & (filtered["rating"] > 0), pd.NA)

    # Style weight column
    styler = display.style
    if "Weight" in display.columns:
        styler = styler.applymap(weight_bg, subset=["Weight"])

    # Keep numbers to 2 decimals
    fmt = {}
    if "Weight" in display.columns:
        fmt["Weight"] = "{:.2f}"
    if "BBG Score" in display.columns:
        fmt["BBG Score"] = "{:.2f}"
    if "Your Rating" in display.columns:
        fmt["Your Rating"] = "{:.1f}"  # your rating usually fine at 1 decimal

    styler = styler.format(fmt, na_rep="")

    st.dataframe(styler, use_container_width=True, hide_index=True)
