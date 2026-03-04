from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Board Game Picker", layout="wide")

RECENT_PATH = Path("recently_played.csv")
COLLECTION_PATH = Path("collection.csv")  # local cache for instant loads
HEAVY_CUTOFF = 3.25  # fixed threshold

# ---------------------------
# Session defaults + reset
# ---------------------------
DEFAULTS = {
    "players": 4,
    "hide_expansions": False,  # default OFF
    "heavy_mode": False,
    "search": "",
    "random_pick_id": None,
    "last_random_pick_id": None,  # prevent repeat picks
    "trigger_random": False,
    "avoid_recent": True,
    "avoid_days": 30,  # ✅ default is now 30
    "confirm_played_pick": False,
    # table confirmation
    "pending_action": None,  # "mark" or "unmark"
    "pending_oid": None,
    "pending_name": None,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


def clear_editor_state():
    if "games_editor" in st.session_state:
        del st.session_state["games_editor"]


def reset_filters():
    for k, v in DEFAULTS.items():
        st.session_state[k] = v
    clear_editor_state()
    st.rerun()


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

      .mini {
        opacity: 0.85;
        font-size: 0.9rem;
        margin-top: 8px;
      }

      .admin-box {
        opacity: 0.85;
        border-top: 1px dashed rgba(0,0,0,0.12);
        margin-top: 14px;
        padding-top: 10px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

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
        return rp.dropna(subset=["objectid"]).copy()
    return pd.DataFrame(columns=["objectid", "last_played"])


def save_recently_played(rp: pd.DataFrame) -> None:
    rp_out = rp.copy()
    if rp_out.empty:
        rp_out = pd.DataFrame(columns=["objectid", "last_played"])
    else:
        rp_out["objectid"] = rp_out["objectid"].astype(int)
        rp_out["last_played"] = rp_out["last_played"].astype(str)
    rp_out.to_csv(RECENT_PATH, index=False)


def mark_played(objectid: int, played_date: Optional[date] = None) -> None:
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


def clear_played(oid: int) -> None:
    rp = load_recently_played()
    if rp.empty:
        return
    rp = rp[rp["objectid"].astype(int) != int(oid)].copy()
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
# Collection CSV (fast path)
# ---------------------------
@st.cache_data(ttl=60 * 60 * 24)
def load_collection_from_csv() -> pd.DataFrame:
    if not COLLECTION_PATH.exists():
        return pd.DataFrame()

    df = pd.read_csv(COLLECTION_PATH)

    expected = ["objectid", "objectname", "itemtype", "minplayers", "maxplayers", "avgweight", "baverage", "bgg_url"]
    for c in expected:
        if c not in df.columns:
            df[c] = pd.NA

    df["objectid"] = pd.to_numeric(df["objectid"], errors="coerce")
    df["minplayers"] = pd.to_numeric(df["minplayers"], errors="coerce")
    df["maxplayers"] = pd.to_numeric(df["maxplayers"], errors="coerce")
    df["avgweight"] = pd.to_numeric(df["avgweight"], errors="coerce")
    df["baverage"] = pd.to_numeric(df["baverage"], errors="coerce")

    df["itemtype"] = df["itemtype"].astype(str).str.lower().replace(
        {"boardgameexpansion": "expansion", "boardgame": "boardgame"}
    )

    # Ensure bgg_url exists even if missing / blank
    df["bgg_url"] = df["bgg_url"].astype(str).replace({"nan": "", "<NA>": ""}).str.strip()
    missing = df["bgg_url"].eq("") & df["objectid"].notna()
    df.loc[missing, "bgg_url"] = df.loc[missing, "objectid"].astype(int).apply(
        lambda oid: f"https://boardgamegeek.com/boardgame/{oid}"
    )

    return df


def save_uploaded_collection_csv(uploaded_file) -> None:
    df_in = pd.read_csv(uploaded_file)
    colmap = {c.lower().strip(): c for c in df_in.columns}

    def pick(*names):
        for n in names:
            key = n.lower().strip()
            if key in colmap:
                return colmap[key]
        return None

    oid_col = pick("objectid", "id", "object id", "gameid", "game id", "bggid", "bgg id")
    name_col = pick("objectname", "name", "game", "title")

    if oid_col is None or name_col is None:
        raise ValueError("That CSV needs columns for game ID and game name. (Ex: objectid + objectname)")

    out = pd.DataFrame()
    out["objectid"] = pd.to_numeric(df_in[oid_col], errors="coerce")
    out["objectname"] = df_in[name_col].astype(str)

    min_col = pick("minplayers", "min players", "minplayer")
    max_col = pick("maxplayers", "max players", "maxplayer")
    w_col = pick("avgweight", "averageweight", "weight")
    s_col = pick("baverage", "bayesaverage", "bgg score", "score")
    type_col = pick("itemtype", "subtype", "type")
    url_col = pick("bgg_url", "url", "bgg url", "link")

    out["minplayers"] = pd.to_numeric(df_in[min_col], errors="coerce") if min_col else pd.NA
    out["maxplayers"] = pd.to_numeric(df_in[max_col], errors="coerce") if max_col else pd.NA
    out["avgweight"] = pd.to_numeric(df_in[w_col], errors="coerce") if w_col else pd.NA
    out["baverage"] = pd.to_numeric(df_in[s_col], errors="coerce") if s_col else pd.NA
    out["itemtype"] = df_in[type_col].astype(str).str.lower() if type_col else "boardgame"

    if url_col:
        out["bgg_url"] = df_in[url_col].astype(str).replace({"nan": "", "<NA>": ""}).str.strip()
    else:
        out["bgg_url"] = ""

    out = out.dropna(subset=["objectid"])
    out["objectid"] = out["objectid"].astype(int)

    missing = out["bgg_url"].astype(str).str.strip().eq("")
    out.loc[missing, "bgg_url"] = out.loc[missing, "objectid"].apply(
        lambda oid: f"https://boardgamegeek.com/boardgame/{int(oid)}"
    )

    out.to_csv(COLLECTION_PATH, index=False)


# ---------------------------
# Header (changes when Heavy Mode is on)
# ---------------------------
title = "🔥🎲 Board Game Picker" if st.session_state["heavy_mode"] else "🎲 Board Game Picker"
st.title(title)
st.markdown('<div class="subtitle">Pick player count → get the games that fit.</div>', unsafe_allow_html=True)

left, right = st.columns([1, 3], gap="large")

# ---------------------------
# Load collection
# ---------------------------
df = load_collection_from_csv()

# ---------------------------
# LEFT controls
# ---------------------------
with left:
    st.markdown('<div class="card">', unsafe_allow_html=True)

    st.slider("How many players tonight?", 1, 10, key="players")

    # Badge near slider
    if st.session_state["heavy_mode"]:
        st.markdown("🔥 **Heavy Mode Active**")

    st.text_input("Search games", placeholder="Concordia.", key="search")  # ✅ placeholder updated

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🎲 Random", use_container_width=True):
            st.session_state["last_random_pick_id"] = st.session_state.get("random_pick_id")
            st.session_state["random_pick_id"] = None
            st.session_state["trigger_random"] = True
            st.session_state["confirm_played_pick"] = False
    with c2:
        if st.button("🔥 Heavy", use_container_width=True):
            st.session_state["heavy_mode"] = not st.session_state["heavy_mode"]
            st.session_state["random_pick_id"] = None
            st.session_state["confirm_played_pick"] = False
            st.rerun()
    with c3:
        st.button("↺ Reset", use_container_width=True, on_click=reset_filters)

    # ✅ banner under buttons
    if st.session_state["heavy_mode"]:
        st.error(f"🔥 HEAVY MODE ACTIVE — Showing games with weight ≥ {HEAVY_CUTOFF:.2f}")
    else:
        st.success("Normal Mode — All weights allowed")

    # Random pick placeholder directly under buttons/banner
    pick_slot = st.empty()

    # moved above Hide Expansions per request
    st.markdown(
        f'<div class="mini">Heavy Mode filters to games with <b>Weight ≥ {HEAVY_CUTOFF:.2f}</b>.</div>',
        unsafe_allow_html=True,
    )

    st.toggle("Hide expansions", key="hide_expansions")

    st.toggle("Avoid recently played in Random", key="avoid_recent")
    st.slider(
        "Avoid window (days)",
        1,
        120,
        key="avoid_days",
        disabled=not st.session_state["avoid_recent"],
    )

    if COLLECTION_PATH.exists():
        st.caption(f"Using local cache: `{COLLECTION_PATH.name}`")
    else:
        st.warning("No `collection.csv` found yet. Upload a CSV (bottom-left) to create it.")

    st.markdown('<div class="admin-box">', unsafe_allow_html=True)
    with st.expander("Admin: Update collection.csv", expanded=False):
        uploaded = st.file_uploader(
            "Upload / replace collection.csv",
            type=["csv"],
            help="Upload your saved collection.csv to update the app’s library.",
        )
        if uploaded is not None:
            try:
                save_uploaded_collection_csv(uploaded)
                load_collection_from_csv.clear()
                st.success("Uploaded and saved! Reloading…")
                st.rerun()
            except Exception as e:
                st.error(f"Upload failed: {e}")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

if df.empty:
    st.stop()

# ---------------------------
# Filtering
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

q = (st.session_state["search"] or "").strip()
if q:
    filtered = filtered[filtered["objectname"].astype(str).str.contains(q, case=False, na=False)]

if st.session_state["heavy_mode"] and "avgweight" in filtered.columns:
    filtered = filtered[filtered["avgweight"].notna() & (filtered["avgweight"] >= HEAVY_CUTOFF)]

# Merge recently played
rp = load_recently_played()
if "objectid" in filtered.columns and not rp.empty:
    filtered = filtered.merge(rp, on="objectid", how="left")
else:
    filtered["last_played"] = pd.NA

filtered["days_ago"] = filtered["last_played"].apply(days_ago)

filtered["avgweight"] = pd.to_numeric(filtered["avgweight"], errors="coerce").round(2)
filtered["baverage"] = pd.to_numeric(filtered["baverage"], errors="coerce").round(2)

filtered = filtered.reset_index(drop=True)

# ---------------------------
# Random pick selection
# ---------------------------
if st.session_state["trigger_random"]:
    st.session_state["trigger_random"] = False
    pool = filtered.copy()

    # ✅ Never allow expansions in Random
    if "itemtype" in pool.columns:
        pool = pool[pool["itemtype"].astype(str).str.lower() != "expansion"]

    if st.session_state["avoid_recent"]:
        window = int(st.session_state["avoid_days"])
        pool = pool[(pool["days_ago"].isna()) | (pool["days_ago"] >= window)]

    last_id = st.session_state.get("last_random_pick_id")
    if last_id is not None and "objectid" in pool.columns and len(pool) > 1:
        pool = pool[pool["objectid"].astype(int) != int(last_id)]

    if len(pool) > 0 and "objectid" in pool.columns:
        new_id = int(pool.sample(1)["objectid"].iloc[0])
        st.session_state["random_pick_id"] = new_id
        st.session_state["last_random_pick_id"] = new_id
    else:
        st.session_state["random_pick_id"] = None

# ---------------------------
# Random pick card
# ---------------------------
with pick_slot.container():
    if st.session_state["random_pick_id"] is not None and "objectid" in filtered.columns:
        match = filtered[filtered["objectid"] == st.session_state["random_pick_id"]]
        if not match.empty:
            row = match.iloc[0]

            mn = int(row["minplayers"]) if pd.notna(row["minplayers"]) else None
            mx = int(row["maxplayers"]) if pd.notna(row["maxplayers"]) else None
            players_txt = (
                f"👥 {mn}–{mx}" if (mn is not None and mx is not None) else (f"👥 {mn}+" if mn is not None else "")
            )

            w = row.get("avgweight", pd.NA)
            s = row.get("baverage", pd.NA)
            link = row.get("bgg_url", "")
            lp = row.get("last_played", pd.NA)
            da = row.get("days_ago", pd.NA)

            last_played_txt = "Never (in this app)" if pd.isna(lp) else f"{lp} ({int(da)} days ago)"
            w_txt = f"{float(w):.2f}" if pd.notna(w) else "—"
            s_txt = f"{float(s):.2f}" if pd.notna(s) else "—"

            st.markdown(
                f"""
                <div class="card">
                  <div class="pick-title">Tonight’s pick</div>
                  <div class="pick-name">{row['objectname']}</div>
                  <div class="pick-meta">
                    {players_txt} &nbsp;|&nbsp; 🧠 Weight {w_txt} &nbsp;|&nbsp; ⭐ {s_txt}
                    <br/>
                    🕒 Last played: {last_played_txt}
                    <br/>
                    <a href="{link}" target="_blank" rel="noopener noreferrer">Open on BGG 🔗</a>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            played_today = (not pd.isna(lp)) and (lp == date.today())
            if not played_today:
                st.checkbox("Confirm we played this game tonight", key="confirm_played_pick")
                if st.button(
                    "✅ Mark as Played Today (Pick)",
                    use_container_width=True,
                    disabled=not st.session_state["confirm_played_pick"],
                ):
                    mark_played(int(row["objectid"]), date.today())
                    st.session_state["confirm_played_pick"] = False
                    st.success("Saved!")
                    st.rerun()
            else:
                if st.button("↩️ Undo Played Today (Pick)", use_container_width=True):
                    clear_played(int(row["objectid"]))
                    st.success("Undone!")
                    st.rerun()


# ---------------------------
# Confirm dialog for table checkbox actions
# ---------------------------
def show_pending_dialog():
    action = st.session_state["pending_action"]
    oid = st.session_state["pending_oid"]
    name = st.session_state["pending_name"]
    if oid is None or name is None or action is None:
        return

    title = "Confirm played today" if action == "mark" else "Undo played today"
    prompt = f"Confirm you played **{name}** today?" if action == "mark" else f"Remove **{name}** from *played today*?"

    if hasattr(st, "dialog"):

        @st.dialog(title)
        def _dlg():
            st.write(prompt)
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ Confirm", use_container_width=True):
                    if action == "mark":
                        mark_played(int(oid), date.today())
                    else:
                        clear_played(int(oid))
                    st.session_state["pending_action"] = None
                    st.session_state["pending_oid"] = None
                    st.session_state["pending_name"] = None
                    clear_editor_state()
                    st.rerun()
            with c2:
                if st.button("Cancel", use_container_width=True):
                    st.session_state["pending_action"] = None
                    st.session_state["pending_oid"] = None
                    st.session_state["pending_name"] = None
                    clear_editor_state()
                    st.rerun()

        _dlg()
    else:
        st.warning(prompt)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Confirm"):
                if action == "mark":
                    mark_played(int(oid), date.today())
                else:
                    clear_played(int(oid))
                st.session_state["pending_action"] = None
                st.session_state["pending_oid"] = None
                st.session_state["pending_name"] = None
                clear_editor_state()
                st.rerun()
        with c2:
            if st.button("Cancel"):
                st.session_state["pending_action"] = None
                st.session_state["pending_oid"] = None
                st.session_state["pending_name"] = None
                clear_editor_state()
                st.rerun()


# ---------------------------
# RIGHT panel: Table ONLY + Heavy-mode header text
# ---------------------------
with right:
    table_df = filtered.copy()

    if st.session_state["heavy_mode"]:
        st.write(f"### 🔥 {len(table_df)} Heavy Games Available for {players} players")
    else:
        st.write(f"### {len(table_df)} games available for {players} players")

    st.caption("Toggle ✅ Played Tonight (you’ll be asked to confirm). Uncheck to undo.")

    editor_df = pd.DataFrame(
        {
            "Played Tonight": table_df["last_played"].apply(lambda d: (not pd.isna(d)) and (d == date.today())),
            "Game": table_df["objectname"],
            "Players": table_df.apply(
                lambda r: f"👥 {int(r['minplayers'])}–{int(r['maxplayers'])}"
                if pd.notna(r["maxplayers"])
                else f"👥 {int(r['minplayers'])}+",
                axis=1,
            ),
            "Weight": table_df["avgweight"].apply(
                lambda w: (
                    f"🟢 {w:.2f}" if pd.notna(w) and w < 2
                    else f"🟡 {w:.2f}" if pd.notna(w) and w < 3
                    else f"🟠 {w:.2f}" if pd.notna(w) and w < 3.75
                    else f"🔴 {w:.2f}" if pd.notna(w)
                    else ""
                )
            ),
            "BGG Score": table_df["baverage"].apply(lambda x: f"⭐ {float(x):.2f}" if pd.notna(x) else ""),
            "Last Played": table_df["last_played"].astype(str).replace({"<NA>": "", "nan": ""}),
            "Days Ago": table_df["days_ago"],
            "BGG": table_df["bgg_url"],
            "_oid": table_df["objectid"],
        }
    )

    baseline_key = "played_baseline_by_oid"
    if baseline_key not in st.session_state:
        st.session_state[baseline_key] = {
            int(oid): bool(val)
            for oid, val in zip(
                editor_df["_oid"].fillna(-1).astype(int).tolist(),
                editor_df["Played Tonight"].tolist(),
            )
            if oid != -1
        }

    edited = st.data_editor(
        editor_df.drop(columns=["_oid"]),
        key="games_editor",
        use_container_width=True,
        hide_index=True,
        disabled=["Game", "Players", "Weight", "BGG Score", "Last Played", "Days Ago", "BGG"],
        column_config={
            "Played Tonight": st.column_config.CheckboxColumn("Played Tonight"),
            "BGG": st.column_config.LinkColumn("BGG", display_text="🔗", width="small"),
        },
    )

    baseline_map = st.session_state[baseline_key]
    pending = None

    for played_now, oid, name, played_today_truth in zip(
        edited["Played Tonight"].tolist(),
        editor_df["_oid"].tolist(),
        editor_df["Game"].tolist(),
        editor_df["Played Tonight"].tolist(),
    ):
        if pd.isna(oid):
            continue
        oid = int(oid)
        was = bool(baseline_map.get(oid, False))
        now = bool(played_now)

        if now and not was:
            pending = ("mark", oid, name)
            break

        if (not now) and was and bool(played_today_truth):
            pending = ("unmark", oid, name)
            break

    if pending and st.session_state["pending_oid"] is None:
        action, oid, name = pending
        st.session_state["pending_action"] = action
        st.session_state["pending_oid"] = oid
        st.session_state["pending_name"] = name
        clear_editor_state()
        st.rerun()

    if st.session_state["pending_oid"] is not None:
        show_pending_dialog()

    st.session_state[baseline_key] = {
        int(oid): bool(val)
        for oid, val in zip(
            editor_df["_oid"].fillna(-1).astype(int).tolist(),
            editor_df["Played Tonight"].tolist(),
        )
        if oid != -1
    }
