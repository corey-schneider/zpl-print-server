import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, Request, BackgroundTasks, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from app.database import init_db, SessionLocal, Settings, Job
from app.services import EmailPoller, PrinterManager, LabelConverter
from app.encryption import IS_FIRST_RUN

DATA_DIR = "/app/data"

email_poller = EmailPoller()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    asyncio.create_task(email_poller.start())
    yield
    email_poller.stop()

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# --- WEB ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    db = SessionLocal()
    settings = db.query(Settings).first()
    jobs = db.query(Job).order_by(Job.created_at.desc()).limit(20).all()
    db.close()
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "jobs": jobs, 
        "settings": settings,
        "is_first_run": IS_FIRST_RUN
    })

@app.get("/help", response_class=HTMLResponse)
async def help_page(request: Request):
    return templates.TemplateResponse("help.html", {"request": request})

def _detect_file_type(filename: str, content: bytes) -> str:
    """Detect if file is PDF or ZPL based on extension and content."""
    ext = filename.lower().split('.')[-1] if '.' in filename else ''
    
    # Check extension first (most reliable)
    if ext == 'pdf':
        return 'pdf'
    if ext == 'zpl':
        return 'zpl'
    
    # Fallback: check first byte
    if content.startswith(b'%PDF'):
        return 'pdf'
    if content.startswith(b'^') or content.startswith(b'%'):
        return 'zpl'
    
    # Default to PDF if unsure
    return 'pdf'

@app.post("/upload")
async def upload_file(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    """Universal upload endpoint - auto-detects PDF or ZPL and routes accordingly."""
    content = await file.read()
    file_type = _detect_file_type(file.filename, content)
    db = SessionLocal()
    
    # Determine source based on file type
    if file_type == 'zpl':
        source = "ZPL Direct Upload"
    else:
        source = "Manual UI Upload"
    
    job = Job(filename=file.filename, source=source, status="READY")
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = job.id

    try:
        if file_type == 'zpl':
            # ZPL: Store directly as binary (lossless)
            zpl_path = os.path.join(DATA_DIR, f"{job_id}.zpl")
            with open(zpl_path, "wb") as f:
                f.write(content)
            job.log = "Ready - ZPL direct upload (no conversion)"
        else:
            # PDF: Store PDF and generate ZPL conversion
            pdf_path = os.path.join(DATA_DIR, f"{job_id}.pdf")
            with open(pdf_path, "wb") as f:
                f.write(content)
            
            converter = LabelConverter()
            zpl_content = converter.convert_pdf_to_zpl(content, job_id=job_id)
            zpl_path = os.path.join(DATA_DIR, f"{job_id}.zpl")
            with open(zpl_path, "w") as f:
                f.write(zpl_content)
            job.log = "Ready - will try PDF first, then ZPL fallback"
        
        db.commit()

        # Start printing in background
        if background_tasks:
            mgr = PrinterManager()
            background_tasks.add_task(mgr.run_job, job_id)
            
    except Exception as e:
        job.status = "FAILED"
        job.log = f"Error: {str(e)}"
        db.commit()
    finally:
        db.close()

    return JSONResponse({"status": "accepted", "job_id": job_id})

@app.post("/settings")
async def update_settings(
    printer_ip: str = Form(""),
    email_user: str = Form(""),
    email_pass: str = Form(""),
    email_polling_enabled: bool = Form(False),
    email_filter_from: str = Form(""),
    email_filter_subject: str = Form(""),
    email_filter_body: str = Form(""),
    scan_interval: str = Form("60"),
    smart_plug_enabled: bool = Form(False),
    smart_plug_webhook: str = Form(""),
    smart_plug_off_webhook: str = Form("")
):
    db = SessionLocal()
    s = db.query(Settings).first()
    if printer_ip:
        s.printer_ip = printer_ip
    s.email_user = email_user
    # Always update email password (allows clearing by submitting empty value)
    s.email_pass = email_pass.strip() if email_pass else ""
    # Email polling toggle
    s.email_polling_enabled = email_polling_enabled
    # Always update email filters (allows clearing filters or changing them)
    s.email_filter_from = email_filter_from
    s.email_filter_subject = email_filter_subject
    s.email_filter_body = email_filter_body
    # Handle scan_interval as string and convert safely
    try:
        interval = int(scan_interval) if scan_interval else 60
        if interval >= 10:
            s.scan_interval = interval
    except (ValueError, TypeError):
        pass  # Keep existing value if invalid
    s.smart_plug_enabled = smart_plug_enabled
    s.smart_plug_webhook = smart_plug_webhook
    s.smart_plug_off_webhook = smart_plug_off_webhook
    db.commit()
    db.close()
    return JSONResponse({"status": "saved"})

@app.get("/api/jobs")
async def get_jobs():
    db = SessionLocal()
    jobs = db.query(Job).order_by(Job.created_at.desc()).limit(10).all()
    data = [{"id": j.id, "filename": j.filename, "status": j.status, "log": j.log, "source": j.source, "created_at": j.created_at.isoformat()} for j in jobs]
    db.close()
    return data

@app.get("/preview/zpl/{job_id}")
async def preview_job(job_id: int):
    """Preview the rendered ZPL as a PNG image."""
    file_path = os.path.join(DATA_DIR, f"{job_id}_preview.png")
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="Preview image not found. Job may still be processing.")

@app.get("/preview/pdf/{job_id}")
async def preview_pdf(job_id: int):
    # Search for the file based on ID
    file_path = os.path.join(DATA_DIR, f"{job_id}.pdf")
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="application/pdf")
    raise HTTPException(status_code=404, detail="PDF file not found on disk.")

@app.get("/download/pdf/{job_id}")
async def download_pdf(job_id: int):
    file_path = f"/app/data/{job_id}.pdf"
    if os.path.exists(file_path):
        return FileResponse(
            path=file_path, 
            media_type="application/pdf",
            # filename=f"label_{job_id}.pdf" # This forces the 'Save As' dialog
        )
    raise HTTPException(status_code=404, detail="PDF file not found.")

@app.get("/download/zpl/{job_id}")
async def download_zpl(job_id: int):
    file_path = os.path.join(DATA_DIR, f"{job_id}.zpl")
    if os.path.exists(file_path):
        return FileResponse(
            file_path, 
            media_type="text/plain", 
            filename=f"label_{job_id}.zpl"
        )
    raise HTTPException(status_code=404, detail="ZPL file not found on disk.")

@app.post("/api/test-email")
async def test_email():
    """Manually trigger email polling for testing."""
    try:
        result = await email_poller.poll()
        return JSONResponse(result if result else {"status": "success", "message": "Email poll completed"})
    except Exception as e:
        return JSONResponse({"status": "failed", "reason": str(e)}, status_code=500)

@app.get("/api/printer-status")
async def get_printer_status():
    """Check the current printer connection status."""
    db = SessionLocal()
    settings = db.query(Settings).first()
    db.close()
    
    if not settings or not settings.printer_ip:
        return JSONResponse({
            "status": "not_configured",
            "message": "Printer IP not configured",
            "ip": None
        })
    
    mgr = PrinterManager(printer_ip=settings.printer_ip)
    
    if mgr.is_printer_online():
        return JSONResponse({
            "status": "connected",
            "message": f"✅ Connected to {settings.printer_ip}:{mgr.printer_port}",
            "ip": settings.printer_ip
        })
    else:
        return JSONResponse({
            "status": "offline",
            "message": f"❌ Could not reach printer at {settings.printer_ip}:{mgr.printer_port}",
            "ip": settings.printer_ip
        })
