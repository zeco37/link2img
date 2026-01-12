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
    page_title="Image → ZIP & Server",
    page_icon="📦",
    layout="wide",
)

# ─────────────────────────────────────────────
# SIDEBAR – LOGS PANEL
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🧾 Processing Logs")
    show_logs = st.toggle("Show logs", value=False)
    log_container = st.container()

def log(message: str):
    if show_logs:
        log_container.markdown(message)

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
st.markdown("## 📦 Image Downloader → Company Server")
st.caption("Upload CSV/XLSX → host images on company server → export ZIP & CSV")
st.divider()

# ─────────────────────────────────────────────
# LOAD SECRETS (STREAMLIT CLOUD)
# ─────────────────────────────────────────────
try:
    AWS_ACCESS_KEY = st.secrets["AWS_ACCESS_KEY_ID"]
    AWS_SECRET_KEY = st.secrets["AWS_SECRET_ACCESS_KEY"]
    S3_BUCKET = st.secrets["S3_BUCKET"]
except Exception:
    st.error("❌ AWS secrets are missing in Streamlit")
    st.stop()

S3_PREFIX = "streamlit/"
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
uploaded = st.file_uploader("📄 Upload CSV or XLSX", type=["csv", "xlsx"])

if uploaded:
    df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)

    st.subheader("📌 Columns detected")
    st.json(list(df.columns))

    product_col = st.selectbox("Product name column", df.columns)
    url_col = st.selectbox("Image URL column", df.columns)

    if st.button("🚀 Process Images", type="primary"):

        zip_buffer = BytesIO()
        server_urls = [None] * len(df)

        uploaded_count = 0
        skipped_count = 0

        progress = st.progress(0)
        status = st.empty()
        total = len(df)

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:

            for i, (idx, row) in enumerate(df.iterrows()):
                progress.progress((i + 1) / total)
                status.info(f"Processing image {i + 1} / {total}")

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
                s3_key = S3_PREFIX + filename

                try:
                    # DOWNLOAD IMAGE
                    log("⬇️ Downloading image…")
                    r = requests.get(url, headers=HEADERS, timeout=25)
                    r.raise_for_status()

                    img = Image.open(BytesIO(r.content))
                    log(f"🖼️ Image mode: `{img.mode}`")

                    if img.mode != "RGB":
                        img = img.convert("RGB")

                    # CREATE JPEG BYTES ONCE
                    jpeg_bytes = BytesIO()
                    img.save(jpeg_bytes, "JPEG", quality=90)
                    jpeg_bytes.seek(0)

                    # UPLOAD TO S3 (SEPARATE BUFFER)
                    log("☁️ Uploading to server…")
                    s3_buffer = BytesIO(jpeg_bytes.getvalue())
                    s3.upload_fileobj(
                        s3_buffer,
                        S3_BUCKET,
                        s3_key,
                        ExtraArgs={"ContentType": "image/jpeg"},
                    )

                    public_url = PUBLIC_BASE_URL + filename
                    server_urls[idx] = public_url
                    uploaded_count += 1

                    log(f"✅ **Uploaded successfully**  \n🔗 {public_url}")

                    # ADD TO ZIP (SEPARATE BUFFER)
                    zipf.writestr(filename, jpeg_bytes.getvalue())

                except Exception as e:
                    skipped_count += 1
                    server_urls[idx] = None
                    log(f"❌ **Error**  \n`{e}`")

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
