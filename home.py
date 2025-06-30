import streamlit as st
import requests
import json
import pandas as pd



# Flask Backend URLs
FLASK_UPLOAD_URL = "http://127.0.0.1:5000/upload"
FLASK_PING_URL = "http://127.0.0.1:5000/ping"

st.set_page_config(page_title="SnapBudget - Smart Receipt Analyzer", layout="wide")
st.title("💸 SnapBudget – Smart Receipt Analyzer")
st.write("Upload a receipt and get personalized spending insights instantly.")

# --- Session State ---
if 'uploaded_file' not in st.session_state:
    st.session_state.uploaded_file = None
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = None
if 'backend_status' not in st.session_state:
    st.session_state.backend_status = "Checking..."

# --- Check Backend ---
if st.session_state.backend_status == "Checking...":
    try:
        ping = requests.get(FLASK_PING_URL, timeout=5)
        if ping.status_code == 200:
            st.session_state.backend_status = "🟢 Connected"
        else:
            st.session_state.backend_status = "🔴 Unresponsive"
    except Exception as e:
        st.session_state.backend_status = f"🔴 Error: {e}"
    st.toast(st.session_state.backend_status)

st.sidebar.write(f"Backend Status: {st.session_state.backend_status}")

# --- Upload Section ---
uploaded_file = st.file_uploader("📤 Upload your receipt (PNG, JPG, JPEG)", type=["png", "jpg", "jpeg"])
if uploaded_file:
    st.image(uploaded_file, caption="Uploaded Receipt", use_container_width=True)
    if st.button("🚀 Process Receipt"):
        st.info("Uploading to backend and analyzing...")

        files = {
            'file': (
                uploaded_file.name,
                uploaded_file.getvalue(),
                uploaded_file.type
            )
        }

        try:
            res = requests.post(FLASK_UPLOAD_URL, files=files)
            if res.status_code == 200:
                st.success("✅ Receipt processed successfully.")
                st.session_state.uploaded_file = uploaded_file
                st.session_state.processed_data = res.json()

                # START OF ADDED DEBUGGING PRINT
                print(f"Streamlit Received Data (home.py): {json.dumps(st.session_state.processed_data, indent=2)}")
                # END OF ADDED DEBUGGING PRINT

            else:
                st.error(f"❌ Server error: {res.status_code}")
                try:
                    st.error(res.json().get("error", "No error message."))
                except:
                    st.error(res.text)
        except requests.exceptions.ConnectionError:
            st.error("❌ Cannot connect to Flask backend. Is it running?")
        except Exception as e:
            st.error(f"Unexpected error: {e}")

# --- Display Results ---
# Ensure processed_data is a dictionary before trying to access its keys
if st.session_state.processed_data and isinstance(st.session_state.processed_data, dict):
    data = st.session_state.processed_data
    st.subheader("🧾 Receipt Summary")
    st.markdown(f"Total Spent: ₹{data.get('total', 0)}")

    # Items Table
    if isinstance(data.get('items'), list) and data.get('items'): # Added check for empty list
        st.subheader("📦 Items")
        df = pd.DataFrame(data['items'])
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("No items found in receipt.")

    # Categories Chart
    if isinstance(data.get("category_breakdown"), dict) and data.get("category_breakdown"): # Added check for empty dict
        st.subheader("📊 Category Breakdown")
        chart_df = pd.DataFrame({
            "Category": list(data["category_breakdown"].keys()),
            "Amount": list(data["category_breakdown"].values())
        })
        st.bar_chart(chart_df.set_index("Category"))
    else:
        st.warning("Category breakdown is missing or empty.")

    # Savings Tip
    st.subheader("💡 Savings Tip")
    st.info(data.get("savings_tip", "No tip available."))

    # Display processed image from backend (served by Flask)
    image_url = data.get("image_url")
    if image_url and image_url.startswith("http"):
        st.subheader("🖼 Processed Receipt")
        st.image(image_url, caption="Stored Image from Flask Backend", use_container_width=True)
    else:
        st.warning("Processed image URL missing or invalid.")

    # Reset button
    if st.button("🔁 Upload Another"):
        st.session_state.uploaded_file = None
        st.session_state.processed_data = None
        st.experimental_rerun()

# Message if nothing uploaded
if not uploaded_file and not st.session_state.processed_data:
    st.info("Please upload a receipt to get started.")