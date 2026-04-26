# =====================================
# PYTHON PRODUCTION VERSION
# FastAPI + WebSocket + SQLite + Print Queue + PySide6 UI
# =====================================

# INSTALL DEPENDENCIES:
# pip install fastapi uvicorn websockets pyside6 sqlite3 pydantic

# =====================================
# 1. BACKEND (FastAPI + Queue + SQLite)
# =====================================

# file: backend.py

import sqlite3
import asyncio
import subprocess
from fastapi import FastAPI, WebSocket
from pydantic import BaseModel
from datetime import datetime

app = FastAPI()

# DB INIT
conn = sqlite3.connect("airway.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    input TEXT,
    status TEXT,
    message TEXT
)
""")
conn.commit()

# CONFIG
PRINTER_NAME = "Your_Printer_Name"

# QUEUE
queue = asyncio.Queue()

# PRINT FUNCTION
async def print_pdf(file_path):
    try:
        subprocess.run([
            "SumatraPDF.exe",
            "-print-to", PRINTER_NAME,
            "-silent",
            file_path
        ])
    except Exception as e:
        raise e

# WORKER
async def worker():
    while True:
        job = await queue.get()
        input_value = job
        try:
            # Simulate lookup
            pdf_path = "sample.pdf"

            await print_pdf(pdf_path)

            cursor.execute("INSERT INTO logs (timestamp, input, status, message) VALUES (?, ?, ?, ?)",
                           (datetime.now().isoformat(), input_value, "SUCCESS", "Printed"))
            conn.commit()

        except Exception as e:
            cursor.execute("INSERT INTO logs VALUES (NULL, ?, ?, ?, ?)",
                           (datetime.now().isoformat(), input_value, "FAILED", str(e)))
            conn.commit()

        queue.task_done()

# START WORKER
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(worker())

# API
class ScanInput(BaseModel):
    input: str

@app.post("/scan")
async def scan(data: ScanInput):
    await queue.put(data.input)
    return {"status": "queued"}

@app.get("/logs")
def get_logs():
    cursor.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 100")
    return cursor.fetchall()

# WEBSOCKET (mobile scan)
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    while True:
        data = await ws.receive_text()
        await queue.put(data)


# =====================================
# 2. DESKTOP UI (PySide6)
# =====================================

# file: ui.py

import sys
import requests
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem
)
from PySide6.QtCore import QTimer

API_URL = "http://127.0.0.1:8000"

class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Airway Bill Auto Printer")
        self.resize(800, 600)

        layout = QVBoxLayout()

        self.label = QLabel("Waiting for scans...")
        layout.addWidget(self.label)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Time", "Input", "Status", "Message"])
        layout.addWidget(self.table)

        self.setLayout(layout)

        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_logs)
        self.timer.start(2000)

    def refresh_logs(self):
        try:
            res = requests.get(f"{API_URL}/logs").json()
            self.table.setRowCount(len(res))

            for row_idx, row in enumerate(res):
                for col_idx, value in enumerate(row[1:]):
                    self.table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))
        except:
            pass

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())


# =====================================
# 3. RUN INSTRUCTIONS
# =====================================

# Start backend:
# uvicorn backend:app --reload

# Start UI:
# python ui.py

# Scan using:
# - USB scanner (keyboard input mapped to API call if needed)
# - Mobile via WebSocket

# =====================================
# NEXT UPGRADES
# =====================================
# - Add real API lookup
# - Add printer config file
# - Add ZPL support
# - Add offline retry persistence
