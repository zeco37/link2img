import streamlit as st
import pandas as pd
import boto3
import requests
from PIL import Image
from io import BytesIO
import zipfile
import re
from datetime import datetime
import uuid

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Image → ZIP + Server",
    page_icon="📦",
    layout="wide",
)

st.title("📦 Image Downloader → Company Server")

# ─────────────────────────────────────────────
# USER IDENTIFICATION (SAFE)
# ─────────────────────────────────────────────
def get_user_identity():
    try:
        return st.user.email
    except Exception:
        return "unknown@user"

USER_EMAIL = get_user_identity()
SESSION_ID = str(uuid.uuid4())[:8]
SESSION_TIME = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

st.caption(f"👤 **User:** {USER_EMAIL} | 🕒 {SESSION_TIME} | 🔑 Session `{SESSION_ID}`")

# ─────────────────────────────────────────────
# ADMIN LOG STORAGE (SESSION)
# ─────────────────────────────────────────────
if "ADMIN_LOGS" not in st.session_state:
    st.session_state.ADMIN_LOGS = []

def admin_log(event, details="", level="INFO"):
    st.session_state.ADMIN_LOGS.append({
        "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "user": USER_EMAIL,
        "session": SESSION_ID,
        "level": level,
        "event": event,
        "details": details,
    })

# ─────────────────────────────────────────────
# SIDEBAR – LOG PANEL
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🛡 Admin Panel")
    show_logs = st.toggle("Show logs")

    if show_logs:
        st.markdown("### 📜 Activity Logs")
        for log in reversed(st.session_state.ADMIN_LOGS):
            icon = {"INFO": "🟦", "ERROR": "🟥"}.get(log["level"], "⬜")
            st.markdown(
                f"""
                {icon} **{log['time']}**  
                👤 `{log['user']}`  
                🔁 **{log['event']}**  
                📝 {log['details']}
                ---
                """
            )

# ─────────────────────────────────────────────
# S3 CONFIG (FROM STREAMLIT SECRETS)
# ─────────────────────────────────────────────
try:
    AWS_ACCESS_KEY = st.secrets["AWS_ACCESS_KEY_ID"]
    AWS_SECRET_KEY = st.secrets["AWS_SECRET_ACCESS_KEY"]
    S3_BUCKET = st.secrets["S3_BUCKET"]
    AWS_REGION = "eu-west-3"
    BASE_PUBLIC_URL = "https://static.ora.ma/streamlit/"
except Exception:
    st.error("❌ Missing AWS secrets")
    st.stop()

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

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://glovoapp.com/",
}

# ─────────────────────────────────────────────
# FILE UPLOAD
# ─────────────────────────────────────────────
uploaded = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx"])

if uploaded:
    admin_log("CSV uploaded", uploaded.name)

    df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)

    st.subheader("📌 Columns detected")
    st.json(list(df.columns))

    product_col = st.selectbox("Product column", df.columns)
    url_col = st.selectbox("Image URL column", df.columns)

    if st.button("🚀 Process Images"):
        admin_log("Processing started", f"Rows: {len(df)}")

        zip_buffer = BytesIO()
        server_urls = [None] * len(df)

        uploaded_count = 0
        skipped_count = 0

        session_folder = f"streamlit/{SESSION_ID}/"
        progress = st.progress(0.0)
        status = st.empty()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for idx, row in df.iterrows():
                progress.progress((idx + 1) / len(df))
                product = str(row[product_col])
                url = str(row[url_col])

                status.info(f"Processing: {product}")

                if not url.startswith("http"):
                    skipped_count += 1
                    admin_log("Skipped row", product)
                    continue

                try:
                    # Download
                    r = requests.get(url, headers=HEADERS, timeout=20)
                    r.raise_for_status()

                    img = Image.open(BytesIO(r.content)).convert("RGB")

                    img_buffer = BytesIO()
                    img.save(img_buffer, "JPEG", quality=90)
                    img_buffer.seek(0)

                    filename = sanitize_filename(product) + ".jpg"
                    s3_key = session_folder + filename

                    # Upload to S3 (NO ACL)
                    s3.upload_fileobj(
                        img_buffer,
                        S3_BUCKET,
                        s3_key,
                        ExtraArgs={"ContentType": "image/jpeg"},
                    )

                    public_url = BASE_PUBLIC_URL + SESSION_ID + "/" + filename
                    server_urls[idx] = public_url

                    # ZIP COPY (NEW BUFFER – FIXED)
                    zipf.writestr(filename, img_buffer.getvalue())

                    uploaded_count += 1
                    admin_log("Image uploaded", public_url)

                except Exception as e:
                    skipped_count += 1
                    admin_log("Error", str(e), level="ERROR")

        df["Server Image URL"] = server_urls

        admin_log("Processing finished", f"Uploaded: {uploaded_count}, Skipped: {skipped_count}")

        st.success(f"🎉 Uploaded: {uploaded_count} | Skipped: {skipped_count}")

        st.download_button(
            "⬇️ Download Images ZIP",
            zip_buffer.getvalue(),
            file_name="images.zip",
            mime="application/zip",
        )

        st.download_button(
            "⬇️ Download Updated CSV",
            df.to_csv(index=False).encode(),
            file_name="updated_with_links.csv",
            mime="text/csv",
        )
