from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
import sqlite3
import os
import json
import io
import mimetypes
from threading import Lock

# 🔥 Google Drive
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

app = FastAPI()
templates = Jinja2Templates(directory=".")

# =========================
# 🧠 DATABASE
# =========================

conn = sqlite3.connect("db.sqlite", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    option TEXT,
    ip TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT
)
""")

conn.commit()

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
# 🖼️ IMÁGENES DESDE DRIVE
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

    print("🧠 IMAGES:", IMAGES)

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
# 🌐 ROUTES
# =========================

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# 🔥 VOTAR (ANTI DUPLICADO)
@app.post("/vote")
def vote(request: Request, option: str = Form(...)):
    ip = request.client.host

    # verificar si ya votó
    cursor.execute("SELECT * FROM votes WHERE ip=?", (ip,))
    existing = cursor.fetchone()

    if existing:
        return RedirectResponse(url="/", status_code=303)

    cursor.execute(
        "INSERT INTO votes (option, ip) VALUES (?, ?)",
        (option, ip)
    )
    conn.commit()

    return RedirectResponse(url="/", status_code=303)

# 📊 STATS TIEMPO REAL
@app.get("/stats")
def stats():
    cursor.execute("SELECT COUNT(*) FROM votes WHERE option='mbappe'")
    mbappe = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM votes WHERE option='stay'")
    stay = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM votes WHERE option='vinicius'")
    vinicius = cursor.fetchone()[0]

    return {
        "mbappe": mbappe,
        "stay": stay,
        "vinicius": vinicius
    }

# 💌 LEADS
@app.post("/lead")
def lead(email: str = Form(...)):
    cursor.execute("INSERT INTO leads (email) VALUES (?)", (email,))
    conn.commit()

    save_email_to_drive(email)

    return RedirectResponse(url="/", status_code=303)