from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, Request, BackgroundTasks
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from app.database import init_db, SessionLocal, Settings, Job
from app.services import EmailPoller, PrinterManager, convert_pdf_to_zpl

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
    try:
        zpl = convert_pdf_to_zpl(content)
        
        db = SessionLocal()
        job = Job(filename=file.filename, source="WEB", zpl_content=zpl)
        db.add(job)
        db.commit()
        job_id = job.id
        db.close()
        
        # Start printing in background
        mgr = PrinterManager()
        background_tasks.add_task(mgr.run_job, job_id)
        
        return JSONResponse({"status": "success", "job_id": job_id})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

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
