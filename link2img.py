import streamlit as st
import pandas as pd
import requests
import zipfile
import io
from PIL import Image
import os

st.title("Download Images from CSV/XLSX")

uploaded_file = st.file_uploader("Upload .xlsx or .csv")

if uploaded_file:
    # Load df
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    st.write("📌 Columns detected:")
    st.json(list(df.columns))

    product_col = st.selectbox("Select product column", df.columns)
    url_col = st.selectbox("Select image URL column", df.columns)

    if st.button("Download Images & Generate ZIP"):

        # where ZIP will be stored
        zip_buffer = io.BytesIO()

        downloaded_urls = []
        count = 0

        with zipfile.ZipFile(zip_buffer, "w") as zipf:
            for i, row in df.iterrows():
                product = str(row[product_col]).strip()
                url = str(row[url_col]).strip()

                if pd.isna(url) or url == "":
                    downloaded_urls.append(None)
                    continue

                try:
                    response = requests.get(url, timeout=10)
                    if response.status_code == 200:
                        img = Image.open(io.BytesIO(response.content))
                        img_bytes = io.BytesIO()
                        img.save(img_bytes, format="PNG")
                        img_bytes.seek(0)

                        file_name = f"{product}.png"
                        zipf.writestr(file_name, img_bytes.getvalue())
                        downloaded_urls.append(url)
                        count += 1
                    else:
                        downloaded_urls.append(None)

                except:
                    downloaded_urls.append(None)

        # ALIGN COLUMN LENGTHS
        if len(downloaded_urls) < len(df):
            downloaded_urls += [None] * (len(df) - len(downloaded_urls))
        else:
            downloaded_urls = downloaded_urls[:len(df)]

        # ADD NEW COLUMN (DO NOT OVERWRITE)
        df["Downloaded URL"] = downloaded_urls

        # Download updated table
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)

        st.success(f"🎉 Done! {count} images downloaded.")
        st.download_button(
            "📥 Download ZIP",
            data=zip_buffer.getvalue(),
            file_name="images.zip",
            mime="application/zip"
        )

        st.download_button(
            "📄 Download updated CSV",
            data=csv_buffer.getvalue(),
            file_name="updated.csv",
            mime="text/csv"
        )
