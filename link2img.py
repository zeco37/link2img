import streamlit as st
import pandas as pd
import boto3
import requests
from PIL import Image
from io import BytesIO
import zipfile
import re
import traceback

# ─────────────────────────────────────────────
# Streamlit Config
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Image → ZIP + Server (DEBUG)",
    page_icon="🪵",
    layout="centered",
)

st.title("🪵 Image Downloader → Company Server (DEBUG MODE)")

# ─────────────────────────────────────────────
# S3 CONFIG (FROM SECRETS)
# ─────────────────────────────────────────────
st.write("🔐 Loading secrets...")

try:
    AWS_ACCESS_KEY = st.secrets["AWS_ACCESS_KEY_ID"]
    AWS_SECRET_KEY = st.secrets["AWS_SECRET_ACCESS_KEY"]
    S3_BUCKET = st.secrets["S3_BUCKET"]

    S3_PREFIX = "streamlit/"
    PUBLIC_BASE_URL = "https://static.ora.ma/streamlit/"
    AWS_REGION = "eu-west-3"

    st.success("✅ Secrets loaded successfully")

except Exception as e:
    st.error("❌ Missing AWS / S3 secrets")
    st.exception(e)
    st.stop()

# ─────────────────────────────────────────────
# S3 CLIENT
# ─────────────────────────────────────────────
st.write("🔌 Creating S3 client...")

try:
    s3 = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=AWS_REGION,
    )
    st.success("✅ S3 client created")

except Exception as e:
    st.error("❌ Failed to create S3 client")
    st.exception(e)
    st.stop()

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

st.write("🌐 Browser headers:", BROWSER_HEADERS)

# ─────────────────────────────────────────────
# FILE UPLOAD
# ─────────────────────────────────────────────
uploaded = st.file_uploader("📤 Upload CSV or XLSX", type=["csv", "xlsx"])

if uploaded:
    st.write("📄 File uploaded:", uploaded.name)

    try:
        if uploaded.name.lower().endswith(".csv"):
            df = pd.read_csv(uploaded)
        else:
            df = pd.read_excel(uploaded)

        st.success("✅ File loaded into DataFrame")

    except Exception as e:
        st.error("❌ Failed to read file")
        st.exception(e)
        st.stop()

    st.subheader("📌 Columns detected")
    st.write(df.columns.tolist())

    product_col = st.selectbox("Select product column", df.columns)
    url_col = st.selectbox("Select image URL column", df.columns)

    if st.button("🚀 Process Images (DEBUG)"):

        st.write("▶️ Starting processing...")
        zip_buffer = BytesIO()
        server_urls = [None] * len(df)

        uploaded_count = 0
        skipped_count = 0

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:

            for idx, row in df.iterrows():
                st.write(f"────────────────────────")
                st.write(f"🔎 ROW {idx}")

                try:
                    product = str(row[product_col]).strip()
                    url = str(row[url_col]).strip()

                    st.write("📝 Product:", product)
                    st.write("🔗 URL:", url)

                    if not url.startswith("http"):
                        st.warning("⚠️ Invalid URL → skipped")
                        skipped_count += 1
                        continue

                    filename = sanitize_filename(product) + ".jpg"
                    s3_key = S3_PREFIX + filename

                    st.write("🧾 Filename:", filename)
                    st.write("📂 S3 Key:", s3_key)

                    # ───── DOWNLOAD IMAGE ─────
                    st.write("⬇️ Downloading image...")
                    r = requests.get(url, headers=BROWSER_HEADERS, timeout=25)

                    st.write("🌐 HTTP status:", r.status_code)
                    st.write("📦 Content-Type:", r.headers.get("Content-Type"))

                    r.raise_for_status()

                    img = Image.open(BytesIO(r.content))
                    st.write("🖼 Image format:", img.format, "| mode:", img.mode)

                    if img.mode == "RGBA":
                        img = img.convert("RGB")
                        st.write("🎨 Converted RGBA → RGB")

                    # ───── SAVE JPG ─────
                    img_bytes = BytesIO()
                    img.save(img_bytes, "JPEG", quality=90)
                    img_bytes.seek(0)

                    st.write("💾 Image converted to JPG in memory")

                    # ───── UPLOAD TO S3 ─────
                    st.write("☁️ Uploading to S3...")

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

                    st.success(f"✅ Uploaded to: {public_url}")

                    # ───── ADD TO ZIP ─────
                    zipf.writestr(filename, img_bytes.getvalue())
                    st.write("📦 Added to ZIP")

                    uploaded_count += 1

                except Exception as e:
                    skipped_count += 1
                    server_urls[idx] = None

                    st.error("❌ ERROR on this row")
                    st.text(traceback.format_exc())

        df["Server Image URL"] = server_urls

        st.success(f"🎉 DONE | Uploaded: {uploaded_count} | Skipped: {skipped_count}")

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
