import os
import io
import asyncio
import binascii
import socket
import logging
import numpy as np
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageOps, ImageFilter
from pyzbar.pyzbar import decode, ZBarSymbol

# Setup logging for a production environment
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class LabelConverter:
    """
    Minimal PDF to ZPL converter.
    Renders PDF to image and converts to ZPL format cleanly.
    """
    def __init__(self, dpi=203, width_mm=101.6, height_mm=152.4):
        self.dpi = dpi
        self.width_px = int((width_mm / 25.4) * dpi)
        self.height_px = int((height_mm / 25.4) * dpi)

    def convert_pdf_to_zpl(self, pdf_bytes: bytes, job_id: int = None) -> str:
        try:
            # Render PDF at native DPI (203)
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            page = doc.load_page(0)
            zoom = self.dpi / 72
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            
            # Convert to PIL image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            # Resize to label dimensions first
            img = img.resize((self.width_px, self.height_px), Image.Resampling.LANCZOS)
            
            # Convert to grayscale
            img = img.convert("L")
            
            # Apply light sharpening to crisp edges
            from PIL import ImageFilter
            img = img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=100, threshold=1))
            
            # Use Otsu's adaptive thresholding for better contrast preservation
            import numpy as np
            img_array = np.array(img)
            threshold = np.mean(img_array)  # Simple but effective threshold
            img = Image.fromarray((img_array > threshold).astype(np.uint8) * 255)
            img = img.convert("1")
            
            # Save preview PNG if job_id provided
            if job_id:
                try:
                    png_path = f"/app/data/{job_id}_preview.png"
                    img.save(png_path)
                    logger.info(f"Preview PNG saved: {png_path}")
                except Exception as png_err:
                    logger.error(f"Failed to save preview PNG: {png_err}")
            else:
                logger.warning("No job_id provided to convert_pdf_to_zpl, preview PNG not saved")
            
            # Convert to ZPL
            zpl = self._image_to_zpl(img)
            
            return f"^XA^PW{self.width_px}^LL{self.height_px}{zpl}^XZ"
            
        except Exception as e:
            logger.error(f"Conversion Error: {e}")
            return f"^XA^FO50,50^A0N,36,36^FDError^FS^XZ"

    def _image_to_zpl(self, image: Image.Image) -> str:
        """
        Convert PIL image to ZPL hex format.
        Inverts bits to match ZPL convention (1=print, 0=skip).
        """
        # Invert: ZPL uses 1 for black (print), 0 for white
        img_inv = ImageOps.invert(image)
        
        width_bytes = (img_inv.width + 7) // 8
        total_bytes = width_bytes * img_inv.height
        hex_data = binascii.hexlify(img_inv.tobytes()).decode('utf-8').upper()
        
        return f"^GFA,{total_bytes},{total_bytes},{width_bytes},{hex_data}"

# --- 2. INFRASTRUCTURE & BACKGROUND TASKS ---

class PrinterManager:
    """Manages sending ZPL jobs directly to Zebra printers via socket connection."""
    def __init__(self, printer_ip: str = None, printer_port: int = 9100):
        self.printer_ip = printer_ip or "192.168.1.111"
        self.printer_port = printer_port

    def update_job_status(self, job_id, status, log=None):
        from app.database import SessionLocal, Job
        db = SessionLocal()
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = status
            if log: job.log = log
            db.commit()
        db.close()

    def is_printer_online(self) -> bool:
        """Checks if printer is reachable via socket connection."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((self.printer_ip, self.printer_port))
            sock.close()
            return result == 0
        except Exception as e:
            logger.error(f"Printer connectivity check failed: {e}")
            return False

    async def run_job(self, job_id: int):
        # Get printer IP from settings
        from app.database import SessionLocal, Settings, Job
        db = SessionLocal()
        settings = db.query(Settings).first()
        job = db.query(Job).filter(Job.id == job_id).first()
        db.close()
        
        if settings and settings.printer_ip:
            self.printer_ip = settings.printer_ip
        
        if not self.is_printer_online():
            self.update_job_status(job_id, "QUEUED", f"Printer offline at {self.printer_ip}:{self.printer_port}. Job queued.")
            logger.info(f"Job {job_id} queued - printer is offline")
            return

        self.update_job_status(job_id, "SENDING", "Connecting to printer...")
        
        try:
            # Check if this is a direct ZPL upload (already in correct format)
            if job and job.source == "ZPL Direct Upload":
                # Send ZPL directly without any processing
                await self._send_zpl_direct(job_id)
            else:
                # Standard PDF workflow: try PDF passthrough, fall back to ZPL
                pdf_path = f"/app/data/{job_id}.pdf"
                success = await self._try_pdf_passthrough(job_id, pdf_path)
                
                if not success:
                    # Fall back to ZPL if PDF doesn't work
                    logger.info(f"PDF passthrough failed for job {job_id}, falling back to ZPL")
                    await self._try_zpl_fallback(job_id, pdf_path)
                
        except Exception as e:
            self.update_job_status(job_id, "FAILED", f"Error: {str(e)}")

    async def process_queued_jobs(self):
        """Process all queued jobs when printer comes back online."""
        from app.database import SessionLocal, Job
        
        while True:
            try:
                # Check every 10 seconds for queued jobs
                await asyncio.sleep(10)
                
                db = SessionLocal()
                queued_jobs = db.query(Job).filter(Job.status == "QUEUED").order_by(Job.created_at).all()
                db.close()
                
                if not queued_jobs:
                    continue  # No queued jobs, keep polling
                
                # Check if printer is online
                if not self.is_printer_online():
                    continue  # Printer still offline, wait and try again
                
                logger.info(f"Printer is back online! Processing {len(queued_jobs)} queued jobs...")
                
                # Process queued jobs one by one
                for job in queued_jobs:
                    logger.info(f"Processing queued job {job.id}")
                    await self.run_job(job.id)
                    await asyncio.sleep(1)  # Small delay between jobs
                    
            except Exception as e:
                logger.error(f"Error in queue processor: {e}")
                await asyncio.sleep(10)  # Wait before retrying

    async def _try_pdf_passthrough(self, job_id: int, pdf_path: str) -> bool:
        """Skip PDF passthrough - Zebra printers need ZPL, not raw PDF."""
        logger.info(f"Skipping PDF passthrough (Zebra printers require ZPL format)")
        return False

    async def _send_zpl_direct(self, job_id: int):
        """Send ZPL file directly to printer without any conversion (lossless)."""
        try:
            zpl_path = f"/app/data/{job_id}.zpl"
            
            if not os.path.exists(zpl_path):
                self.update_job_status(job_id, "FAILED", "ZPL file not found")
                return
            
            # Read ZPL file as binary (preserve exact format)
            with open(zpl_path, "rb") as f:
                zpl_content = f.read()
            
            # Send directly to printer
            logger.info(f"Sending ZPL directly to printer at {self.printer_ip}:{self.printer_port}")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            try:
                sock.connect((self.printer_ip, self.printer_port))
                sock.sendall(zpl_content)  # Send as binary (lossless)
                logger.info(f"ZPL sent successfully to {self.printer_ip}:{self.printer_port}")
            finally:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except:
                    pass
                sock.close()
            
            self.update_job_status(job_id, "PRINTING", f"ZPL sent to {self.printer_ip}:{self.printer_port}")
            await asyncio.sleep(2)
            self.update_job_status(job_id, "COMPLETED", "Print job completed (Direct ZPL).")
        except Exception as e:
            logger.error(f"Direct ZPL send error: {str(e)}")
            self.update_job_status(job_id, "FAILED", f"Direct ZPL send error: {str(e)}")

    async def _try_zpl_fallback(self, job_id: int, pdf_path: str):
        """Fall back to ZPL conversion and printing."""
        try:
            zpl_path = f"/app/data/{job_id}.zpl"
            
            # Convert PDF to ZPL if not already done
            if not os.path.exists(zpl_path):
                self.update_job_status(job_id, "CONVERTING", "Converting PDF to ZPL format...")
                with open(pdf_path, "rb") as f:
                    pdf_content = f.read()
                converter = LabelConverter()
                zpl_content = converter.convert_pdf_to_zpl(pdf_content, job_id=job_id)
                with open(zpl_path, "w") as f:
                    f.write(zpl_content)
                logger.info(f"ZPL file created: {zpl_path}, {len(zpl_content)} bytes")
            else:
                with open(zpl_path, "r") as f:
                    zpl_content = f.read()
                logger.info(f"Using cached ZPL file: {zpl_path}, {len(zpl_content)} bytes")
            
            # Send ZPL to printer
            logger.info(f"Sending ZPL to printer at {self.printer_ip}:{self.printer_port}")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            try:
                sock.connect((self.printer_ip, self.printer_port))
                sock.sendall(zpl_content.encode('utf-8'))  # Prints the label
                logger.info(f"ZPL sent successfully to {self.printer_ip}:{self.printer_port}")
            finally:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except:
                    pass
                sock.close()
            
            self.update_job_status(job_id, "PRINTING", f"ZPL sent to {self.printer_ip}:{self.printer_port}")
            await asyncio.sleep(2)
            self.update_job_status(job_id, "COMPLETED", "Print job completed (ZPL mode).")
        except Exception as e:
            logger.error(f"ZPL fallback error: {str(e)}")
            self.update_job_status(job_id, "FAILED", f"ZPL fallback error: {str(e)}")

class EmailPoller:
    """
    Polls Yahoo Mail inbox for PDF attachments and creates print jobs.
    """
    def __init__(self):
        self._running = True

    async def start(self):
        logger.info("Email Poller started.")
        while self._running:
            try:
                await self.poll()
            except Exception as e:
                logger.error(f"Email Poller Error: {e}")
            # Read scan_interval from settings each loop
            from app.database import SessionLocal, Settings
            db = SessionLocal()
            settings = db.query(Settings).first()
            db.close()
            interval = settings.scan_interval if settings else 60
            await asyncio.sleep(interval)

    def stop(self):
        """Stop the email polling loop."""
        self._running = False
        logger.info("Email Poller stopped.")

    async def poll(self):
        """Poll Yahoo Mail for eBay shipping label PDFs."""
        from app.database import SessionLocal, Settings, Job
        
        db = SessionLocal()
        settings = db.query(Settings).first()
        db.close()
        
        # Check if polling is explicitly enabled
        if not settings or not settings.email_polling_enabled:
            logger.debug("Email polling disabled - skipping")
            return {"status": "skipped", "reason": "Email polling not enabled"}
        
        if not settings.email_user or not settings.email_pass:
            logger.debug("Email poller skipped: credentials not configured")
            return {"status": "failed", "reason": "Email credentials not configured"}  # No email config
        
        try:
            # Connect to Yahoo IMAP
            logger.debug(f"[POLL] Connecting to Yahoo IMAP for {settings.email_user}...")
            imap = imaplib.IMAP4_SSL("imap.mail.yahoo.com", 993)
            imap.login(settings.email_user, settings.email_pass)
            logger.debug(f"[POLL] Authenticated as {settings.email_user}")
            imap.select("INBOX")
            
            # Search for unseen emails (we mark as read after processing)
            # Search for unseen emails that match basic criteria WITHOUT fetching them yet
            # This prevents marking unrelated emails as read
            from_filter = f'FROM "{settings.email_filter_from}"'
            subject_filter = f'SUBJECT "{settings.email_filter_subject}"'
            
            # Search for emails matching BOTH from AND subject (case-insensitive)
            status, messages = imap.search(None, 'UNSEEN', 'FROM', settings.email_filter_from)
            
            if status == 'OK':
                email_ids = messages[0].split()
                logger.info(f"[POLL] Found {len(email_ids)} unseen emails from {settings.email_filter_from}")
                
                for email_id in email_ids[-10:]:  # Process last 10 matching unseen emails
                    status, msg_data = imap.fetch(email_id, "(RFC822)")
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            
                            # Check subject
                            subject = msg.get("Subject", "").lower()
                            if settings.email_filter_subject.lower() not in subject:
                                logger.debug(f"Rejected email - subject '{subject}' missing: '{settings.email_filter_subject}'")
                                continue
                            
                            # Check body
                            body_text = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    content_type = part.get_content_type()
                                    if content_type == "text/plain":
                                        try:
                                            body_text += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                        except:
                                            pass
                                    elif content_type == "text/html":
                                        try:
                                            body_text += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                        except:
                                            pass
                            else:
                                try:
                                    body_text = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                                except:
                                    body_text = msg.get_payload()
                            
                            if settings.email_filter_body.lower() not in body_text.lower():
                                logger.debug(f"Rejected email - body missing: '{settings.email_filter_body}'")
                                continue
                            
                            logger.info(f"✅ Email passed all filters - creating print job")
                            
                            # All checks passed - extract FIRST PDF attachment only
                            pdf_found = False
                            for part in msg.walk():
                                if part.get_content_disposition() == "attachment":
                                    filename = part.get_filename()
                                    if filename and filename.lower().endswith(".pdf") and not pdf_found:
                                        pdf_data = part.get_payload(decode=True)
                                        pdf_found = True
                                        
                                        # Create print job
                                        db = SessionLocal()
                                        job = Job(
                                            filename=filename,
                                            source="Email (eBay Shipping Label)",
                                            status="READY"
                                        )
                                        db.add(job)
                                        db.commit()
                                        db.refresh(job)
                                        job_id = job.id
                                        db.close()
                                        
                                        # Save PDF
                                        pdf_path = f"/app/data/{job_id}.pdf"
                                        with open(pdf_path, "wb") as f:
                                            f.write(pdf_data)
                                        
                                        # Pre-generate ZPL
                                        converter = LabelConverter()
                                        zpl_content = converter.convert_pdf_to_zpl(pdf_data, job_id=job_id)
                                        zpl_path = f"/app/data/{job_id}.zpl"
                                        with open(zpl_path, "w") as f:
                                            f.write(zpl_content)
                                        
                                        logger.info(f"eBay label job created: {job_id} ({filename})")
                                        
                                        # Mark email as read so we don't process it again
                                        imap.store(email_id, '+FLAGS', '\\Seen')
                                        
                                        # Start printing
                                        mgr = PrinterManager()
                                        asyncio.create_task(mgr.run_job(job_id))
                                        break  # Only process first PDF, ignore others
                            
                            if not pdf_found:
                                logger.warning(f"Valid eBay email but no PDF attachment found")
            
            imap.close()
            imap.logout()
            return {"status": "success", "message": "Email poll completed"}
            
        except Exception as e:
            logger.error(f"Email poll error: {e}")
            return {"status": "failed", "reason": str(e)}

def convert_pdf_to_zpl(pdf_bytes: bytes) -> str:
    """Legacy compatibility function."""
    return LabelConverter().convert_pdf_to_zpl(pdf_bytes)
