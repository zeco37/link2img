import streamlit as st
import pandas as pd
import boto3
import requests
from PIL import Image
from io import BytesIO
import zipfile
import re

# ─────────────────────────────────────────────
# STREAMLIT CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Image → ZIP + Company Server",
    page_icon="📦",
    layout="wide",
)

st.title("📦 Image Downloader → Company Server")

# ─────────────────────────────────────────────
# LOAD SECRETS
# ─────────────────────────────────────────────
AWS_REGION = "eu-west-3"

AWS_ACCESS_KEY = st.secrets["AWS_ACCESS_KEY_ID"]
AWS_SECRET_KEY = st.secrets["AWS_SECRET_ACCESS_KEY"]
S3_BUCKET = st.secrets["S3_BUCKET"]

S3_PREFIX = "streamlit/"
PUBLIC_BASE_URL = "https://static.ora.ma/streamlit/"

# ─────────────────────────────────────────────
# S3 CLIENT
# ─────────────────────────────────────────────
s3 = boto3.client(
    "s3",
    region_name=AWS_REGION,
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
    "Accept": "image/*,*/*;q=0.8",
    "Referer": "https://glovoapp.com/",
}

# ─────────────────────────────────────────────
# FILE UPLOAD
# ─────────────────────────────────────────────
uploaded = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx"])

if uploaded:
    df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)

    product_col = st.selectbox("Product column", df.columns)
    url_col = st.selectbox("Image URL column", df.columns)

    show_logs = st.checkbox("🧾 Show logs", value=False)

    if st.button("🚀 Process Images"):
        zip_buffer = BytesIO()
        server_urls = [None] * len(df)

        uploaded_count = 0
        skipped_count = 0

        log_box = st.expander("📋 Logs", expanded=show_logs)

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:

            for idx, row in df.iterrows():

                product = str(row[product_col]).strip()
                url = str(row[url_col]).strip()

                if not url.startswith("http"):
                    skipped_count += 1
                    continue

                filename = sanitize_filename(product) + ".jpg"
                s3_key = S3_PREFIX + filename

                try:
                    with log_box:
                        st.write(f"🔎 Row {idx+1}: {product}")
                        st.write(f"⬇ Downloading…")

                    # DOWNLOAD IMAGE
                    r = requests.get(url, headers=HEADERS, timeout=20)
                    r.raise_for_status()

                    img = Image.open(BytesIO(r.content))
                    if img.mode != "RGB":
                        img = img.convert("RGB")

                    # 🔥 IMPORTANT FIX
                    # Convert ONCE → raw bytes
                    img_raw = BytesIO()
                    img.save(img_raw, "JPEG", quality=90)
                    img_bytes = img_raw.getvalue()

                    # UPLOAD (new stream)
                    s3.upload_fileobj(
                        BytesIO(img_bytes),
                        S3_BUCKET,
                        s3_key,
                        ExtraArgs={"ContentType": "image/jpeg"},
                    )

                    public_url = PUBLIC_BASE_URL + filename
                    server_urls[idx] = public_url

                    # ZIP (separate stream)
                    zipf.writestr(filename, img_bytes)

                    uploaded_count += 1

                    with log_box:
                        st.success(f"✅ Uploaded → {public_url}")

                except Exception as e:
                    skipped_count += 1
                    with log_box:
                        st.error(f"❌ Error: {e}")

        df["Server Image URL"] = server_urls

        st.success(f"🎉 Uploaded: {uploaded_count} | Skipped: {skipped_count}")

        st.download_button(
            "⬇ Download Images ZIP",
            zip_buffer.getvalue(),
            "images.zip",
            "application/zip",
        )

        st.download_button(
            "⬇ Download Updated CSV",
            df.to_csv(index=False).encode(),
            "updated_with_server_links.csv",
            "text/csv",
        )
