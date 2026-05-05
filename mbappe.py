from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
import sqlite3

# 🔥 Google Drive (ENV)
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
import io
import os
import json

app = FastAPI()
templates = Jinja2Templates(directory=".")

# =========================
# 🧠 DATABASE LOCAL
# =========================

conn = sqlite3.connect("db.sqlite", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    option TEXT
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
# 🎨 SERVIR CSS
# =========================

@app.get("/estilos.css")
def estilos():
    return FileResponse("estilos.css")

# =========================
# ☁️ GOOGLE DRIVE
# =========================

SCOPES = ['https://www.googleapis.com/auth/drive']

creds_json_str = os.getenv("GOOGLE_CREDS_JSON")
if not creds_json_str:
    raise ValueError("❌ Falta GOOGLE_CREDS_JSON en ENV")

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

        media = MediaIoBaseUpload(
            io.BytesIO(file_content),
            mimetype='text/plain'
        )

        drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()

    except Exception as e:
        print("❌ Error guardando en Drive:", e)
# =========================
# 🖼️ IMÁGENES (DISK CACHE 🔥)
# =========================

from fastapi.responses import FileResponse
from googleapiclient.http import MediaIoBaseDownload
import os

# 📁 Carpeta persistente en Render
DATA_DIR = "/var/data/images"
os.makedirs(DATA_DIR, exist_ok=True)

# 🔑 IDs reales de Drive
IMAGES = {
    "mbappe.jpg": "ID_MBAPPE",
    "vinicius.jpg": "ID_VINICIUS"
}

# 🔒 Locks para evitar descargas duplicadas
from threading import Lock
locks = {}

def get_lock(name):
    if name not in locks:
        locks[name] = Lock()
    return locks[name]

# ⬇️ Descargar desde Drive y guardar en disco
def download_from_drive(file_id, path):
    request = drive_service.files().get_media(fileId=file_id)

    with open(path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)

        done = False
        while not done:
            _, done = downloader.next_chunk()

# 🚀 Endpoint de imágenes
@app.get("/img/{image_name}")
def serve_image(image_name: str):
    if image_name not in IMAGES:
        return {"error": "Imagen no encontrada"}

    file_path = os.path.join(DATA_DIR, image_name)

    lock = get_lock(image_name)

    # 🔥 Evita descargas duplicadas concurrentes
    with lock:
        if not os.path.exists(file_path):
            download_from_drive(IMAGES[image_name], file_path)

    # ⚡ Sirve directo desde disco (rápido)
    return FileResponse(
        file_path,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=31536000"
        }
    )

# =========================
# 🌐 ROUTES
# =========================

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    cursor.execute("SELECT COUNT(*) FROM votes WHERE option='mbappe'")
    mbappe = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM votes WHERE option='vinicius'")
    vinicius = cursor.fetchone()[0]

    return templates.TemplateResponse("index.html", {
        "request": request,
        "mbappe": mbappe,
        "vinicius": vinicius
    })

@app.post("/vote")
def vote(option: str = Form(...)):
    cursor.execute("INSERT INTO votes (option) VALUES (?)", (option,))
    conn.commit()
    return RedirectResponse(url="/thanks", status_code=303)

@app.get("/thanks", response_class=HTMLResponse)
def thanks(request: Request):
    return templates.TemplateResponse("thanks.html", {"request": request})

@app.post("/lead")
def lead(email: str = Form(...)):
    cursor.execute("INSERT INTO leads (email) VALUES (?)", (email,))
    conn.commit()

    save_email_to_drive(email)

    return RedirectResponse(url="/", status_code=303)