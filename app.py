import random
import time
import pandas as pd
import requests
import streamlit as st
import xml.etree.ElementTree as ET
from pathlib import Path

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

CATS_CACHE_PATH = Path("bgg_categories_cache.csv")

# ---------------------------
# BGG helpers
# ---------------------------
def fetch_bgg_thing_xml(objectid: int) -> str:
    url = "https://boardgamegeek.com/xmlapi2/thing"
    r = requests.get(url, params={"id": objectid, "stats": 1}, timeout=30)
    r.raise_for_status()
    return r.text

def parse_categories(xml_text: str) -> list[str]:
    root = ET.fromstring(xml_text)
    item = root.find("item")
    if item is None:
        return []
    cats = []
    for link in item.findall("link"):
        if link.attrib.get("type") == "boardgamecategory":
            v = link.attrib.get("value")
            if v:
                cats.append(v)
    return sorted(set(cats))

def load_categories_cache() -> pd.DataFrame:
    if CATS_CACHE_PATH.exists():
        try:
            return pd.read_csv(CATS_CACHE_PATH)
        except Exception:
            return pd.DataFrame(columns=["objectid", "categories"])
    return pd.DataFrame(columns=["objectid", "categories"])

def save_categories_cache(cache_df: pd.DataFrame) -> None:
    cache_df.to_csv(CATS_CACHE_PATH, index=False)

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

    # BGG link
    if "objectid" in df.columns:
        df["bgg_url"] = df["objectid"].apply(
            lambda x: f"https://boardgamegeek.com/boardgame/{int(x)}" if pd.notna(x) else ""
        )
    else:
        df["bgg_url"] = ""

    return df

df = load_collection()

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

    # Category refresh/enrichment
    st.markdown("---")
    st.markdown("**Categories**")
    refresh = st.button("🔄 Fetch / Refresh Categories", use_container_width=True)
    st.caption("Run once. Uses BGG API, then caches locally for faster loads.")

    st.markdown("---")
    if st.button("🎲 Random Game", use_container_width=True):
        if len(df) > 0:
            st.session_state["random_pick_id"] = int(df.sample(1)["objectid"].iloc[0]) if "objectid" in df.columns else None

    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------
# Category enrichment / cache merge
# ---------------------------
cats_cache = load_categories_cache()

if refresh and "objectid" in df.columns:
    # Build a set of ids already cached
    cached_ids = set(pd.to_numeric(cats_cache.get("objectid", pd.Series([])), errors="coerce").dropna().astype(int).tolist())

    ids_to_fetch = [int(x) for x in df["objectid"].dropna().astype(int).tolist() if int(x) not in cached_ids]

    progress = st.progress(0, text="Fetching categories from BGG…")
    new_rows = []

    total = len(ids_to_fetch)
    for i, oid in enumerate(ids_to_fetch, start=1):
        try:
            xml_text = fetch_bgg_thing_xml(oid)
            cats = parse_categories(xml_text)
            new_rows.append({"objectid": oid, "categories": "; ".join(cats)})
        except Exception:
            new_rows.append({"objectid": oid, "categories": ""})

        progress.progress(int(i / max(total, 1) * 100), text=f"Fetching categories… {i}/{total}")
        time.sleep(1.1)  # be polite to BGG

    progress.empty()

    if new_rows:
        cats_cache = pd.concat([cats_cache, pd.DataFrame(new_rows)], ignore_index=True)

    # de-dupe
    if "objectid" in cats_cache.columns:
        cats_cache["objectid"] = pd.to_numeric(cats_cache["objectid"], errors="coerce")
        cats_cache = cats_cache.drop_duplicates(subset=["objectid"], keep="last")

    save_categories_cache(cats_cache)
    st.success("Categories cached. Refresh the page if you don’t see them yet.")

# Merge categories onto df
if "objectid" in df.columns and "objectid" in cats_cache.columns:
    merged = df.merge(cats_cache, on="objectid", how="left")
else:
    merged = df.copy()
    merged["categories"] = ""

# Create a normalized categories list column
merged["categories"] = merged.get("categories", "").fillna("")
merged["categories_list"] = merged["categories"].apply(
    lambda s: [c.strip() for c in s.split(";") if c.strip()] if isinstance(s, str) else []
)

# ---------------------------
# Filtering
# ---------------------------
filtered = merged.copy()

if hide_expansions and "itemtype" in filtered.columns:
    filtered = filtered[filtered["itemtype"] != "expansion"]

# Player-count filter
filtered = filtered[
    (filtered["minplayers"].notna()) &
    (filtered["minplayers"] <= players) &
    ((filtered["maxplayers"].isna()) | (filtered["maxplayers"] >= players))
]

# Category filter UI (populate from cached categories)
all_categories = sorted({c for lst in filtered["categories_list"] for c in lst})
with left:
    selected_categories = st.multiselect("Filter by category", options=all_categories, default=[])

if selected_categories:
    selected_set = set(selected_categories)
    filtered = filtered[filtered["categories_list"].apply(lambda lst: bool(selected_set.intersection(set(lst))))]

# Sorting
if sort_display == "BBG Score":
    filtered = filtered.sort_values("baverage", ascending=False, na_position="last")
elif sort_display == "Weight":
    filtered = filtered.sort_values("avgweight", ascending=False, na_position="last")
else:
    filtered = filtered.sort_values("objectname", ascending=True, na_position="last")

# Round values
for col in ["avgweight", "baverage"]:
    if col in filtered.columns:
        filtered[col] = filtered[col].round(2)

filtered = filtered.reset_index(drop=True)

# ---------------------------
# Weight Coloring (Green -> Red)
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
# Display
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

    # 🔗 icon column (clickable)
    display["🔗"] = filtered["bgg_url"]

    # Optional: show categories (you can remove if you want it cleaner)
    if "categories" in filtered.columns:
        display["Category"] = filtered["categories"]

    styler = display.style.applymap(weight_color, subset=["Weight"]).format({
        "Weight": "{:.2f}",
        "BBG Score": "{:.2f}",
    })

    st.dataframe(
        styler,
        use_container_width=True,
        hide_index=True,
        column_config={
            "🔗": st.column_config.LinkColumn(
                "BGG",
                display_text="🔗"
            )
        },
    )
