import pandas as pd
import streamlit as st

st.set_page_config(page_title="Baird Game Picker", layout="wide")

@st.cache_data
def load_data():
    df = pd.read_csv("collection.csv")
    df = df[df["own"] == 1].copy()

    df["minplayers"] = pd.to_numeric(df["minplayers"], errors="coerce")
    df["maxplayers"] = pd.to_numeric(df["maxplayers"], errors="coerce")
    df["avgweight"] = pd.to_numeric(df["avgweight"], errors="coerce")
    df["baverage"] = pd.to_numeric(df["baverage"], errors="coerce")

    return df

df = load_data()

st.title("🎲 Baird Game Picker")

players = st.slider("How many players tonight?", 1, 10, 4)

filtered = df[
    (df["minplayers"] <= players) &
    (df["maxplayers"] >= players)
].copy()

sort_display = st.selectbox(
    "Sort by",
    ["BGG Score", "Weight", "Game Name"]
)

if sort_display == "BGG Score":
    sort_column = "baverage"
elif sort_display == "Weight":
    sort_column = "avgweight"
else:
    sort_column = "objectname"

filtered = filtered.sort_values(by=sort_column, ascending=False)



st.write(f"### {len(filtered)} Games Available")

st.dataframe(
    filtered[
        ["objectname", "minplayers", "maxplayers", "avgweight", "baverage"]
    ],
    use_container_width=True
)
