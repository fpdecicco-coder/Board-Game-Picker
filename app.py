import random
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Board Game Picker", layout="wide")

RECENT_PATH = Path("recently_played.csv")

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
        background: rgba(255,255,255,0.88);
        box-shadow: 0 1px 6px rgba(0,0,0,0.05);
        margin-bottom: 12px;
      }

      .pick-title { font-size: 1.05rem; opacity: 0.8; margin-bottom: 4px; }
      .pick-name { font-size: 1.35rem; font-weight: 800; line-height: 1.15; }
      .pick-meta { margin-top: 8px; font-size: 0.95rem; opacity: 0.9; }

      .badge {
        display:inline-block;
        padding: 6px 10px;
        border-radius: 999px;
        font-weight: 800;
        font-size: 0.9rem;
        letter-spacing: 0.3px;
        margin-top: 10px;
      }
      .badge-on {
        background: rgba(220, 60, 60, 0.12);
        border: 1px solid rgba(220, 60, 60, 0.35);
        color: rgb(170, 30, 30);
      }
      .badge-off {
        background: rgba(40, 180, 120, 0.12);
        border: 1px solid rgba(40, 180, 120, 0.35);
        color: rgb(20, 120, 80);
      }

      .mini {
        opacity: 0.85;
        font-size: 0.9rem;
        margin-top: 8px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------
# Load collection
# ---------------------------
@st.cache_data
def load_collection():
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

    if "objectid" in df.columns:
        df["bgg_url"] = df["objectid"].apply(
            lambda x: f"https://boardgamegeek.com/boardgame/{int(x)}" if pd.notna(x) else ""
        )
    else:
        df["bgg_url"] = ""

    return df


# ---------------------------
# Recently played helpers
# ---------------------------
def load_recently_played() -> pd.DataFrame:
    if RECENT_PATH.exists():
        rp = pd.read_csv(RECENT_PATH)
        if "objectid" in rp.columns:
            rp["objectid"] = pd.to_numeric(rp["objectid"], errors="coerce")
        if "last_played" in rp.columns:
            rp["last_played"] = pd.to_datetime(rp["last_played"], errors="coerce").dt.date
        rp = rp.dropna(subset=["objectid"]).copy()
        return rp
    return pd.DataFrame(columns=["objectid", "last_played"])


def save_recently_played(rp: pd.DataFrame) -> None:
    rp_out = rp.copy()
    rp_out["objectid"] = rp_out["objectid"].astype(int)
    rp_out["last_played"] = rp_out["last_played"].astype(str)
    rp_out.to_csv(RECENT_PATH, index=False)


def mark_played(objectid: int, played_date: date | None = None) -> None:
    played_date = played_date or date.today()
    rp = load_recently_played()
    oid = int(objectid)

    if rp.empty:
        rp = pd.DataFrame([{"objectid": oid, "last_played": played_date}])
    else:
        if (rp["objectid"] == oid).any():
            rp.loc[rp["objectid"] == oid, "last_played"] = played_date
        else:
            rp = pd.concat(
                [rp, pd.DataFrame([{"objectid": oid, "last_played": played_date}])],
                ignore_index=True,
            )

    rp["last_played"] = pd.to_datetime(rp["last_played"], errors="coerce").dt.date
    rp = rp.dropna(subset=["objectid", "last_played"])
    rp = rp.drop_duplicates(subset=["objectid"], keep="last")
    rp = rp.sort_values("last_played", ascending=False)

    save_recently_played(rp)


def days_ago(d):
    if pd.isna(d):
        return pd.NA
    try:
        dd = d if isinstance(d, date) else pd.to_datetime(d).date()
        return (date.today() - dd).days
    except Exception:
        return pd.NA


# ---------------------------
# Session defaults + reset
# ---------------------------
DEFAULTS = {
    "players": 4,
    "hide_expansions": True,
    "sort_display": "BBG Score",
    "heavy_mode": False,
    "heavy_cutoff": 3.25,
    "search": "",
    "random_pick_id": None,
    "trigger_random": False,
    "avoid_recent": True,
    "avoid_days": 14,
    "confirm_played": False,
}

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


def reset_filters():
    for k, v in DEFAULTS.items():
        st.session_state[k] = v
    st.rerun()


# ---------------------------
# Header
# ---------------------------
st.title("🎲 Board Game Picker")
st.markdown('<div class="subtitle">Pick player count → get the games that fit.</div>', unsafe_allow_html=True)

df = load_collection()
left, right = st.columns([1, 3], gap="large")

# ---------------------------
# Controls (LEFT)
# ---------------------------
with left:
    st.markdown('<div class="card">', unsafe_allow_html=True)

    st.slider("How many players tonight?", 1, 10, key="players")
    st.text_input("Search games", placeholder="e.g., Concordia, Scythe, Wingspan…", key="search")
    st.toggle("Hide expansions", key="hide_expansions")
    st.selectbox("Sort by", ["BBG Score", "Weight", "Game Name"], key="sort_display")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🎲 Random", use_container_width=True):
            st.session_state["random_pick_id"] = None
            st.session_state["trigger_random"] = True
            st.session_state["confirm_played"] = False
    with c2:
        if st.button("🔥 Heavy", use_container_width=True):
            st.session_state["heavy_mode"] = not st.session_state["heavy_mode"]
            st.session_state["random_pick_id"] = None
            st.session_state["confirm_played"] = False
    with c3:
        st.button("↺ Reset", use_container_width=True, on_click=reset_filters)

    # Heavy status badge + cutoff
    if st.session_state["heavy_mode"]:
        st.markdown('<span class="badge badge-on">HEAVY MODE: ON</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="badge badge-off">HEAVY MODE: OFF</span>', unsafe_allow_html=True)

    st.slider(
        "Heavy cutoff (Weight ≥)",
        min_value=1.00,
        max_value=5.00,
        step=0.05,
        key="heavy_cutoff",
    )
    st.markdown(
        f'<div class="mini">Heavy Mode filters to games with <b>Weight ≥ {st.session_state["heavy_cutoff"]:.2f}</b>.</div>',
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.toggle("Avoid recently played in Random", key="avoid_recent")
    st.slider("Avoid window (days)", 1, 120, key="avoid_days")
    st.caption("Only affects Random picks. A game is only marked as played when you confirm it.")

    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------
# Filtering (RIGHT + used for Random pool too)
# ---------------------------
filtered = df.copy()

if st.session_state["hide_expansions"] and "itemtype" in filtered.columns:
    filtered = filtered[filtered["itemtype"] != "expansion"]

players = int(st.session_state["players"])
filtered = filtered[
    (filtered["minplayers"].notna())
    & (filtered["minplayers"] <= players)
    & ((filtered["maxplayers"].isna()) | (filtered["maxplayers"] >= players))
]

# Search filter
q = (st.session_state["search"] or "").strip()
if q:
    filtered = filtered[filtered["objectname"].astype(str).str.contains(q, case=False, na=False)]

# Heavy mode filter
if st.session_state["heavy_mode"] and "avgweight" in filtered.columns:
    cutoff = float(st.session_state["heavy_cutoff"])
    filtered = filtered[filtered["avgweight"].notna() & (filtered["avgweight"] >= cutoff)]

# Merge recently played
rp = load_recently_played()
if "objectid" in filtered.columns and not rp.empty:
    filtered = filtered.merge(rp, on="objectid", how="left")
else:
    filtered["last_played"] = pd.NA

filtered["days_ago"] = filtered["last_played"].apply(days_ago)

# Sorting (table view)
sd = st.session_state["sort_display"]
if sd == "BBG Score":
    filtered = filtered.sort_values("baverage", ascending=False, na_position="last")
elif sd == "Weight":
    filtered = filtered.sort_values("avgweight", ascending=False, na_position="last")
else:
    filtered = filtered.sort_values("objectname", ascending=True, na_position="last")

# Round numbers
filtered["avgweight"] = filtered["avgweight"].round(2)
filtered["baverage"] = filtered["baverage"].round(2)
filtered = filtered.reset_index(drop=True)

# ---------------------------
# Random pick selection (AFTER filtering + avoid recent option)
# ---------------------------
if st.session_state["trigger_random"]:
    st.session_state["trigger_random"] = False

    pool = filtered.copy()

    if st.session_state["avoid_recent"]:
        window = int(st.session_state["avoid_days"])
        # Exclude games played within the last N days
        pool = pool[(pool["days_ago"].isna()) | (pool["days_ago"] >= window)]

    if len(pool) > 0 and "objectid" in pool.columns:
        st.session_state["random_pick_id"] = int(pool.sample(1)["objectid"].iloc[0])
    else:
        st.session_state["random_pick_id"] = None

# ---------------------------
# Show Random Pick under controls (LEFT) + confirm-to-mark-played
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
            lp = row.get("last_played", pd.NA)
            da = row.get("days_ago", pd.NA)

            last_played_txt = "Never (in this app)" if pd.isna(lp) else f"{lp} ({int(da)} days ago)"

            st.markdown(
                f"""
                <div class="card">
                  <div class="pick-title">Tonight’s pick</div>
                  <div class="pick-name">{row['objectname']}</div>
                  <div class="pick-meta">
                    👥 {players_txt} &nbsp;|&nbsp; 🧠 Weight {w:.2f} &nbsp;|&nbsp; ⭐ BBG {s:.2f}
                    <br/>
                    🕒 Last played: {last_played_txt}
                    <br/>
                    <a href="{link}" target="_blank" rel="noopener noreferrer">Open on BGG 🔗</a>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Confirmation gate
            st.checkbox("Confirm we played this game tonight", key="confirm_played")

            if st.button(
                "✅ Mark as Played Tonight",
                use_container_width=True,
                disabled=not st.session_state["confirm_played"],
            ):
                mark_played(int(row["objectid"]), date.today())
                st.session_state["confirm_played"] = False
                st.success("Game marked as played!")
                st.rerun()
        else:
            st.info("Your random pick isn’t in the filtered list anymore. Try Random again.")

# ---------------------------
# Weight coloring
# ---------------------------
def weight_color(val):
    try:
        x = float(val)
    except Exception:
        return ""
    x = max(1.0, min(5.0, x))
    t = (x - 1.0) / 4.0
    r = int(40 + (220 - 40) * t)
    g = int(170 + (60 - 170) * t)
    b = 80
    return f"background-color: rgb({r},{g},{b}); color: white; font-weight: 700;"

# ---------------------------
# Display table (RIGHT)
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

    # Recently played columns (populated only when you click Mark as Played Tonight)
    display["Last Played"] = filtered["last_played"].astype(str).replace({"<NA>": "", "nan": ""})
    display["Days Ago"] = filtered["days_ago"]

    display["🔗"] = filtered["bgg_url"]

    styled = display.style.applymap(weight_color, subset=["Weight"]).format(
        {
            "Weight": "{:.2f}",
            "BBG Score": "{:.2f}",
            "Days Ago": "{:,.0f}",
        },
        na_rep="",
    )

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        column_config={
            "🔗": st.column_config.LinkColumn("BGG", display_text="🔗"),
        },
    )
