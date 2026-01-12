import streamlit as st
import pandas as pd
import boto3
import requests
from PIL import Image
from io import BytesIO
import zipfile
import re
from datetime import datetime, UTC
import uuid

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Image → ZIP Uploader",
    page_icon="📦",
    layout="wide",
)

# ─────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────
if "admin_logs" not in st.session_state:
    st.session_state.admin_logs = []

# ─────────────────────────────────────────────
# SIDEBAR – CONTROL PANEL
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Control Panel")
    mode = st.radio("Mode", ["User mode", "Admin mode"])
    st.divider()

    if mode == "Admin mode":
        st.markdown("### 🛡 Admin Logs")
        if st.session_state.admin_logs:
            for log in reversed(st.session_state.admin_logs):
                st.code(log, language="text")
        else:
            st.info("No admin logs yet.")

# ─────────────────────────────────────────────
# TITLE
# ─────────────────────────────────────────────
st.title("📦 Image Downloader → Company Server")

# ─────────────────────────────────────────────
# LOAD SECRETS
# ─────────────────────────────────────────────
try:
    AWS_ACCESS_KEY = st.secrets["AWS_ACCESS_KEY_ID"]
    AWS_SECRET_KEY = st.secrets["AWS_SECRET_ACCESS_KEY"]
    S3_BUCKET = st.secrets["S3_BUCKET"]
except Exception:
    st.error("❌ Missing AWS secrets in Streamlit settings.")
    st.stop()

# ─────────────────────────────────────────────
# S3 CLIENT (EU-WEST-3)
# ─────────────────────────────────────────────
s3 = boto3.client(
    "s3",
    region_name="eu-west-3",
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
)

PUBLIC_BASE_URL = "https://static.ora.ma/"
UPLOAD_PREFIX = f"streamlit/{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}/"

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def sanitize_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", name).strip() or "image"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "image/*",
    "Referer": "https://glovoapp.com/",
}

def log_user(msg):
    st.write(msg)

def log_admin(msg):
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    st.session_state.admin_logs.append(f"[{timestamp}] {msg}")

# ─────────────────────────────────────────────
# FILE UPLOAD
# ─────────────────────────────────────────────
uploaded = st.file_uploader("📄 Upload CSV or XLSX", type=["csv", "xlsx"])

if uploaded:
    df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)

    st.markdown("### 📌 Columns detected")
    st.json(list(df.columns))

    product_col = st.selectbox("Product column", df.columns)
    url_col = st.selectbox("Image URL column", df.columns)

    if st.button("🚀 Process Images"):
        zip_buffer = BytesIO()
        server_urls = [None] * len(df)

        uploaded_count = 0
        skipped_count = 0

        progress = st.progress(0)
        status = st.empty()

        log_admin(f"START upload | file={uploaded.name} | rows={len(df)}")

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for idx, row in df.iterrows():
                progress.progress((idx + 1) / len(df))
                product = str(row[product_col])
                url = str(row[url_col])

                status.info(f"Processing row {idx+1}: {product}")
                log_user(f"🔄 Row {idx+1}: {product}")

                if not url.startswith("http"):
                    skipped_count += 1
                    log_user("❌ Invalid URL → skipped")
                    continue

                try:
                    r = requests.get(url, headers=BROWSER_HEADERS, timeout=20)
                    r.raise_for_status()
                    log_user("✅ HTTP 200")

                    img = Image.open(BytesIO(r.content))
                    if img.mode == "RGBA":
                        img = img.convert("RGB")

                    filename = sanitize_filename(product) + ".jpg"
                    s3_key = UPLOAD_PREFIX + filename

                    # CREATE RAW BYTES (ONCE)
                    img_buffer = BytesIO()
                    img.save(img_buffer, "JPEG", quality=90)
                    raw_bytes = img_buffer.getvalue()

                    # UPLOAD TO S3 (NEW STREAM)
                    s3.upload_fileobj(
                        BytesIO(raw_bytes),
                        S3_BUCKET,
                        s3_key,
                        ExtraArgs={"ContentType": "image/jpeg"},
                    )

                    public_url = PUBLIC_BASE_URL + s3_key
                    server_urls[idx] = public_url

                    # ZIP WRITE (RAW BYTES)
                    zipf.writestr(filename, raw_bytes)

                    uploaded_count += 1
                    log_user(f"✅ Uploaded → {public_url}")
                    log_admin(f"UPLOADED | row={idx+1} | {public_url}")

                except Exception as e:
                    skipped_count += 1
                    log_user(f"❌ ERROR: {e}")
                    log_admin(f"FAILED | row={idx+1} | {e}")

        df["Server Image URL"] = server_urls

        st.success(f"🎉 Uploaded: {uploaded_count} | Skipped: {skipped_count}")

        st.download_button(
            "⬇️ Download Images ZIP",
            data=zip_buffer.getvalue(),
            file_name="images.zip",
            mime="application/zip",
        )

        st.download_button(
            "⬇️ Download Updated CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="updated_with_server_links.csv",
            mime="text/csv",
        )

        log_admin(f"END upload | uploaded={uploaded_count} skipped={skipped_count}")
