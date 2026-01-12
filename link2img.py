import streamlit as st
import pandas as pd
import boto3
import requests
from PIL import Image
from io import BytesIO
import zipfile
import re

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Image → ZIP + Server",
    page_icon="📦",
    layout="wide",
)

# ─────────────────────────────────────────────
# STYLE (UI POLISH)
# ─────────────────────────────────────────────
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2.5rem;
        max-width: 1200px;
    }
    .stButton>button {
        border-radius: 10px;
        padding: 0.6rem 1.4rem;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
st.markdown("## 📦 Image Processing Tool")
st.caption("Upload images from URLs → host on company server → export ZIP & CSV")
st.divider()

# ─────────────────────────────────────────────
# LOG TOGGLE
# ─────────────────────────────────────────────
show_logs = st.toggle("📋 Show logs", value=False)
log_box = st.container() if show_logs else None

def log(msg):
    if log_box:
        log_box.write(msg)

# ─────────────────────────────────────────────
# S3 CONFIG (EU-WEST-3)
# ─────────────────────────────────────────────
try:
    AWS_ACCESS_KEY = st.secrets["AWS_ACCESS_KEY_ID"]
    AWS_SECRET_KEY = st.secrets["AWS_SECRET_ACCESS_KEY"]
    S3_BUCKET = st.secrets["S3_BUCKET"]
except Exception:
    st.error("❌ AWS credentials missing in secrets.toml")
    st.stop()

S3_PREFIX = "streamlit/"
PUBLIC_BASE_URL = "https://static.ora.ma/streamlit/"

s3 = boto3.client(
    "s3",
    region_name="eu-west-3",
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
)

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def sanitize_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", name).strip() or "image"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://glovoapp.com/",
}

# ─────────────────────────────────────────────
# FILE UPLOAD
# ─────────────────────────────────────────────
col1, col2 = st.columns([2, 1])

with col1:
    uploaded = st.file_uploader("📄 Upload CSV or XLSX", type=["csv", "xlsx"])

with col2:
    st.info("✔ Bulk image processing\n✔ Secure server hosting\n✔ ZIP + CSV export")

if not uploaded:
    st.info("⬆ Upload a file to get started.")
    st.stop()

# ─────────────────────────────────────────────
# LOAD FILE
# ─────────────────────────────────────────────
df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)

st.subheader("📌 Columns detected")
st.json(list(df.columns))

product_col = st.selectbox("Product name column", df.columns)
url_col = st.selectbox("Image URL column", df.columns)

# ─────────────────────────────────────────────
# PROCESS BUTTON
# ─────────────────────────────────────────────
if st.button("🚀 Process Images", type="primary"):

    zip_buffer = BytesIO()
    server_urls = [None] * len(df)

    uploaded_count = 0
    skipped_count = 0

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:

        for idx, row in df.iterrows():
            product = str(row[product_col]).strip()
            url = str(row[url_col]).strip()

            log(f"🔹 Row {idx+1}: {product}")

            if not url.startswith("http"):
                log("⛔ Invalid URL")
                skipped_count += 1
                continue

            filename = sanitize_filename(product) + ".jpg"
            s3_key = S3_PREFIX + filename

            try:
                log("⬇ Downloading image...")
                r = requests.get(url, headers=HEADERS, timeout=25)
                r.raise_for_status()

                img = Image.open(BytesIO(r.content))
                if img.mode != "RGB":
                    img = img.convert("RGB")

                img_bytes = BytesIO()
                img.save(img_bytes, "JPEG", quality=90)
                img_bytes.seek(0)

                log("☁ Uploading to S3...")
                s3.upload_fileobj(
                    img_bytes,
                    S3_BUCKET,
                    s3_key,
                    ExtraArgs={"ContentType": "image/jpeg"},
                )

                server_url = PUBLIC_BASE_URL + filename
                server_urls[idx] = server_url

                # ZIP requires fresh buffer
                zipf.writestr(filename, img_bytes.getvalue())

                uploaded_count += 1
                log(f"✅ Uploaded → {server_url}")

            except Exception as e:
                skipped_count += 1
                log(f"❌ Error: {e}")

    # ─────────────────────────────────────────────
    # SAVE RESULTS
    # ─────────────────────────────────────────────
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
