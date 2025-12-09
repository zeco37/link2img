import streamlit as st
import pandas as pd
import requests
from PIL import Image
from io import BytesIO
import zipfile
import os
import re

st.title("Image Downloader from CSV/XLSX")

uploaded_file = st.file_uploader("Upload .xlsx or .csv")

def sanitize_filename(name: str) -> str:
    """Remove invalid characters from filenames"""
    name = re.sub(r'[^a-zA-Z0-9_\- ]', '_', name)
    return name.strip()

if uploaded_file:

    # Load DataFrame
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    st.write("👇 Columns detected:")
    st.json(list(df.columns))

    product_col = st.selectbox("Select product column", df.columns)
    url_col = st.selectbox("Select image URL column", df.columns)

    if st.button("Download Images and ZIP"):
        zip_buffer = BytesIO()
        downloaded_count = 0

        with zipfile.ZipFile(zip_buffer, "w") as zipf:
            for idx, row in df.iterrows():
                product = str(row[product_col])
                url = str(row[url_col])

                if pd.isna(url) or not url.startswith("http"):
                    continue

                try:
                    response = requests.get(url, timeout=15)
                    if response.status_code == 200:

                        img = Image.open(BytesIO(response.content))

                        # Convert transparent → RGB
                        if img.mode == "RGBA":
                            img = img.convert("RGB")

                        filename = sanitize_filename(product) + ".jpg"

                        img_bytes = BytesIO()
                        img.save(img_bytes, "JPEG", quality=95)
                        img_bytes.seek(0)

                        zipf.writestr(filename, img_bytes.getvalue())
                        downloaded_count += 1

                except:
                    pass

        st.success(f"🎉 Done! {downloaded_count} images downloaded.")

        st.download_button(
            "⬇️ Download ZIP",
            data=zip_buffer.getvalue(),
            file_name="images.zip",
            mime="application/zip"
        )
