import streamlit as st
import pandas as pd
import cloudinary
import cloudinary.uploader
from PIL import Image
import requests
from io import BytesIO
import zipfile
import os
import re

# === Cloudinary Config ===
cloudinary.config(
    cloud_name=st.secrets["dqye9uju0"],
    api_key=st.secrets["786456455339284"],
    api_secret=st.secrets["wHsLn_TPTtUR1dZezXbEaFWXy3g"]
)

st.title("CSV Image Downloader + Cloudinary Uploader")

uploaded_file = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx"])

def sanitize_filename(name):
    name = re.sub(r'[^a-zA-Z0-9_\- ]', "_", name)
    return name.strip()    

if uploaded_file:
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    st.json(list(df.columns))

    product_col = st.selectbox("Select product column", df.columns)
    url_col = st.selectbox("Select image URL column", df.columns)

    if st.button("Start Process"):
        st.info("Downloading images and uploading to Cloudinary...")

        zip_buffer = BytesIO()
        cloud_urls = []
        downloaded = 0

        with zipfile.ZipFile(zip_buffer, "w") as zipf:
            for idx, row in df.iterrows():
                product = str(row[product_col])
                url = str(row[url_col])

                if not url.startswith("http"):
                    cloud_urls.append(None)
                    continue

                try:
                    r = requests.get(url, timeout=20)
                    img = Image.open(BytesIO(r.content))

                    if img.mode == "RGBA":
                        img = img.convert("RGB")

                    filename = sanitize_filename(product) + ".jpg"

                    # Upload to Cloudinary
                    upload_result = cloudinary.uploader.upload(
                        BytesIO(r.content),
                        folder="streamlit_import",
                        public_id=filename.replace(".jpg",""),
                        overwrite=True,
                        resource_type="image"
                    )

                    c_url = upload_result["secure_url"]
                    cloud_urls.append(c_url)

                    # Add to ZIP
                    img_bytes = BytesIO()
                    img.save(img_bytes, format="JPEG", quality=90)
                    img_bytes.seek(0)
                    zipf.writestr(filename, img_bytes.getvalue())
                    downloaded += 1

                except:
                    cloud_urls.append(None)

        st.success(f"Done! {downloaded} images processed.")

        # Add column with Cloudinary URLs
        df["Cloudinary Url"] = cloud_urls

        # Download updated table
        st.download_button(
            "⬇️ Download Updated CSV (with Cloudinary URLs)",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="updated.csv",
            mime="text/csv"
        )

        # Download ZIP of images
        st.download_button(
            "⬇️ Download ZIP of Images",
            data=zip_buffer.getvalue(),
            file_name="images.zip",
            mime="application/zip"
        )
