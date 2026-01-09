import streamlit as st
import pandas as pd
import requests
import boto3
from PIL import Image
from io import BytesIO
import zipfile
import re

# ─────────────────────────────────────────────
# AWS S3 CONFIG
# ─────────────────────────────────────────────
try:
    s3 = boto3.client(
        "s3",
        aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
        region_name=st.secrets["AWS_REGION"],
    )
    BUCKET = st.secrets["AWS_BUCKET_NAME"]
except Exception as e:
    st.error("❌ AWS secrets not configured correctly")
    st.stop()

BASE_URL = "https://static.ora.ma/streamlit/"

# ─────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────
st.set_page_config(page_title="Link → Image ZIP (S3)", page_icon="📦")
st.title("📦 Image Downloader → ZIP + Company Server")

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def sanitize_filename(name: str) -> str:
    name = str(name)
    name = re.sub(r"[^A-Za-z0-9_\- ]", "_", name)
    return name.strip().replace(" ", "_") or "image"

# ─────────────────────────────────────────────
# Upload file
# ─────────────────────────────────────────────
uploaded = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx"])

if uploaded:
    if uploaded.name.lower().endswith(".csv"):
        df = pd.read_csv(uploaded)
    else:
        df = pd.read_excel(uploaded)

    st.subheader("📌 Columns detected")
    st.json(list(df.columns))

    product_col = st.selectbox("Select product name column", df.columns)
    url_col = st.selectbox("Select image URL column", df.columns)

    if st.button("🚀 Process Images"):

        zip_buffer = BytesIO()
        image_urls = [None] * len(df)

        uploaded_count = 0
        skipped_count = 0

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:

            for idx, row in df.iterrows():

                # ─── Validate URL ─────────────────────
                if pd.isna(row[url_col]):
                    skipped_count += 1
                    continue

                url = str(row[url_col]).strip()
                if not url.lower().startswith(("http://", "https://")):
                    skipped_count += 1
                    continue

                filename = sanitize_filename(row[product_col]) + ".jpg"
                s3_key = f"streamlit/{filename}"

                try:
                    # Download image
                    r = requests.get(url, timeout=20)
                    r.raise_for_status()

                    img = Image.open(BytesIO(r.content))
                    if img.mode == "RGBA":
                        img = img.convert("RGB")

                    # Convert to JPG
                    img_bytes = BytesIO()
                    img.save(img_bytes, "JPEG", quality=90)
                    img_bytes.seek(0)

                    # Upload to S3
                    s3.upload_fileobj(
                        img_bytes,
                        BUCKET,
                        s3_key,
                        ExtraArgs={
                            "ContentType": "image/jpeg",
                            "ACL": "public-read",
                        },
                    )

                    public_url = BASE_URL + filename
                    image_urls[idx] = public_url

                    # Add to ZIP
                    zipf.writestr(filename, img_bytes.getvalue())

                    uploaded_count += 1

                except Exception as e:
                    skipped_count += 1
                    image_urls[idx] = None

        # ─────────────────────────────────────────────
        # Save results
        # ─────────────────────────────────────────────
        df["Image URL (Server)"] = image_urls

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
