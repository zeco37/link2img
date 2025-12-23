import streamlit as st
import pandas as pd
import cloudinary
import cloudinary.uploader
from cloudinary import CloudinaryImage
from PIL import Image
import requests
from io import BytesIO
import zipfile
import re

# ─────────────────────────────────────────────
# Cloudinary config (from Streamlit secrets)
# ─────────────────────────────────────────────
try:
    cloudinary.config(
        cloud_name=st.secrets["CLOUDINARY_CLOUD_NAME"],
        api_key=st.secrets["CLOUDINARY_API_KEY"],
        api_secret=st.secrets["CLOUDINARY_API_SECRET"],
        secure=True,
    )
except Exception:
    st.error("❌ Cloudinary secrets not found. Please configure secrets.toml")
    st.stop()

st.set_page_config(page_title="Link → Image ZIP", page_icon="📦", layout="centered")
st.title("📦 Image Downloader → ZIP + Cloudinary")

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def sanitize_filename(name: str) -> str:
    return re.sub(r'[^A-Za-z0-9_\- ]', '_', name).strip() or "image"

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

    product_col = st.selectbox("Select product column", df.columns)
    url_col = st.selectbox("Select image URL column", df.columns)

    if st.button("🚀 Process Images"):

        zip_buffer = BytesIO()

        # IMPORTANT: pre-size list to avoid ValueError
        cloud_urls = [None] * len(df)
        success_count = 0

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:

            # ─────────────────────────────────────────────
            # ✅ CORRECTED LOOP (INDEX-BASED – SAFE)
            # ─────────────────────────────────────────────
            for idx, row in df.iterrows():
                product = str(row[product_col]).strip()
                url = str(row[url_col]).strip()

                if not url.startswith("http"):
                    cloud_urls[idx] = None
                    continue

                try:
                    # Download image
                    r = requests.get(url, timeout=20)
                    r.raise_for_status()

                    img = Image.open(BytesIO(r.content))
                    if img.mode == "RGBA":
                        img = img.convert("RGB")

                    filename = sanitize_filename(product)

                    # Upload to Cloudinary (FORCE JPG)
                    upload_res = cloudinary.uploader.upload(
                        BytesIO(r.content),
                        folder="Products",
                        public_id=filename,
                        overwrite=True,
                        resource_type="image",
                        format="jpg",
                        use_filename=True,
                        unique_filename=False,
                    )

                    # Build DOWNLOAD-ALLOWED URL
                    cloud_url = CloudinaryImage(upload_res["public_id"]).build_url(
                        secure=True,
                        format="jpg",
                        flags="attachment",
                    )

                    cloud_urls[idx] = cloud_url

                    # Add image to ZIP
                    img_bytes = BytesIO()
                    img.save(img_bytes, "JPEG", quality=90)
                    img_bytes.seek(0)

                    zipf.writestr(filename + ".jpg", img_bytes.getvalue())
                    success_count += 1

                except Exception:
                    cloud_urls[idx] = None

        # ─────────────────────────────────────────────
        # Save results
        # ─────────────────────────────────────────────
        df["Cloudinary URL"] = cloud_urls

        st.success(f"🎉 Done! {success_count} images processed.")

        st.download_button(
            "⬇️ Download Images ZIP",
            data=zip_buffer.getvalue(),
            file_name="images.zip",
            mime="application/zip",
        )

        st.download_button(
            "⬇️ Download Updated CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="updated_with_cloudinary.csv",
            mime="text/csv",
        )
