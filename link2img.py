import streamlit as st
import pandas as pd
import cloudinary
import cloudinary.uploader
from PIL import Image
import requests
from io import BytesIO
import zipfile
import re

# ========= Cloudinary Config =========
try:
    cloudinary.config(
        cloud_name=st.secrets["CLOUDINARY_CLOUD_NAME"],
        api_key=st.secrets["CLOUDINARY_API_KEY"],
        api_secret=st.secrets["CLOUDINARY_API_SECRET"]
    )
except Exception:
    st.error("❌ Cloudinary secrets not found. Please configure secrets.toml")
    st.stop()


st.set_page_config(page_title="Image Downloader", page_icon="📥", layout="centered")
st.title("📥 Link Converter")


# ========= Filename Sanitizer =========
def sanitize_filename(name: str):
    return re.sub(r'[^A-Za-z0-9_\- ]', '_', name).strip()


# ========= File Upload =========
uploaded = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx"])

if uploaded:

    # Load file
    if uploaded.name.endswith(".csv"):
        df = pd.read_csv(uploaded)
    else:
        df = pd.read_excel(uploaded)

    st.subheader("📌 Columns detected:")
    st.json(list(df.columns))

    product_col = st.selectbox("Select product column", df.columns)
    url_col = st.selectbox("Select image URL column", df.columns)

    if st.button("🚀 Process Images"):

        zip_buffer = BytesIO()
        cloud_urls = []
        count = 0

        with zipfile.ZipFile(zip_buffer, "w") as zipf:

            for idx, row in df.iterrows():
                product = str(row[product_col]).strip()
                url = str(row[url_col]).strip()

                if not url.startswith("http"):
                    cloud_urls.append(None)
                    continue

                try:
                    r = requests.get(url, timeout=20)
                    img = Image.open(BytesIO(r.content))

                    if img.mode == "RGBA":
                        img = img.convert("RGB")

                    filename = sanitize_filename(product)

                    # ===== Upload to Cloudinary =====
                    upload_res = cloudinary.uploader.upload(
                        BytesIO(r.content),
                        folder="streamlit_import",
                        public_id=filename,
                        overwrite=True
                    )

                    c_url = upload_res.get("secure_url")
                    cloud_urls.append(c_url)

                    # ===== Add image to ZIP =====
                    img_bytes = BytesIO()
                    img.save(img_bytes, "JPEG", quality=90)
                    img_bytes.seek(0)

                    zipf.writestr(filename + ".jpg", img_bytes.getvalue())
                    count += 1

                except:
                    cloud_urls.append(None)

        # ========= Update CSV =========
        df["Cloudinary URL"] = cloud_urls

        st.success(f"🎉 Done! {count} images processed.")

        # Download CSV
        st.download_button(
            "⬇️ Download Updated CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="updated.csv",
            mime="text/csv"
        )

        # Download ZIP
        st.download_button(
            "⬇️ Download Images ZIP",
            data=zip_buffer.getvalue(),
            file_name="images.zip",
            mime="application/zip"
        )

