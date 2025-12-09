import streamlit as st
import pandas as pd
import requests
import zipfile
import io
from PIL import Image
from pathlib import Path
import openpyxl

st.set_page_config(page_title="Download Images Tool", page_icon="📥", layout="centered")

st.title("📥 Download Images From CSV / XLSX")
st.caption("Upload a CSV or XLSX file containing product names and image URLs. The tool downloads all images and generates a ZIP file.")


# ============================
# Extract hyperlinks from XLSX
# ============================
def extract_urls_xlsx_real(file_data, sheet_name):
    wb = openpyxl.load_workbook(file_data, data_only=True)
    ws = wb[sheet_name]

    urls = []
    for row in ws.iter_rows(min_row=2):
        cell = row[1]  # URL column (second column)
        if cell.hyperlink:
            urls.append(cell.hyperlink.target)
        else:
            urls.append(str(cell.value))
    return urls


# ============================
# FILE UPLOAD
# ============================
uploaded = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx"])

if uploaded:
    ext = Path(uploaded.name).suffix.lower()

    # Load file
    if ext == ".csv":
        df = pd.read_csv(uploaded)
        sheet_name = None
    else:
        xls = pd.ExcelFile(uploaded)
        sheet_name = st.selectbox("Select sheet", xls.sheet_names)
        df = pd.read_excel(xls, sheet_name=sheet_name)

    st.subheader("📌 Columns detected:")
    st.json(list(df.columns))

    # Column selection
    product_col = st.selectbox("Select product column", df.columns)
    url_col = st.selectbox("Select image URL column", df.columns)

    # Fix protected XLSX hyperlinks
    if ext == ".xlsx":
        real_urls = extract_urls_xlsx_real(uploaded, sheet_name)
        df[url_col] = real_urls

    # ============================
    # DOWNLOAD IMAGES
    # ============================
    if st.button("⬇️ Download Images & Generate ZIP"):

        zip_buffer = io.BytesIO()
        zipf = zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED)

        count = 0
        progress = st.progress(0)

        for i, row in df.iterrows():
            name = str(row[product_col]).strip()
            url = str(row[url_col]).strip()

            if not url.startswith("http"):
                continue

            try:
                resp = requests.get(url, timeout=20)
                if resp.ok:
                    img = Image.open(io.BytesIO(resp.content))

                    if img.mode == "RGBA":
                        img = img.convert("RGB")

                    # filename safe
                    fname = (
                        name.replace("/", "_")
                        .replace("\\", "_")
                        .replace(":", "_")
                        .replace("*", "_")
                        .replace("?", "_")
                    ) + ".jpg"

                    img_buf = io.BytesIO()
                    img.save(img_buf, format="JPEG", quality=95)
                    img_buf.seek(0)

                    zipf.writestr(fname, img_buf.getvalue())
                    count += 1

                progress.progress((i + 1) / len(df))

            except Exception:
                pass

        zipf.close()

        st.success(f"🎉 Done! {count} images downloaded!")

        st.download_button(
            "⬇️ Download ZIP",
            data=zip_buffer.getvalue(),
            file_name="images.zip",
            mime="application/zip",
        )
