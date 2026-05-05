from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
import sqlite3
import os
import json
import io
import mimetypes
from threading import Lock
import requests
import re
import time

# 🔥 Google Drive
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

app = FastAPI()
templates = Jinja2Templates(directory=".")

# =========================
# 🧠 DATABASE
# =========================



DB_PATH = "/var/data/votes.db"

def get_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)
import os

if not os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        option TEXT,
        ip TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT
    )
    """)

    conn.commit()
    conn.close()
# =========================
# 🎨 CSS
# =========================

@app.get("/estilos.css")
def estilos():
    return FileResponse("estilos.css")

# =========================
# ☁️ GOOGLE DRIVE
# =========================

SCOPES = ['https://www.googleapis.com/auth/drive']

creds_json_str = os.getenv("GOOGLE_CREDS_JSON")
creds_dict = json.loads(creds_json_str)

credentials = service_account.Credentials.from_service_account_info(
    creds_dict,
    scopes=SCOPES
)

drive_service = build('drive', 'v3', credentials=credentials)

FOLDER_ID = "19Rq5-1457Y7b4TAu995pTxOvwmub7slf"

def save_email_to_drive(email: str):
    try:
        file_content = email.encode()

        file_metadata = {
            'name': f'{email}.txt',
            'parents': [FOLDER_ID]
        }

        media = MediaIoBaseUpload(io.BytesIO(file_content), mimetype='text/plain')

        drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()

    except Exception as e:
        print("❌ Error Drive:", e)

# =========================
# 🖼️ IMÁGENES
# =========================

DATA_DIR = "/var/data/images"
os.makedirs(DATA_DIR, exist_ok=True)

IMAGES = {}
locks = {}

def get_lock(name):
    if name not in locks:
        locks[name] = Lock()
    return locks[name]

def load_images_from_drive():
    global IMAGES

    results = drive_service.files().list(
        q=f"'{FOLDER_ID}' in parents and trashed=false",
        fields="files(id, name)"
    ).execute()

    files = results.get("files", [])
    IMAGES = {file["name"]: file["id"] for file in files}

def download_from_drive(file_id, path):
    request = drive_service.files().get_media(fileId=file_id)

    with open(path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

@app.get("/img/{image_name}")
def serve_image(image_name: str):

    if not IMAGES:
        load_images_from_drive()

    if image_name not in IMAGES:
        return {"error": "No existe"}

    file_path = os.path.join(DATA_DIR, image_name)

    lock = get_lock(image_name)

    with lock:
        if not os.path.exists(file_path):
            download_from_drive(IMAGES[image_name], file_path)

    media_type, _ = mimetypes.guess_type(file_path)

    return FileResponse(file_path, media_type=media_type)

# =========================
# 🌍 SCRAPER EXTERNO (CLAVE)
# =========================

external_cache = {
    "value": 0,
    "last_update": 0
}

def get_external_votes():
    # 🔥 cache 30s
    if time.time() - external_cache["last_update"] < 30:
        return external_cache["value"]

    try:
        url = "https://mbappeout.replit.app/"
        res = requests.get(url, timeout=5)
        html = res.text

        # 🔥 detectar número tipo 2.525.160
        match = re.search(r'(\d{1,3}(?:\.\d{3})+)', html)

        if match:
            number = match.group(1)
            number = int(number.replace(".", ""))

            # 🚀 DETECTAR SALTO GRANDE (ej: +5000)
            if abs(number - external_cache["value"]) > 5000:
                print("🚀 SALTO DETECTADO:", number)

            external_cache["value"] = number
            external_cache["last_update"] = time.time()

            print("🌍 EXTERNO:", number)

        return external_cache["value"]

    except Exception as e:
        print("❌ ERROR scraping:", e)
        return external_cache["value"]

# =========================
# 🌐 ROUTES
# =========================
import sqlite3

def get_db():
    return sqlite3.connect("tu_db.db", check_same_thread=False)
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
import os
from fastapi import Query, HTTPException

ADMIN_KEY = os.getenv("ADMIN_KEY")
from fastapi import Query, HTTPException

ADMIN_KEY = os.getenv("ADMIN_KEY")

@app.post("/admin/vote")
def admin_vote(
    option: str = Query(...),
    key: str = Query(...),
    amount: int = Query(1)
):
    if key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="No autorizado")

    conn = get_db()
    cursor = conn.cursor()

    data = [(option,) for _ in range(amount)]

    cursor.executemany(
        "INSERT INTO votes (option) VALUES (?)",
        data
    )

    conn.commit()
    conn.close()

    return {"ok": True, "added": amount}


@app.post("/vote")
def vote(request: Request, option: str = Form(...)):
    conn = get_db()
    cursor = conn.cursor()

    ip = request.client.host

    cursor.execute("SELECT 1 FROM votes WHERE ip=?", (ip,))
    if cursor.fetchone():
        conn.close()
        return RedirectResponse(url="/", status_code=303)

    cursor.execute(
        "INSERT INTO votes (option, ip) VALUES (?, ?)",
        (option, ip)
    )

    conn.commit()
    conn.close()

    return RedirectResponse(url="/", status_code=303)


import sqlite3
@app.get("/stats")
def stats():
    try:
        conn = get_db()
        cursor = conn.cursor()

        GOAL = 200000

        BASE_MBAPPE_OUT = 3912138
        BASE_MBAPPE_STAY = 1098432
        BASE_VINI_OUT = 523344
        BASE_VINI_STAY = 1233233

        cursor.execute("SELECT COUNT(*) FROM votes WHERE option='mbappe_out'")
        mbappe_out_real = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM votes WHERE option='mbappe_stay'")
        mbappe_stay_real = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM votes WHERE option='vini_out'")
        vini_out_real = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM votes WHERE option='vini_stay'")
        vini_stay_real = cursor.fetchone()[0] or 0

        conn.close()

        mbappe_out = BASE_MBAPPE_OUT + mbappe_out_real
        mbappe_stay = BASE_MBAPPE_STAY + mbappe_stay_real
        vini_out = BASE_VINI_OUT + vini_out_real
        vini_stay = BASE_VINI_STAY + vini_stay_real

        mbappe_total = mbappe_out + mbappe_stay
        vini_total = vini_out + vini_stay

        def calc(v, goal):
            if goal <= 0:
                goal = 1
            return min((v / goal) * 100, 100)

        return {
            "mbappe_out": mbappe_out,
            "mbappe_stay": mbappe_stay,
            "vini_out": vini_out,
            "vini_stay": vini_stay,
            "goal": GOAL,
            "mbappe_progress": calc(mbappe_total, GOAL),
            "vini_progress": calc(vini_total, GOAL),
            "mbappe_total": mbappe_total,
            "vini_total": vini_total
        }

    except Exception as e:
        print("❌ ERROR /stats:", e)
        return {}





# 💌 LEADS
@app.post("/lead")
def lead(email: str = Form(...)):
    cursor.execute("INSERT INTO leads (email) VALUES (?)", (email,))
    conn.commit()

    save_email_to_drive(email)

    return RedirectResponse(url="/", status_code=303)