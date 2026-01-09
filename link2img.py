import streamlit as st
import pandas as pd
import boto3
import requests
from PIL import Image
from io import BytesIO
import zipfile
import re

# ─────────────────────────────────────────────
# Streamlit Config
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Image → ZIP + Server",
    page_icon="📦",
    layout="centered",
)

st.title("📦 Image Downloader → Company Server")

# ─────────────────────────────────────────────
# S3 CONFIG (FROM SECRETS)
# ─────────────────────────────────────────────
try:
    AWS_ACCESS_KEY = st.secrets["AWS_ACCESS_KEY_ID"]
    AWS_SECRET_KEY = st.secrets["AWS_SECRET_ACCESS_KEY"]
    S3_BUCKET = st.secrets["S3_BUCKET"]

    # Fixed values
    S3_PREFIX = "streamlit/"
    PUBLIC_BASE_URL = "https://static.ora.ma/streamlit/"
    AWS_REGION = "eu-west-3"  # ✅ REQUIRED

except Exception:
    st.error("❌ Missing AWS / S3 secrets in Streamlit")
    st.stop()

# ─────────────────────────────────────────────
# S3 CLIENT (REGION ADDED)
# ─────────────────────────────────────────────
s3 = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION,  # ✅ FIX
)

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def sanitize_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", name).strip() or "image"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://glovoapp.com/",
}

# ─────────────────────────────────────────────
# FILE UPLOAD
# ─────────────────────────────────────────────
uploaded = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx"])

if uploaded:
    if uploaded.name.lower().endswith(".csv"):
        df = pd.read_csv(uploaded)
    else:
        df = pd.read_excel(uploaded)

    st.subheader("📌 Columns detected")
    st.json(list(df.columns))

    product_col = st.selectbox("Select product column", df.columns)
    url_col = st.selectbox("Select image URL column", df.columns)

    if st.button("🚀 Process Images"):
        zip_buffer = BytesIO()
        server_urls = [None] * len(df)

        uploaded_count = 0
        skipped_count = 0

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
                    # DOWNLOAD IMAGE (BROWSER MODE)
                    r = requests.get(url, headers=BROWSER_HEADERS, timeout=25)
                    r.raise_for_status()

                    img = Image.open(BytesIO(r.content))
                    if img.mode == "RGBA":
                        img = img.convert("RGB")

                    # SAVE JPG IN MEMORY
                    img_bytes = BytesIO()
                    img.save(img_bytes, "JPEG", quality=90)
                    img_bytes.seek(0)

                    # UPLOAD TO S3
                    s3.upload_fileobj(
                        img_bytes,
                        S3_BUCKET,
                        s3_key,
                        ExtraArgs={
                            "ContentType": "image/jpeg",
                            "ACL": "public-read",
                        },
                    )

                    public_url = PUBLIC_BASE_URL + filename
                    server_urls[idx] = public_url

                    # ADD TO ZIP
                    zipf.writestr(filename, img_bytes.getvalue())

                    uploaded_count += 1

                except Exception:
                    skipped_count += 1
                    server_urls[idx] = None

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
