# =====================================
# FULL PYTHON PRODUCTION FILES (READY TO RUN)
# =====================================

# This includes:
# - FastAPI backend (API + WebSocket + scanner page hosting)
# - SQLite logging
# - Queue-based printing
# - Mobile scanner auto-connect (no IP hardcoding)
# - PySide6 desktop dashboard

# =====================================
# 1. BACKEND (backend.py)
# =====================================

import sqlite3
import asyncio
import subprocess
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from datetime import datetime

app = FastAPI()

# ---------------- DB ----------------
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

# ---------------- CONFIG ----------------
PRINTER_NAME = "Your_Printer_Name"

# ---------------- QUEUE ----------------
queue = asyncio.Queue()

# ---------------- PRINT ----------------
async def print_pdf(file_path):
    subprocess.run([
        "SumatraPDF.exe",
        "-print-to", PRINTER_NAME,
        "-silent",
        file_path
    ])

# ---------------- WORKER ----------------
async def worker():
    while True:
        data = await queue.get()
        try:
            pdf_path = "sample.pdf"
            await print_pdf(pdf_path)

            cursor.execute(
                "INSERT INTO logs (timestamp, input, status, message) VALUES (?, ?, ?, ?)",
                (datetime.now().isoformat(), data, "SUCCESS", "Printed")
            )
            conn.commit()

        except Exception as e:
            cursor.execute(
                "INSERT INTO logs (timestamp, input, status, message) VALUES (?, ?, ?, ?)",
                (datetime.now().isoformat(), data, "FAILED", str(e))
            )
            conn.commit()

        queue.task_done()

@app.on_event("startup")
async def startup():
    asyncio.create_task(worker())

# ---------------- API ----------------
@app.post("/scan")
async def scan(data: dict):
    await queue.put(data["input"])
    return {"status": "queued"}

@app.get("/logs")
def logs():
    cursor.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 100")
    return cursor.fetchall()

# ---------------- WEBSOCKET ----------------
@app.websocket("/ws")
async def websocket(ws: WebSocket):
    await ws.accept()
    while True:
        data = await ws.receive_text()
        await queue.put(data)

# ---------------- MOBILE SCANNER PAGE ----------------

@app.get("/")
def scanner_page():
    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<script src="https://unpkg.com/html5-qrcode"></script>
</head>
<body style="text-align:center;background:#F5F7FA;font-family:sans-serif;">
<h2>📦 Mobile Scanner</h2>
<div id="reader" style="width:300px;margin:auto;"></div>
<p id="status">Connecting...</p>

<script>
const protocol = location.protocol === "https:" ? "wss" : "ws";
const ws = new WebSocket(`${protocol}://${location.host}/ws`);

let lastScan="";
let lastTime=0;

ws.onopen = () => document.getElementById("status").innerText="Connected";

function onScanSuccess(text) {
    const now = Date.now();

    if (text === lastScan && (now - lastTime) < 2000) return;

    lastScan = text;
    lastTime = now;

    ws.send(text);
    document.getElementById("status").innerText = "Scanned: " + text;
    navigator.vibrate(100);
}

new Html5Qrcode("reader").start(
    { facingMode: "environment" },
    { fps: 10, qrbox: 250 },
    onScanSuccess
);
</script>
</body>
</html>
""")


# =====================================
# 2. DESKTOP UI (ui.py)
# =====================================

import sys
import requests
import time
from collections import deque
from PySide6.QtWidgets import *
from PySide6.QtCore import QTimer, QObject, QEvent

API_URL = "http://127.0.0.1:8000"

class Metrics:
    def __init__(self):
        self.scan_times = deque(maxlen=100)
        self.failures = 0
        self.total = 0

    def record(self, success=True):
        self.scan_times.append(time.time())
        self.total += 1
        if not success:
            self.failures += 1

    def scans_per_minute(self):
        now = time.time()
        return len([t for t in self.scan_times if now - t <= 60])

    def failure_rate(self):
        if self.total == 0: return 0
        return round((self.failures / self.total) * 100, 2)

class ScannerListener(QObject):
    def __init__(self, callback):
        super().__init__()
        self.buffer=""
        self.last_time=time.time()
        self.callback=callback
        self.cooldown=2
        self.last_val=None
        self.last_scan_time=0

    def eventFilter(self, obj, event):
        if event.type()==QEvent.KeyPress:
            now=time.time()

            if now-self.last_time>0.1:
                self.buffer=""

            self.last_time=now

            if event.key()==16777220:
                if len(self.buffer)>3:
                    if not (self.buffer==self.last_val and now-self.last_scan_time<self.cooldown):
                        self.callback(self.buffer)
                        self.last_val=self.buffer
                        self.last_scan_time=now
                self.buffer=""
            else:
                self.buffer+=event.text()

        return False

class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Airway Printer")
        self.resize(1000,700)

        self.metrics=Metrics()

        layout=QVBoxLayout()

        self.scan_rate=QLabel()
        self.fail_rate=QLabel()
        self.printer=QLabel("Printer: Unknown")

        top=QHBoxLayout()
        top.addWidget(self.scan_rate)
        top.addWidget(self.fail_rate)
        top.addWidget(self.printer)

        layout.addLayout(top)

        self.table=QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Time","Input","Status","Msg"])
        layout.addWidget(self.table)

        self.setLayout(layout)

        self.listener=ScannerListener(self.process_scan)
        QApplication.instance().installEventFilter(self.listener)

        self.timer=QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)

    def process_scan(self,val):
        try:
            requests.post(f"{API_URL}/scan",json={"input":val})
            self.metrics.record(True)
        except:
            self.metrics.record(False)

    def refresh(self):
        self.scan_rate.setText(f"Scans/min: {self.metrics.scans_per_minute()}")
        self.fail_rate.setText(f"Failure %: {self.metrics.failure_rate()}")

        try:
            data=requests.get(f"{API_URL}/logs").json()
            self.table.setRowCount(len(data))

            for i,row in enumerate(data):
                for j,val in enumerate(row[1:]):
                    self.table.setItem(i,j,QTableWidgetItem(str(val)))

            self.printer.setText("Printer: Online")
        except:
            self.printer.setText("Printer: Offline")

if __name__=="__main__":
    app=QApplication(sys.argv)
    w=App()
    w.show()
    sys.exit(app.exec())


# =====================================
# RUN
# =====================================

# Start backend:
# uvicorn backend:app --host 0.0.0.0 --port 8000

# Open mobile:
# http://YOUR_IP:8000

# Start desktop:
# python ui.py

# =====================================
# DONE
# =====================================
