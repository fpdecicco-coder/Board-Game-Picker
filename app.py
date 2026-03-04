import time
from datetime import date
from pathlib import Path
from typing import Optional, List, Dict, Any
from xml.etree import ElementTree as ET

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Board Game Picker", layout="wide")

RECENT_PATH = Path("recently_played.csv")
COLLECTION_PATH = Path("collection.csv")  # ✅ local cache for instant loads
HEAVY_CUTOFF = 3.25

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
# BGG fetch (used only when refreshing CSV)
# ---------------------------
def _get_bgg_username() -> str:
    return st.secrets.get("BGG_USERNAME", "Frankie3788")


def _http_get(url: str, params: Optional[Dict[str, Any]] = None, timeout: int = 30) -> requests.Response:
    headers = {"User-Agent": "BoardGamePicker/1.0 (Streamlit)"}
    return requests.get(url, params=params, headers=headers, timeout=timeout)


def _looks_like_xml(text: str) -> bool:
    t = (text or "").lstrip()
    return t.startswith("<?xml") or t.startswith("<items") or t.startswith("<message") or t.startswith("<")


def _parse_collection_xml(xml_text: str) -> pd.DataFrame:
    root = ET.fromstring(xml_text)
    rows = []
    for item in root.findall("item"):
        oid = item.get("objectid")
        subtype = item.get("subtype", "")
        name_el = item.find("name")
        name = name_el.text.strip() if name_el is not None and name_el.text else ""

        stats = item.find("stats")
        minp = stats.get("minplayers") if stats is not None else None
        maxp = stats.get("maxplayers") if stats is not None else None

        rows.append(
            {
                "objectid": int(oid) if oid and oid.isdigit() else pd.NA,
                "objectname": name,
                "itemtype": subtype,
                "minplayers": pd.to_numeric(minp, errors="coerce"),
                "maxplayers": pd.to_numeric(maxp, errors="coerce"),
                "own": 1,
            }
        )

    df = pd.DataFrame(rows)
    df["itemtype"] = df["itemtype"].astype(str).str.lower().replace(
        {"boardgameexpansion": "expansion", "boardgame": "boardgame"}
    )
    return df


def _parse_thing_xml(xml_text: str) -> pd.DataFrame:
    root = ET.fromstring(xml_text)
    out = []
    for item in root.findall("item"):
        oid = item.get("id")
        stats = item.find("statistics")
        ratings = stats.find("ratings") if stats is not None else None

        avgweight = None
        bayes = None

        if ratings is not None:
            aw = ratings.find("averageweight")
            ba = ratings.find("bayesaverage")
            try:
                avgweight = float(aw.get("value")) if aw is not None and aw.get("value") not in (None, "N/A") else None
            except Exception:
                avgweight = None
            try:
                bayes = float(ba.get("value")) if ba is not None and ba.get("value") not in (None, "N/A") else None
            except Exception:
                bayes = None

        out.append(
            {
                "objectid": int(oid) if oid and oid.isdigit() else pd.NA,
                "avgweight": avgweight,
                "baverage": bayes,
            }
        )
    return pd.DataFrame(out)


def fetch_bgg_owned_collection_uncached(username: str) -> pd.DataFrame:
    """
    Uncached fetch: used ONLY when user clicks Refresh.
    Polls /collection until ready (BGG often returns 202).
    """
    url = "https://boardgamegeek.com/xmlapi2/collection"
    params = {"username": username, "own": 1, "stats": 1}

    wait_seconds = 2
    max_wait_total = 75
    waited = 0
    last_status = None

    while waited < max_wait_total:
        r = _http_get(url, params=params, timeout=30)
        last_status = r.status_code

        if r.status_code == 200 and _looks_like_xml(r.text):
            try:
                return _parse_collection_xml(r.text)
            except Exception:
                pass

        if r.status_code == 202:
            time.sleep(wait_seconds)
            waited += wait_seconds
            wait_seconds = min(wait_seconds * 2, 10)
            continue

        time.sleep(2)
        waited += 2

    raise RuntimeError(f"BGG collection still preparing or unavailable (last HTTP {last_status}). Try again in a minute.")


def fetch_bgg_things_stats_uncached(object_ids: List[int]) -> pd.DataFrame:
    if not object_ids:
        return pd.DataFrame(columns=["objectid", "avgweight", "baverage"])

    url = "https://boardgamegeek.com/xmlapi2/thing"
    all_rows = []

    BATCH = 75
    for i in range(0, len(object_ids), BATCH):
        batch = object_ids[i : i + BATCH]
        params = {"id": ",".join(map(str, batch)), "stats": 1}
        r = _http_get(url, params=params, timeout=30)
        if r.status_code != 200 or not _looks_like_xml(r.text):
            continue
        try:
            all_rows.append(_parse_thing_xml(r.text))
        except Exception:
            continue

    if not all_rows:
        return pd.DataFrame(columns=["objectid", "avgweight", "baverage"])
    return pd.concat(all_rows, ignore_index=True)


def refresh_collection_csv() -> None:
    username = _get_bgg_username()

    with st.status("Refreshing from BGG…", expanded=True) as status:
        status.write("Fetching owned collection…")
        base = fetch_bgg_owned_collection_uncached(username)

        base["bgg_url"] = base["objectid"].apply(
            lambda x: f"https://boardgamegeek.com/boardgame/{int(x)}" if pd.notna(x) else ""
        )

        ids = [int(x) for x in base["objectid"].dropna().astype(int).tolist()]
        status.write(f"Fetching ratings/weights for {len(ids)} games…")
        stats = fetch_bgg_things_stats_uncached(ids)

        df_new = base.merge(stats, on="objectid", how="left")

        if "maxplayers" in df_new.columns:
            df_new.loc[df_new["maxplayers"].isna() | (df_new["maxplayers"] <= 0), "maxplayers"] = pd.NA

        # Normalize types
        df_new["objectid"] = pd.to_numeric(df_new["objectid"], errors="coerce").astype("Int64")
        df_new["minplayers"] = pd.to_numeric(df_new["minplayers"], errors="coerce")
        df_new["maxplayers"] = pd.to_numeric(df_new["maxplayers"], errors="coerce")
        df_new["avgweight"] = pd.to_numeric(df_new["avgweight"], errors="coerce")
        df_new["baverage"] = pd.to_numeric(df_new["baverage"], errors="coerce")

        # Save
        df_new.to_csv(COLLECTION_PATH, index=False)

        status.update(label="Refresh complete ✅", state="complete")


@st.cache_data(ttl=60 * 60 * 24)
def load_collection_from_csv() -> pd.DataFrame:
    if not COLLECTION_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(COLLECTION_PATH)

    # Ensure expected columns exist
    expected = ["objectid", "objectname", "itemtype", "minplayers", "maxplayers", "avgweight", "baverage", "bgg_url"]
    for c in expected:
        if c not in df.columns:
            df[c] = pd.NA

    df["objectid"] = pd.to_numeric(df["objectid"], errors="coerce")
    df["minplayers"] = pd.to_numeric(df["minplayers"], errors="coerce")
    df["maxplayers"] = pd.to_numeric(df["maxplayers"], errors="coerce")
    df["avgweight"] = pd.to_numeric(df["avgweight"], errors="coerce")
    df["baverage"] = pd.to_numeric(df["baverage"], errors="coerce")

    return df


# ---------------------------
# Session defaults + reset
# ---------------------------
DEFAULTS = {
    "players": 4,
    "hide_expansions": True,
    "heavy_mode": False,
    "search": "",
    "random_pick_id": None,
    "trigger_random": False,
    "avoid_recent": True,
    "avoid_days": 14,
    "confirm_played_pick": False,
    "sort_display": "BBG Score",
    "pending_action": None,
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
# Header
# ---------------------------
st.title("🎲 Board Game Picker")
st.markdown('<div class="subtitle">Pick player count → get the games that fit.</div>', unsafe_allow_html=True)

left, right = st.columns([1, 3], gap="large")

# ---------------------------
# LEFT controls
# ---------------------------
with left:
    st.markdown('<div class="card">', unsafe_allow_html=True)

    st.slider("How many players tonight?", 1, 10, key="players")
    st.text_input("Search games", placeholder="e.g., Gloomhaven…", key="search")
    st.toggle("Hide expansions", key="hide_expansions")

    st.toggle("Avoid recently played in Random", key="avoid_recent")
    st.slider(
        "Avoid window (days)",
        1, 120,
        key="avoid_days",
        disabled=not st.session_state["avoid_recent"],
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🎲 Random", use_container_width=True):
            st.session_state["random_pick_id"] = None
            st.session_state["trigger_random"] = True
            st.session_state["confirm_played_pick"] = False
    with c2:
        if st.button("🔥 Heavy", use_container_width=True):
            st.session_state["heavy_mode"] = not st.session_state["heavy_mode"]
            st.session_state["random_pick_id"] = None
            st.session_state["confirm_played_pick"] = False
    with c3:
        st.button("↺ Reset", use_container_width=True, on_click=reset_filters)

    # ✅ CSV-first refresh
    if st.button("🔄 Refresh from BGG (update CSV)", use_container_width=True):
        try:
            refresh_collection_csv()
            load_collection_from_csv.clear()
            st.toast("Updated collection.csv ✅")
            st.rerun()
        except Exception as e:
            st.error(f"Refresh failed: {e}")

    if st.session_state["heavy_mode"]:
        st.markdown('<span class="badge badge-on">HEAVY MODE: ON</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="badge badge-off">HEAVY MODE: OFF</span>', unsafe_allow_html=True)

    st.markdown(
        f'<div class="mini">Heavy Mode filters to games with <b>Weight ≥ {HEAVY_CUTOFF:.2f}</b>.</div>',
        unsafe_allow_html=True,
    )

    if COLLECTION_PATH.exists():
        st.caption(f"Using local cache: `{COLLECTION_PATH.name}`")
    else:
        st.warning("No `collection.csv` found yet. Click **Refresh from BGG** once to create it.")

    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------
# DATA LOAD (FAST)
# ---------------------------
df = load_collection_from_csv()
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

# Round for display
filtered["avgweight"] = pd.to_numeric(filtered["avgweight"], errors="coerce").round(2)
filtered["baverage"] = pd.to_numeric(filtered["baverage"], errors="coerce").round(2)

filtered = filtered.reset_index(drop=True)

# ---------------------------
# Random pick selection
# ---------------------------
if st.session_state["trigger_random"]:
    st.session_state["trigger_random"] = False
    pool = filtered.copy()

    if st.session_state["avoid_recent"]:
        window = int(st.session_state["avoid_days"])
        pool = pool[(pool["days_ago"].isna()) | (pool["days_ago"] >= window)]

    if len(pool) > 0 and "objectid" in pool.columns:
        st.session_state["random_pick_id"] = int(pool.sample(1)["objectid"].iloc[0])
    else:
        st.session_state["random_pick_id"] = None

# ---------------------------
# Random pick card (LEFT)
# ---------------------------
with left:
    if st.session_state["random_pick_id"] is not None and "objectid" in filtered.columns:
        match = filtered[filtered["objectid"] == st.session_state["random_pick_id"]]
        if not match.empty:
            row = match.iloc[0]

            mn = int(row["minplayers"]) if pd.notna(row["minplayers"]) else None
            mx = int(row["maxplayers"]) if pd.notna(row["maxplayers"]) else None
            players_txt = f"{mn}–{mx}" if (mn is not None and mx is not None) else (f"{mn}+" if mn is not None else "")

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
                    👥 {players_txt} &nbsp;|&nbsp; 🧠 Weight {w_txt} &nbsp;|&nbsp; ⭐ BBG {s_txt}
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
# RIGHT panel: Sort + table with confirm
# ---------------------------
with right:
    st.session_state["sort_display"] = st.selectbox(
        "Sort by",
        ["BBG Score", "Weight", "Game Name", "Last Played (Newest)", "Last Played (Oldest)"],
        index=["BBG Score", "Weight", "Game Name", "Last Played (Newest)", "Last Played (Oldest)"].index(
            st.session_state.get("sort_display", "BBG Score")
        ),
    )

    table_df = filtered.copy()
    sort_choice = st.session_state["sort_display"]

    if sort_choice == "BBG Score":
        table_df = table_df.sort_values("baverage", ascending=False, na_position="last")
    elif sort_choice == "Weight":
        table_df = table_df.sort_values("avgweight", ascending=False, na_position="last")
    elif sort_choice == "Game Name":
        table_df = table_df.sort_values("objectname", ascending=True, na_position="last")
    elif sort_choice == "Last Played (Newest)":
        table_df = table_df.sort_values("last_played", ascending=False, na_position="last")
    else:
        table_df = table_df.sort_values("last_played", ascending=True, na_position="last")

    table_df = table_df.reset_index(drop=True)

    extra = " (Heavy Mode)" if st.session_state["heavy_mode"] else ""
    st.write(f"### {len(table_df)} games available for {players} players{extra}")
    st.caption("Toggle ✅ Played Tonight (you’ll be asked to confirm). Uncheck to undo.")

    editor_df = pd.DataFrame(
        {
            "Played Tonight": table_df["last_played"].apply(lambda d: (not pd.isna(d)) and (d == date.today())),
            "Game": table_df["objectname"],
            "Players": table_df.apply(
                lambda r: f"{int(r['minplayers'])}–{int(r['maxplayers'])}"
                if pd.notna(r["maxplayers"])
                else f"{int(r['minplayers'])}+",
                axis=1,
            ),
            "Weight": table_df["avgweight"],
            "BBG Score": table_df["baverage"],
            "Last Played": table_df["last_played"].astype(str).replace({"<NA>": "", "nan": ""}),
            "Days Ago": table_df["days_ago"],
            "🔗": table_df["bgg_url"],
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
        disabled=["Game", "Players", "Weight", "BBG Score", "Last Played", "Days Ago", "🔗"],
        column_config={
            "Played Tonight": st.column_config.CheckboxColumn("Played Tonight"),
            "🔗": st.column_config.LinkColumn("BGG", display_text="🔗"),
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
