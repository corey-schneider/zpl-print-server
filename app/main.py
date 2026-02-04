import asyncio
import os
import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, Request, BackgroundTasks, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from app.database import init_db, SessionLocal, Settings, Job
from app.services import EmailPoller, PrinterManager, LabelConverter
from app.ebay_service import EBayAPI
from app.webhook_service import WebhookVerifier, WebhookVerificationError
from app.encryption import IS_FIRST_RUN

logger = logging.getLogger(__name__)

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

@app.post("/upload")
async def manual_upload(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    content = await file.read()
    db = SessionLocal()
    
    job = Job(filename=file.filename, source="Manual UI Upload", status="READY")
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = job.id

    try:
        # Store PDF
        pdf_path = os.path.join(DATA_DIR, f"{job_id}.pdf")
        with open(pdf_path, "wb") as f:
            f.write(content)

        # Pre-generate ZPL as fallback (in case PDF passthrough fails)
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
    printer_ip: str = Form(...),
    email_user: str = Form(...),
    email_pass: str = Form(""),
    email_filter_from: str = Form(""),
    email_filter_subject: str = Form(""),
    email_filter_body: str = Form(""),
    scan_interval: int = Form(60),
    smart_plug_enabled: bool = Form(False),
    smart_plug_webhook: str = Form(""),
    smart_plug_off_webhook: str = Form(""),
    ebay_enabled: bool = Form(False),
    ebay_app_id: str = Form(""),
    ebay_cert_id: str = Form(""),
    ebay_user_token: str = Form(""),
    ebay_refresh_token: str = Form(""),
    ebay_webhook_enabled: bool = Form(False),
    ebay_webhook_url: str = Form("")
):
    db = SessionLocal()
    s = db.query(Settings).first()
    s.printer_ip = printer_ip
    s.email_user = email_user
    if email_pass.strip(): # Only update password if provided
        s.email_pass = email_pass
    # Always update email filters (allows clearing filters or changing them)
    s.email_filter_from = email_filter_from
    s.email_filter_subject = email_filter_subject
    s.email_filter_body = email_filter_body
    if scan_interval and scan_interval >= 10: # Only update if provided and valid
        s.scan_interval = scan_interval
    s.smart_plug_enabled = smart_plug_enabled
    s.smart_plug_webhook = smart_plug_webhook
    s.smart_plug_off_webhook = smart_plug_off_webhook
    # eBay API settings
    s.ebay_enabled = ebay_enabled
    if ebay_app_id.strip():
        s.ebay_app_id = ebay_app_id
    if ebay_cert_id.strip():
        s.ebay_cert_id = ebay_cert_id
    if ebay_user_token.strip():
        s.ebay_user_token = ebay_user_token
    if ebay_refresh_token.strip():
        s.ebay_refresh_token = ebay_refresh_token
    # eBay Webhook settings
    s.ebay_webhook_enabled = ebay_webhook_enabled
    if ebay_webhook_url.strip():
        s.ebay_webhook_url = ebay_webhook_url
    db.commit()
    db.close()
    return JSONResponse({"status": "saved"})

@app.get("/api/jobs")
async def get_jobs():
    db = SessionLocal()
    jobs = db.query(Job).order_by(Job.created_at.desc()).limit(10).all()
    data = [{"id": j.id, "filename": j.filename, "status": j.status, "log": j.log, "source": j.source, "time": j.created_at.isoformat()} for j in jobs]
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

@app.post("/api/test-ebay")
async def test_ebay():
    """Test eBay API connection with stored credentials."""
    db = SessionLocal()
    settings = db.query(Settings).first()
    db.close()
    
    if not settings or not settings.ebay_app_id or not settings.ebay_cert_id or not settings.ebay_user_token:
        return JSONResponse({
            "status": "not_configured",
            "message": "eBay credentials not configured"
        })
    
    try:
        ebay = EBayAPI(
            app_id=settings.ebay_app_id,
            cert_id=settings.ebay_cert_id,
            user_token=settings.ebay_user_token,
            refresh_token=settings.ebay_refresh_token
        )
        result = await ebay.test_connection()
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({
            "status": "error",
            "message": f"❌ Test failed: {str(e)}"
        })

@app.post("/api/fetch-ebay-labels")
async def fetch_ebay_labels(background_tasks: BackgroundTasks = None):
    """
    Fetch recently purchased shipping labels from eBay.
    Can be called manually or via webhook from eBay.
    """
    db = SessionLocal()
    settings = db.query(Settings).first()
    db.close()
    
    if not settings or not settings.ebay_enabled:
        return JSONResponse({
            "status": "error",
            "message": "eBay API not enabled"
        })
    
    try:
        ebay = EBayAPI(
            app_id=settings.ebay_app_id,
            cert_id=settings.ebay_cert_id,
            user_token=settings.ebay_user_token,
            refresh_token=settings.ebay_refresh_token
        )
        
        # Fetch labels from past 30 minutes
        labels = await ebay.fetch_recent_labels(minutes=30)
        
        if not labels:
            return JSONResponse({
                "status": "no_labels",
                "message": "No new labels found in the past 30 minutes"
            })
        
        # Save labels in background
        for label in labels:
            if background_tasks:
                background_tasks.add_task(
                    ebay.fetch_and_save_label,
                    label["order_id"],
                    label
                )
        
        return JSONResponse({
            "status": "success",
            "message": f"Found {len(labels)} label(s), fetching in background...",
            "count": len(labels)
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "status": "error",
            "message": f"Failed to fetch labels: {str(e)}"
        }, status_code=500)
# --- eBay WEBHOOK INTEGRATION ---

async def process_webhook_label(order_id: str, shipment_id: str, event_id: str):
    """
    Background task: Fetch label from eBay and create print job.
    This is called immediately when webhook is received.
    """
    try:
        db = SessionLocal()
        settings = db.query(Settings).first()
        db.close()
        
        if not settings or not settings.ebay_enabled:
            raise Exception("eBay API not enabled")
        
        ebay = EBayAPI(
            app_id=settings.ebay_app_id,
            cert_id=settings.ebay_cert_id,
            user_token=settings.ebay_user_token,
            refresh_token=settings.ebay_refresh_token
        )
        
        # Fetch the specific label
        labels = await ebay.fetch_recent_labels(minutes=5)
        label = next((l for l in labels if l["order_id"] == order_id), None)
        
        if label:
            job = await ebay.fetch_and_save_label(order_id, label)
            WebhookVerifier.update_webhook_event(
                event_id,
                status="COMPLETED",
                job_id=job.id if job else None
            )
            logger.info(f"Webhook: Created job {job.id if job else 'N/A'} for order {order_id}")
        else:
            raise Exception(f"Label not found for order {order_id}")
            
    except Exception as e:
        logger.error(f"Webhook processing error for {order_id}: {e}")
        WebhookVerifier.update_webhook_event(
            event_id,
            status="FAILED",
            error_message=str(e)
        )


@app.post("/webhooks/ebay")
async def handle_ebay_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    eBay webhook endpoint - Handles label purchase notifications.
    
    Security:
    - HMAC-SHA256 signature verification
    - Timestamp validation (prevents replay attacks)
    - Idempotency check (prevents duplicate processing)
    - Returns 200 immediately, processes in background
    
    Reference:
    https://developer.ebay.com/api-docs/user-defined-subscriptions/webhooks
    """
    try:
        # Get settings and webhook secret
        db = SessionLocal()
        settings = db.query(Settings).first()
        db.close()
        
        if not settings or not settings.ebay_webhook_enabled:
            logger.warning("Webhook received but not enabled")
            return JSONResponse({"status": "disabled"}, status_code=204)
        
        if not settings.ebay_webhook_secret:
            logger.error("Webhook secret not configured")
            return JSONResponse({"status": "error", "message": "Webhook not configured"}, status_code=400)
        
        # Get headers
        x_ebay_signature = request.headers.get("X-EBAY-SIGNATURE", "")
        x_ebay_timestamp = request.headers.get("X-EBAY-DELIVERY-TIMESTAMP", "")
        
        if not x_ebay_signature or not x_ebay_timestamp:
            logger.warning("Missing webhook headers")
            return JSONResponse({"status": "error", "message": "Missing headers"}, status_code=400)
        
        # Get raw request body
        body = await request.body()
        
        # 1. Verify HMAC-SHA256 signature
        if not WebhookVerifier.verify_signature(
            settings.ebay_webhook_secret,
            body.decode('utf-8'),
            x_ebay_signature
        ):
            logger.error("Webhook signature verification failed")
            return JSONResponse({"status": "error", "message": "Signature verification failed"}, status_code=401)
        
        # 2. Verify timestamp (prevents replay attacks)
        if not WebhookVerifier.verify_timestamp(x_ebay_timestamp):
            logger.warning(f"Webhook timestamp validation failed: {x_ebay_timestamp}")
            return JSONResponse({"status": "error", "message": "Timestamp too old"}, status_code=400)
        
        # 3. Parse payload
        try:
            payload = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            logger.error("Failed to parse webhook JSON")
            return JSONResponse({"status": "error", "message": "Invalid JSON"}, status_code=400)
        
        # 4. Extract event information
        try:
            event_id, event_type, order_id, shipment_id = WebhookVerifier.parse_ebay_webhook(payload)
        except ValueError as e:
            logger.warning(f"Failed to parse webhook: {e}")
            return JSONResponse({"status": "error", "message": str(e)}, status_code=400)
        
        # 5. Check idempotency (prevent duplicate processing)
        is_new, existing_job_id = WebhookVerifier.check_idempotency(event_id)
        if not is_new:
            logger.info(f"Duplicate webhook detected: {event_id}")
            # Return 200 immediately even for duplicates (eBay expects this)
            return JSONResponse({"status": "success", "message": "Already processed"})
        
        # 6. Record webhook event
        WebhookVerifier.record_webhook_event(
            event_id=event_id,
            event_type=event_type,
            order_id=order_id,
            shipment_id=shipment_id,
            payload=payload,
            status="PROCESSING"
        )
        
        logger.info(f"Valid webhook received: {event_type} for order {order_id}")
        
        # 7. Queue background task to fetch label and print
        background_tasks.add_task(
            process_webhook_label,
            order_id,
            shipment_id,
            event_id
        )
        
        # Return 200 immediately - eBay expects fast response
        return JSONResponse({"status": "success", "message": "Webhook queued for processing"})
        
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return JSONResponse({"status": "error", "message": "Internal server error"}, status_code=500)


@app.post("/api/generate-webhook-secret")
async def generate_webhook_secret():
    """Generate a new eBay webhook secret and return it."""
    try:
        db = SessionLocal()
        settings = db.query(Settings).first()
        
        if not settings:
            db.close()
            return JSONResponse({"status": "error", "message": "Settings not found"}, status_code=400)
        
        # Generate new secret (256-bit = 32 bytes)
        secret = settings.generate_webhook_secret()
        db.commit()
        db.close()
        
        logger.info("New webhook secret generated")
        
        return JSONResponse({
            "status": "success",
            "message": "New webhook secret generated",
            "secret": secret
        })
    except Exception as e:
        logger.error(f"Failed to generate webhook secret: {e}")
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)


@app.get("/api/webhook-events")
async def get_webhook_events(limit: int = 20):
    """Get recent webhook events for debugging."""
    try:
        db = SessionLocal()
        from app.database import WebhookEvent
        
        events = db.query(WebhookEvent).order_by(
            WebhookEvent.received_at.desc()
        ).limit(limit).all()
        
        data = [{
            "id": e.id,
            "event_id": e.event_id,
            "event_type": e.event_type,
            "order_id": e.order_id,
            "status": e.status,
            "received_at": e.received_at.isoformat(),
            "processed_at": e.processed_at.isoformat() if e.processed_at else None,
            "job_id": e.job_id,
            "error": e.error_message
        } for e in events]
        
        db.close()
        return data
    except Exception as e:
        logger.error(f"Failed to get webhook events: {e}")
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)
