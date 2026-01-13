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
    page_title="Link2Img – Professional",
    page_icon="📦",
    layout="wide",
)

st.title("📦 Image Downloader → Company Server")

# ─────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────
if "user_logs" not in st.session_state:
    st.session_state.user_logs = []

if "admin_logs" not in st.session_state:
    st.session_state.admin_logs = []

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def log_user(msg):
    st.session_state.user_logs.append(msg)

def log_admin(msg):
    st.session_state.admin_logs.append(f"[{now_utc()}] {msg}")

def sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", name).strip() or "image"

def get_user_identity():
    try:
        return st.experimental_user.email
    except Exception:
        return "anonymous_user"

# ─────────────────────────────────────────────
# SIDEBAR – CONTROL PANEL
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Control Panel")
    mode = st.radio("Mode", ["User mode", "Admin mode"])
    st.divider()

    if mode == "User mode":
        st.markdown("### 📋 User Logs")
        for l in st.session_state.user_logs[-200:]:
            st.markdown(f"- {l}")

    if mode == "Admin mode":
        st.markdown("### 🛡 Admin Logs")
        for l in reversed(st.session_state.admin_logs[-300:]):
            st.code(l)

# ─────────────────────────────────────────────
# LOAD SECRETS
# ─────────────────────────────────────────────
AWS_ACCESS_KEY = st.secrets["AWS_ACCESS_KEY_ID"]
AWS_SECRET_KEY = st.secrets["AWS_SECRET_ACCESS_KEY"]
S3_BUCKET = st.secrets["S3_BUCKET"]
AWS_REGION = "eu-west-3"
PUBLIC_BASE = "https://static.ora.ma/streamlit/"

s3 = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION,
)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "image/*",
}

# ─────────────────────────────────────────────
# FILE UPLOAD
# ─────────────────────────────────────────────
uploaded_file = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx"])

if uploaded_file:
    df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)

    st.subheader("📌 Columns detected")
    st.json(list(df.columns))

    product_col = st.selectbox("Product column", df.columns)
    url_col = st.selectbox("Image URL column", df.columns)

    if st.button("🚀 Process Images"):
        st.session_state.user_logs = []

        user = get_user_identity()
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        folder = f"streamlit/{run_id}/"

        log_admin(f"START run_id={run_id} user={user} file={uploaded_file.name} rows={len(df)}")

        zip_buffer = BytesIO()
        server_urls = [None] * len(df)

        progress = st.progress(0.0)
        status = st.empty()

        uploaded = 0
        skipped = 0

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for i, row in df.iterrows():
                progress.progress((i + 1) / len(df))

                product = str(row[product_col]).strip()
                url = str(row[url_col]).strip()

                status.info(f"Processing row {i+1}: {product}")
                log_user(f"🔄 Row {i+1}: {product}")

                if not url.startswith("http"):
                    skipped += 1
                    log_user("❌ Invalid URL → skipped")
                    log_admin(f"SKIP user={user} row={i+1} product='{product}' reason=invalid_url")
                    continue

                try:
                    r = requests.get(url, headers=HEADERS, timeout=25)
                    r.raise_for_status()
                    log_user("✅ HTTP 200")

                    img = Image.open(BytesIO(r.content))
                    if img.mode == "RGBA":
                        img = img.convert("RGB")

                    raw_img = BytesIO()
                    img.save(raw_img, format="JPEG", quality=90)
                    raw_bytes = raw_img.getvalue()  # 🔥 STORE RAW BYTES

                    filename = sanitize(product) + ".jpg"
                    s3_key = folder + filename

                    # 🔐 S3 upload (new buffer)
                    s3.upload_fileobj(
                        BytesIO(raw_bytes),
                        S3_BUCKET,
                        s3_key,
                        ExtraArgs={"ContentType": "image/jpeg"},
                    )

                    # 📦 ZIP write (independent)
                    zipf.writestr(filename, raw_bytes)

                    public_url = f"{PUBLIC_BASE}{run_id}/{filename}"
                    server_urls[i] = public_url

                    uploaded += 1
                    log_user(f"✅ Uploaded → {public_url}")
                    log_admin(
                        f"UPLOAD user={user} row={i+1} product='{product}' url='{url}' → {public_url}"
                    )

                except Exception as e:
                    skipped += 1
                    log_user(f"❌ FAILED → {e}")
                    log_admin(
                        f"ERROR user={user} row={i+1} product='{product}' url='{url}' error='{e}'"
                    )

        df["Server Image URL"] = server_urls

        log_admin(f"END run_id={run_id} uploaded={uploaded} skipped={skipped}")

        st.success(f"🎉 Uploaded: {uploaded} | Skipped: {skipped}")

        st.download_button(
            "⬇️ Download Images ZIP",
            zip_buffer.getvalue(),
            file_name=f"images_{run_id}.zip",
            mime="application/zip",
        )

        st.download_button(
            "⬇️ Download Updated CSV",
            df.to_csv(index=False).encode("utf-8"),
            file_name=f"updated_{run_id}.csv",
            mime="text/csv",
        )
