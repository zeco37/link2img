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
    layout="centered",
)

st.title("📦 Image Downloader → Company Server (S3)")

# ─────────────────────────────────────────────
# LOAD SECRETS
# ─────────────────────────────────────────────
try:
    AWS_ACCESS_KEY = st.secrets["AWS_ACCESS_KEY_ID"]
    AWS_SECRET_KEY = st.secrets["AWS_SECRET_ACCESS_KEY"]
    S3_BUCKET = st.secrets["S3_BUCKET"]

    AWS_REGION = "eu-west-3"  # Paris
    S3_PREFIX = "streamlit/"
    PUBLIC_BASE_URL = "https://static.ora.ma/streamlit/"

    st.success("✅ AWS secrets loaded")

except Exception as e:
    st.error("❌ Missing AWS secrets")
    st.stop()

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

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "image/*,*/*;q=0.8",
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

                st.write("────────────────────────────")
                st.write(f"🔎 Row {idx + 1}")

                product = str(row[product_col]).strip()
                url = str(row[url_col]).strip()

                st.write(f"📦 Product: {product}")
                st.write(f"🔗 URL: {url}")

                if not url.startswith("http"):
                    st.warning("⏭ Skipped (invalid URL)")
                    skipped_count += 1
                    continue

                filename = sanitize_filename(product) + ".jpg"
                s3_key = S3_PREFIX + filename

                try:
                    # DOWNLOAD IMAGE
                    st.write("⬇ Downloading image...")
                    r = requests.get(url, headers=BROWSER_HEADERS, timeout=25)
                    r.raise_for_status()

                    st.write(f"✅ HTTP {r.status_code}")

                    img = Image.open(BytesIO(r.content))
                    st.write(f"🖼 Image mode: {img.mode}")

                    if img.mode != "RGB":
                        img = img.convert("RGB")

                    # SAVE TO MEMORY
                    img_bytes = BytesIO()
                    img.save(img_bytes, "JPEG", quality=90)
                    img_bytes.seek(0)

                    # UPLOAD TO S3 (NO ACL ❗)
                    st.write("☁ Uploading to S3...")
                    s3.upload_fileobj(
                        img_bytes,
                        S3_BUCKET,
                        s3_key,
                        ExtraArgs={
                            "ContentType": "image/jpeg",
                        },
                    )

                    public_url = PUBLIC_BASE_URL + filename
                    server_urls[idx] = public_url

                    st.success(f"✅ Uploaded → {public_url}")

                    # 🔥 IMPORTANT FIX
                    img_bytes.seek(0)

                    # ADD TO ZIP
                    zipf.writestr(filename, img_bytes.read())

                    uploaded_count += 1

                except Exception as e:
                    st.error("❌ Error on this row")
                    st.code(str(e))
                    skipped_count += 1
                    server_urls[idx] = None

        # ─────────────────────────────────────────────
        # SAVE RESULTS
        # ─────────────────────────────────────────────
        df["Server Image URL"] = server_urls

        st.success(f"🎉 Uploaded: {uploaded_count} | Skipped: {skipped_count}")

        st.download_button(
            "⬇ Download Images ZIP",
            data=zip_buffer.getvalue(),
            file_name="images.zip",
            mime="application/zip",
        )

        st.download_button(
            "⬇ Download Updated CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="updated_with_server_links.csv",
            mime="text/csv",
        )
