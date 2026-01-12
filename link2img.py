import streamlit as st
import pandas as pd
import boto3
import requests
from PIL import Image
from io import BytesIO
import zipfile
import re
from datetime import datetime, timezone
import uuid

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Image → ZIP + Server",
    page_icon="📦",
    layout="wide",
)

# ─────────────────────────────────────────────
# SESSION INIT
# ─────────────────────────────────────────────
if "USER_LOGS" not in st.session_state:
    st.session_state.USER_LOGS = []

if "ADMIN_LOGS" not in st.session_state:
    st.session_state.ADMIN_LOGS = []

# ─────────────────────────────────────────────
# SAFE TIME
# ─────────────────────────────────────────────
def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

# ─────────────────────────────────────────────
# USER IDENTIFICATION (SAFE)
# ─────────────────────────────────────────────
def get_user_email():
    try:
        return st.user.email
    except Exception:
        return "unknown@user"

USER_EMAIL = get_user_email()
SESSION_ID = str(uuid.uuid4())[:8]
SESSION_TIME = utc_now()

# ─────────────────────────────────────────────
# ADMIN CONFIG
# ─────────────────────────────────────────────
ADMIN_EMAILS = st.secrets.get("ADMIN_EMAILS", [])
IS_ADMIN = USER_EMAIL in ADMIN_EMAILS

# ─────────────────────────────────────────────
# LOG HELPERS
# ─────────────────────────────────────────────
def user_log(msg, level="info"):
    st.session_state.USER_LOGS.append((level, msg))

def admin_log(action, details):
    st.session_state.ADMIN_LOGS.append({
        "time": utc_now(),
        "user": USER_EMAIL,
        "session": SESSION_ID,
        "action": action,
        "details": details,
    })

# ─────────────────────────────────────────────
# SIDEBAR (LEFT PANEL)
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Control Panel")

    MODE = st.radio(
        "Mode",
        ["User mode"] + (["Admin mode"] if IS_ADMIN else []),
    )

    st.markdown("---")

    show_logs = st.toggle("Show logs", value=True)

    if MODE == "Admin mode":
        st.markdown("### 🛡 Admin Logs")
        if show_logs:
            for log in reversed(st.session_state.ADMIN_LOGS):
                st.markdown(
                    f"""
                    🕒 **{log['time']}**  
                    👤 `{log['user']}`  
                    🔑 `{log['session']}`  
                    🔁 **{log['action']}**  
                    📝 {log['details']}
                    ---
                    """
                )

    else:
        st.markdown("### 👤 User Logs")
        if show_logs:
            for level, msg in st.session_state.USER_LOGS:
                if level == "error":
                    st.error(msg)
                elif level == "success":
                    st.success(msg)
                else:
                    st.info(msg)

# ─────────────────────────────────────────────
# MAIN UI
# ─────────────────────────────────────────────
st.title("📦 Image Downloader → Company Server")
st.caption(f"👤 {USER_EMAIL} | 🕒 {SESSION_TIME} | 🔑 {SESSION_ID}")

# ─────────────────────────────────────────────
# S3 CONFIG
# ─────────────────────────────────────────────
AWS_ACCESS_KEY = st.secrets["AWS_ACCESS_KEY_ID"]
AWS_SECRET_KEY = st.secrets["AWS_SECRET_ACCESS_KEY"]
S3_BUCKET = st.secrets["S3_BUCKET"]
AWS_REGION = "eu-west-3"
PUBLIC_BASE_URL = "https://static.ora.ma/streamlit/"

s3 = boto3.client(
    "s3",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
)

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def sanitize_filename(name):
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
    df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)
    admin_log("CSV uploaded", uploaded.name)

    st.subheader("📌 Columns detected")
    st.json(list(df.columns))

    product_col = st.selectbox("Product column", df.columns)
    url_col = st.selectbox("Image URL column", df.columns)

    if st.button("🚀 Process Images"):
        user_log("Starting image processing…")
        session_folder = f"streamlit/{SESSION_ID}/"
        zip_buffer = BytesIO()
        server_urls = [None] * len(df)

        uploaded_count = 0
        skipped_count = 0

        progress = st.progress(0.0)

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for idx, row in df.iterrows():
                progress.progress((idx + 1) / len(df))
                product = str(row[product_col])
                url = str(row[url_col])

                user_log(f"Row {idx+1}: {product}")

                if not url.startswith("http"):
                    user_log("Invalid URL → skipped", "error")
                    skipped_count += 1
                    continue

                try:
                    r = requests.get(url, headers=HEADERS, timeout=20)
                    user_log(f"HTTP {r.status_code}")

                    r.raise_for_status()

                    img = Image.open(BytesIO(r.content))
                    user_log(f"Image opened | mode={img.mode}")

                    img = img.convert("RGB")

                    img_buffer = BytesIO()
                    img.save(img_buffer, "JPEG", quality=90)
                    img_buffer.seek(0)

                    filename = sanitize_filename(product) + ".jpg"
                    s3_key = session_folder + filename

                    s3.upload_fileobj(
                        img_buffer,
                        S3_BUCKET,
                        s3_key,
                        ExtraArgs={"ContentType": "image/jpeg"},
                    )

                    public_url = f"{PUBLIC_BASE_URL}{SESSION_ID}/{filename}"
                    server_urls[idx] = public_url

                    zipf.writestr(filename, img_buffer.getvalue())

                    user_log(f"Uploaded → {public_url}", "success")
                    uploaded_count += 1

                except Exception as e:
                    user_log(f"FAILED: {str(e)}", "error")
                    skipped_count += 1

        df["Server Image URL"] = server_urls

        admin_log(
            "Processing finished",
            f"Uploaded={uploaded_count}, Skipped={skipped_count}, Output CSV generated",
        )

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
