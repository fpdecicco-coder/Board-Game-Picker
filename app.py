import pandas as pd
import streamlit as st

st.set_page_config(page_title="KSGS Board Game Picker", layout="wide")

@st.cache_data
def load_data():
    df = pd.read_csv("collection.csv")

    if "own" in df.columns:
        df = df[df["own"] == 1].copy()

    for col in ["minplayers", "maxplayers", "avgweight", "baverage", "average", "numplays", "rating"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "maxplayers" in df.columns:
        df.loc[df["maxplayers"].isna() | (df["maxplayers"] <= 0), "maxplayers"] = pd.NA

    return df

df = load_data()

st.title("🎲 KSGS Board Game Picker")

players = st.slider("How many players tonight?", 1, 10, 4)

filtered = df.copy()

if "minplayers" in filtered.columns:
    filtered = filtered[filtered["minplayers"].notna()]

if "maxplayers" in filtered.columns:
    filtered = filtered[
        (filtered["minplayers"] <= players) &
        ((filtered["maxplayers"].isna()) | (filtered["maxplayers"] >= players))
    ]
else:
    filtered = filtered[filtered["minplayers"] <= players]

sort_display = st.selectbox(
    "Sort by",
    ["BGG Score (Geek Rating)", "Weight (Complexity)", "Average Rating", "Game Name"]
)

if sort_display == "BGG Score (Geek Rating)":
    sort_column = "baverage"
    descending = True
elif sort_display == "Weight (Complexity)":
    sort_column = "avgweight"
    descending = True
elif sort_display == "Average Rating":
    sort_column = "average"
    descending = True
else:
    sort_column = "objectname"
    descending = False

if sort_column in filtered.columns:
    filtered = filtered.sort_values(by=sort_column, ascending=not descending, na_position="last")

# Round numeric display columns to 2 decimal places
for col in ["avgweight", "baverage", "average"]:
    if col in filtered.columns:
        filtered[col] = filtered[col].round(2)

filtered = filtered.reset_index(drop=True)

st.write(f"### {len(filtered)} games available for {players} players")

display_cols_preferred = [
    "objectname",
    "minplayers",
    "maxplayers",
    "avgweight",
    "baverage",
    "average",
    "numplays",
    "rating"
]

display_cols = [c for c in display_cols_preferred if c in filtered.columns]

st.dataframe(
    filtered[display_cols],
    use_container_width=True,
    hide_index=True
)
