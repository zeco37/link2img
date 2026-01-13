import streamlit as st
import pandas as pd
import boto3
import requests
from PIL import Image
from io import BytesIO
import zipfile
import re
from datetime import datetime, timezone
import uuid

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Image → ZIP & Server",
    page_icon="📦",
    layout="wide",
)

st.title("📦 Image Downloader → Company Server")

# ─────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────
if "user_logs" not in st.session_state:
    st.session_state.user_logs = []

if "admin_logs" not in st.session_state:
    st.session_state.admin_logs = []

def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def log_user(msg):
    st.session_state.user_logs.append(msg)

def log_admin(msg):
    st.session_state.admin_logs.append(f"[{now_utc()}] {msg}")

# ─────────────────────────────────────────────
# SIDEBAR CONTROL PANEL
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Control Panel")
    mode = st.radio("Mode", ["User mode", "Admin mode"])
    st.divider()

    if mode == "User mode":
        st.markdown("### 📋 User Logs")
        if st.session_state.user_logs:
            for l in st.session_state.user_logs:
                st.markdown(f"- {l}")
        else:
            st.caption("No activity yet.")

    if mode == "Admin mode":
        st.markdown("### 🛡 Admin Logs")
        if st.session_state.admin_logs:
            for l in reversed(st.session_state.admin_logs):
                st.code(l)
        else:
            st.info("No admin logs yet.")

# ─────────────────────────────────────────────
# LOAD SECRETS
# ─────────────────────────────────────────────
try:
    AWS_ACCESS_KEY = st.secrets["AWS_ACCESS_KEY_ID"]
    AWS_SECRET_KEY = st.secrets["AWS_SECRET_ACCESS_KEY"]
    S3_BUCKET = st.secrets["S3_BUCKET"]
    AWS_REGION = "eu-west-3"
    PUBLIC_BASE_URL = "https://static.ora.ma/streamlit/"
except Exception:
    st.error("❌ Missing AWS secrets")
    st.stop()

s3 = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION,
)

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def sanitize_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", name).strip() or "image"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "image/*",
    "Referer": "https://glovoapp.com/",
}

# ─────────────────────────────────────────────
# FILE UPLOAD
# ─────────────────────────────────────────────
uploaded = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx"])

if uploaded:
    df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)

    st.subheader("📌 Columns detected")
    st.json(list(df.columns))

    product_col = st.selectbox("Product column", df.columns)
    url_col = st.selectbox("Image URL column", df.columns)

    if st.button("🚀 Process Images"):
        # Reset user logs
        st.session_state.user_logs = []

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        folder_prefix = f"streamlit/{run_id}/"

        log_admin(f"START run_id={run_id} rows={len(df)}")

        zip_buffer = BytesIO()
        server_urls = [None] * len(df)

        progress = st.progress(0)
        status = st.empty()

        uploaded_count = 0
        skipped_count = 0

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:

            for idx, row in df.iterrows():
                progress.progress((idx + 1) / len(df))
                product = str(row[product_col]).strip()
                url = str(row[url_col]).strip()

                status.info(f"Processing row {idx + 1}: {product}")
                log_user(f"🔄 Row {idx + 1}: {product}")

                if not url.startswith("http"):
                    skipped_count += 1
                    log_user("❌ Invalid URL → skipped")
                    log_admin(f"SKIP row={idx+1} invalid_url")
                    continue

                try:
                    r = requests.get(url, headers=HEADERS, timeout=25)
                    r.raise_for_status()
                    log_user("✅ HTTP 200")

                    img = Image.open(BytesIO(r.content))
                    if img.mode == "RGBA":
                        img = img.convert("RGB")

                    img_bytes = BytesIO()
                    img.save(img_bytes, "JPEG", quality=90)
                    img_bytes.seek(0)

                    filename = sanitize_filename(product) + ".jpg"
                    s3_key = folder_prefix + filename

                    s3.upload_fileobj(
                        img_bytes,
                        S3_BUCKET,
                        s3_key,
                        ExtraArgs={"ContentType": "image/jpeg"},
                    )

                    public_url = PUBLIC_BASE_URL + run_id + "/" + filename
                    server_urls[idx] = public_url

                    zipf.writestr(filename, img_bytes.getvalue())

                    uploaded_count += 1
                    log_user(f"✅ Uploaded → {public_url}")
                    log_admin(f"UPLOAD row={idx+1} {public_url}")

                except Exception as e:
                    skipped_count += 1
                    log_user(f"❌ FAILED → {e}")
                    log_admin(f"ERROR row={idx+1} {e}")

        df["Server Image URL"] = server_urls

        log_admin(f"END run_id={run_id} uploaded={uploaded_count} skipped={skipped_count}")

        st.success(f"🎉 Uploaded: {uploaded_count} | Skipped: {skipped_count}")

        st.download_button(
            "⬇️ Download Images ZIP",
            data=zip_buffer.getvalue(),
            file_name=f"images_{run_id}.zip",
            mime="application/zip",
        )

        st.download_button(
            "⬇️ Download Updated CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=f"updated_{run_id}.csv",
            mime="text/csv",
        )
