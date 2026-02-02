import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, Request, BackgroundTasks, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from app.database import init_db, SessionLocal, Settings, Job
from app.services import EmailPoller, PrinterManager, convert_pdf_to_zpl

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
        "settings": settings
    })

@app.post("/upload")
async def manual_upload(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    content = await file.read()
    
    db = SessionLocal()
    try:
        job = Job(
            filename=file.filename, 
            source="Manual UI Upload", 
            status="PROCESSING"
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id

        pdf_path = os.path.join(DATA_DIR, f"{job_id}.pdf")
        with open(pdf_path, "wb") as f:
            f.write(content)

        try:
            zpl = convert_pdf_to_zpl(content)
            zpl_path = os.path.join(DATA_DIR, f"{job_id}.zpl")
            with open(zpl_path, "w") as f:
                f.write(zpl)

            job.zpl_content = zpl
            job.status = "COMPLETED"
            db.commit()

            if background_tasks:
                mgr = PrinterManager()
                background_tasks.add_task(mgr.run_job, job_id)

        except Exception as conv_err:
            job.status = "ERROR"
            job.log = f"Conversion failed: {str(conv_err)}"
            db.commit()
        return JSONResponse({"status": "success", "job_id": job_id})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        db.close()

@app.post("/settings")
async def update_settings(
    printer_ip: str = Form(...),
    email_user: str = Form(...),
    email_pass: str = Form(...),
    smart_plug_enabled: bool = Form(False),
    smart_plug_webhook: str = Form(""),
    smart_plug_off_webhook: str = Form("")
):
    db = SessionLocal()
    s = db.query(Settings).first()
    s.printer_ip = printer_ip
    s.email_user = email_user
    if email_pass.strip(): # Only update if provided
        s.email_pass = email_pass
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
    data = [{"id": j.id, "filename": j.filename, "status": j.status, "log": j.log, "time": j.created_at.isoformat()} for j in jobs]
    db.close()
    return data

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
