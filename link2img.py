import streamlit as st
import pandas as pd
import boto3
from botocore.exceptions import ClientError
from PIL import Image
import requests
from io import BytesIO
import zipfile
import re
import os

# ─────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────
st.set_page_config(page_title="Link → Image ZIP (S3)", page_icon="📦", layout="centered")
st.title("📦 Image Downloader → ZIP + Company S3")

# ─────────────────────────────────────────────
# Load secrets
# ─────────────────────────────────────────────
try:
    AWS_ACCESS_KEY_ID = st.secrets["AWS_ACCESS_KEY_ID"]
    AWS_SECRET_ACCESS_KEY = st.secrets["AWS_SECRET_ACCESS_KEY"]
    AWS_REGION = st.secrets.get("AWS_REGION", "eu-west-1")
    S3_BUCKET = st.secrets["S3_BUCKET"]
    S3_PREFIX = st.secrets.get("S3_PREFIX", "streamlit")
    PUBLIC_BASE_URL = st.secrets["PUBLIC_BASE_URL"]
except Exception:
    st.error("❌ Missing AWS S3 secrets. Check `.streamlit/secrets.toml`.")
    st.stop()

# ─────────────────────────────────────────────
# S3 client
# ─────────────────────────────────────────────
s3 = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
)

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def sanitize_filename(name: str) -> str:
    return re.sub(r'[^A-Za-z0-9_\-]', '_', name).strip() or "image"

def upload_to_s3(file_bytes: bytes, filename: str) -> str:
    key = f"{S3_PREFIX}/{filename}"
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=file_bytes,
        ContentType="image/jpeg",
        ACL="public-read"
    )
    return f"{PUBLIC_BASE_URL}/{filename}"

# ─────────────────────────────────────────────
# Upload CSV / XLSX
# ─────────────────────────────────────────────
uploaded = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx"])

if uploaded:
    df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)

    st.subheader("📌 Columns detected")
    st.json(list(df.columns))

    product_col = st.selectbox("Select product column", df.columns)
    url_col = st.selectbox("Select image URL column", df.columns)

    if st.button("🚀 Process Images"):
        zip_buffer = BytesIO()
        server_urls = [None] * len(df)
        success = 0

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for idx, row in df.iterrows():
                product = str(row[product_col]).strip()
                url = str(row[url_col]).strip()

                if not url.startswith("http"):
                    continue

                try:
                    r = requests.get(url, timeout=20)
                    r.raise_for_status()

                    img = Image.open(BytesIO(r.content))
                    if img.mode == "RGBA":
                        img = img.convert("RGB")

                    filename = sanitize_filename(product) + ".jpg"

                    img_bytes = BytesIO()
                    img.save(img_bytes, "JPEG", quality=90)
                    img_bytes.seek(0)

                    public_url = upload_to_s3(img_bytes.getvalue(), filename)
                    server_urls[idx] = public_url

                    zipf.writestr(filename, img_bytes.getvalue())
                    success += 1

                except Exception as e:
                    server_urls[idx] = None

        df["Image URL (Server)"] = server_urls

        st.success(f"🎉 Done! {success} images uploaded to company server.")

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
