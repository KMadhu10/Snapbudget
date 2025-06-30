import streamlit as st
import pandas as pd
import boto3
import json
from datetime import datetime
from boto3.dynamodb.conditions import Key
import os



USE_AWS = False  # Flip this to True when AWS is active

st.set_page_config(page_title="📈 SnapBudget Dashboard", layout="wide")
st.title("📈 SnapBudget – Expense Dashboard")
st.write("Here’s your spending overview from all processed receipts.")

if USE_AWS:
    dynamodb = boto3.resource("dynamodb", region_name="ap-south-1")
    table = dynamodb.Table("snapbudget_receipts")
else:
    dynamodb = None
    table = None

@st.cache_data
def load_data():
    try:
        if USE_AWS:
            response = table.query(KeyConditionExpression=Key("username").eq("madhu"))
            data = response.get("Items", [])
        else:
            with open("results.json", "r") as f:
                data = [json.loads(line) for line in f]

        for entry in data:
            if isinstance(entry.get("items"), str):
                entry["items"] = json.loads(entry["items"])
            if isinstance(entry.get("category_breakdown"), str):
                entry["category_breakdown"] = json.loads(entry["category_breakdown"])

        return pd.DataFrame(data)

    except Exception as e:
        st.error(f"Failed to load data: {e}")
        return pd.DataFrame()

df = load_data()

if df.empty:
    st.warning("No receipts found yet. Upload one on the main SnapBudget page.")
else:
    rows = []
    for _, row in df.iterrows():
        for item in row["items"]:
            rows.append({
                "timestamp": row["timestamp"],
                "category": max(row["category_breakdown"], key=row["category_breakdown"].get),
                "item": item["name"],
                "price": item["price"],
                "image_url": row.get("image_url")
            })

    receipt_df = pd.DataFrame(rows)
    receipt_df["timestamp"] = pd.to_datetime(receipt_df["timestamp"])
    receipt_df["date"] = receipt_df["timestamp"].dt.date
    receipt_df["week"] = receipt_df["timestamp"].dt.isocalendar().week
    receipt_df = receipt_df[(receipt_df["price"] >= 1) & (receipt_df["price"] <= 10000)]

    st.metric("💰 Total Spent", f"₹{receipt_df['price'].sum()}")

    st.subheader("🧾 Spending by Category")
    st.bar_chart(receipt_df.groupby("category")["price"].sum().sort_values(ascending=False))

    st.subheader("🔁 Frequent Items")
    st.write(receipt_df["item"].value_counts().head(3))

    st.subheader("📆 Weekly Spending Breakdown")
    st.bar_chart(receipt_df.groupby("week")["price"].sum())

    st.subheader("📅 Expenses Over Time")
    st.line_chart(receipt_df.groupby("date")["price"].sum())

st.subheader("🧾 Receipt Images")
displayed = set()

if not USE_AWS:
    with open("results.json", "r") as f:
        raw_data = [json.loads(line) for line in f]

    filtered_data = []

    for entry in raw_data:
        image_url = entry.get("image_url", "").strip().lower()
        if not image_url or image_url == "0" or not image_url.startswith("http"):
            filtered_data.append(entry)
            continue

        if image_url in displayed:
            filtered_data.append(entry)
            continue

        st.markdown(f"Receipt Date: {pd.to_datetime(entry['timestamp']).date()}")
        st.image(entry["image_url"], width=300)

        if st.button(f"🗑 Delete This Receipt", key=entry["timestamp"]):
            st.warning("Deleting this receipt...")

            # Filter out the entry to delete
            new_data = [e for e in raw_data if e["timestamp"] != entry["timestamp"]]
            with open("results.json", "w") as f:
                for e in new_data:
                    json.dump(e, f)
                    f.write("\n")

            st.rerun()


        filtered_data.append(entry)
        displayed.add(image_url)