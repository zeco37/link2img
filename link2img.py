import streamlit as st
import pandas as pd
import boto3
import requests
from PIL import Image
from io import BytesIO
import zipfile
import re
from datetime import datetime

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Image → ZIP & Server",
    page_icon="📦",
    layout="wide",
)

# ─────────────────────────────────────────────
# SIDEBAR – TECHNICAL LOGS
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🧾 Technical Logs")
    show_logs = st.toggle("Show logs", value=False)
    log_box = st.container()

def log(msg):
    if show_logs:
        log_box.markdown(msg)

# ─────────────────────────────────────────────
# USER IDENTITY (STREAMLIT CLOUD)
# ─────────────────────────────────────────────
user_email = (
    st.experimental_user.email
    if hasattr(st, "experimental_user") and st.experimental_user.email
    else "unknown@user"
)

# ─────────────────────────────────────────────
# ADMIN USERS
# ─────────────────────────────────────────────
ADMINS = ["wally@ora.ma"]

# ─────────────────────────────────────────────
# ADMIN ACTIVITY LOG (IN-MEMORY)
# ─────────────────────────────────────────────
if "admin_logs" not in st.session_state:
    st.session_state.admin_logs = []

# ─────────────────────────────────────────────
# LOAD SECRETS
# ─────────────────────────────────────────────
AWS_ACCESS_KEY = st.secrets["AWS_ACCESS_KEY_ID"]
AWS_SECRET_KEY = st.secrets["AWS_SECRET_ACCESS_KEY"]
S3_BUCKET = st.secrets["S3_BUCKET"]

PUBLIC_BASE_URL = "https://static.ora.ma/streamlit/"

# ─────────────────────────────────────────────
# S3 CLIENT (EU-WEST-3 – PARIS)
# ─────────────────────────────────────────────
s3 = boto3.client(
    "s3",
    region_name="eu-west-3",
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
)

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def sanitize_filename(name):
    return re.sub(r"[^A-Za-z0-9_-]", "_", name).strip() or "image"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "image/*,*/*;q=0.8",
    "Referer": "https://glovoapp.com/",
}

# ─────────────────────────────────────────────
# UI HEADER
# ─────────────────────────────────────────────
st.title("📦 Image Downloader → Company Server")
st.caption(f"👤 Logged as **{user_email}**")
st.divider()

# ─────────────────────────────────────────────
# FILE UPLOAD
# ─────────────────────────────────────────────
uploaded = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx"])

if uploaded:
    df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)

    st.subheader("📌 Columns detected")
    st.json(list(df.columns))

    product_col = st.selectbox("Product name column", df.columns)
    url_col = st.selectbox("Image URL column", df.columns)

    if st.button("🚀 Process Images", type="primary"):

        session_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        folder_prefix = f"uploads/{session_id}/"

        zip_buffer = BytesIO()
        server_urls = [None] * len(df)

        uploaded_count = 0
        skipped_count = 0

        progress = st.progress(0)
        status = st.empty()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:

            for i, (idx, row) in enumerate(df.iterrows()):
                progress.progress((i + 1) / len(df))
                status.info(f"Processing image {i + 1} / {len(df)}")

                product = str(row[product_col]).strip()
                url = str(row[url_col]).strip()

                log(f"""
---
### 🔹 Row {idx + 1}
📦 **Product:** `{product}`
🔗 **URL:** {url}
""")

                if not url.startswith("http"):
                    skipped_count += 1
                    log("⚠️ Invalid URL — skipped")
                    continue

                filename = sanitize_filename(product) + ".jpg"
                s3_key = folder_prefix + filename

                try:
                    log("⬇️ Downloading image…")
                    r = requests.get(url, headers=HEADERS, timeout=25)
                    r.raise_for_status()

                    img = Image.open(BytesIO(r.content))
                    log(f"🖼️ Image mode: `{img.mode}`")

                    if img.mode != "RGB":
                        img = img.convert("RGB")

                    img_bytes = BytesIO()
                    img.save(img_bytes, "JPEG", quality=90)
                    img_bytes.seek(0)

                    log("☁️ Uploading to server…")
                    s3.upload_fileobj(
                        BytesIO(img_bytes.getvalue()),
                        S3_BUCKET,
                        s3_key,
                        ExtraArgs={"ContentType": "image/jpeg"},
                    )

                    public_url = PUBLIC_BASE_URL + s3_key
                    server_urls[idx] = public_url
                    uploaded_count += 1

                    zipf.writestr(filename, img_bytes.getvalue())
                    log(f"✅ Uploaded → {public_url}")

                except Exception as e:
                    skipped_count += 1
                    log(f"❌ Error: `{e}`")

        df["Server Image URL"] = server_urls

        # ─────────────────────────────────────────────
        # ADMIN ACTIVITY ENTRY (IN-APP ONLY)
        # ─────────────────────────────────────────────
        st.session_state.admin_logs.append({
            "user": user_email,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "csv_uploaded": uploaded.name,
            "product_column": product_col,
            "url_column": url_col,
            "uploaded": uploaded_count,
            "skipped": skipped_count,
            "zip": True,
            "csv": True,
        })

        # ─────────────────────────────────────────────
        # RESULTS
        # ─────────────────────────────────────────────
        st.success(f"🎉 Uploaded: {uploaded_count} | Skipped: {skipped_count}")

        st.download_button(
            "⬇️ Download Images ZIP",
            zip_buffer.getvalue(),
            "images.zip",
            "application/zip",
        )

        st.download_button(
            "⬇️ Download Updated CSV",
            df.to_csv(index=False).encode("utf-8"),
            "updated_with_server_links.csv",
            "text/csv",
        )

# ─────────────────────────────────────────────
# ADMIN ACTIVITY PANEL (UI ONLY)
# ─────────────────────────────────────────────
if user_email in ADMINS:
    st.divider()
    st.markdown("## 🛡️ Admin Activity Log")

    if not st.session_state.admin_logs:
        st.info("No activity yet.")
    else:
        for i, entry in enumerate(reversed(st.session_state.admin_logs), start=1):
            with st.expander(f"📌 Session {i} — {entry['user']}"):
                st.markdown(f"""
**👤 User:** {entry['user']}  
**🕒 Time:** {entry['time']}  
**📄 Uploaded CSV:** `{entry['csv_uploaded']}`  
**📌 Product Column:** `{entry['product_column']}`  
**🖼 Image URL Column:** `{entry['url_column']}`  

**⬆ Uploaded Images:** {entry['uploaded']}  
**⚠ Skipped Images:** {entry['skipped']}  

**📦 ZIP Generated:** ✅  
**📑 CSV Generated:** ✅  
""")
