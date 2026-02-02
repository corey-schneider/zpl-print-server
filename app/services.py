import asyncio
import logging
import socket
import binascii
import imaplib
import email
import requests
import time
from email.header import decode_header
from pdf2image import convert_from_bytes
from PIL import Image, ImageOps
from app.database import SessionLocal, Job, Settings
from datetime import datetime

logger = logging.getLogger("PrintServer")

# --- 1. PDF TO ZPL CONVERTER ---
def convert_pdf_to_zpl(pdf_bytes: bytes, width_dots=812, height_dots=1218) -> str:
    """
    Renders PDF to a 203 DPI monochrome bitmap and encodes as ZPL ^GF.
    Standard 4x6 label at 203 DPI is approx 812x1218 dots.
    """
    try:
        images = convert_from_bytes(pdf_bytes, dpi=203)
        if not images:
            raise ValueError("No images found in PDF")
        
        # Take first page
        img = images[0].convert('L')
        # Resize/Fit
        img = ImageOps.fit(img, (width_dots, height_dots), method=Image.LANCZOS, centering=(0.5, 0.5))
        # Dither to 1-bit monochrome
        img = img.convert('1')
        
        # Get raw bytes
        data = img.tobytes()
        
        # Hex encode for ZPL
        hex_data = binascii.hexlify(data).decode().upper()
        total_bytes = len(data)
        bytes_per_row = width_dots // 8
        if width_dots % 8: bytes_per_row += 1
        
        return f"^XA^FO0,0^GFA,{total_bytes},{total_bytes},{bytes_per_row},{hex_data}^FS^XZ"
    except Exception as e:
        logger.error(f"Conversion Error: {e}")
        raise e

# --- 2. PRINTER MANAGER ---
class PrinterManager:
    async def run_job(self, job_id: int):
        db = SessionLocal()
        job = db.query(Job).filter(Job.id == job_id).first()
        settings = db.query(Settings).first()
        
        try:
            job.status = "PROCESSING"
            db.commit()
            self._log(job, "Starting Job processing.")

            # 1. Trigger Smart Plug ON
            if settings.smart_plug_enabled and settings.smart_plug_webhook:
                self._log(job, "Triggering Smart Plug ON...")
                try:
                    requests.get(settings.smart_plug_webhook, timeout=5)
                except Exception as e:
                    self._log(job, f"Smart Plug Error (Non-fatal): {e}")

            # 2. Network Check (Ping) if plug enabled
            if settings.smart_plug_enabled:
                self._log(job, f"Waiting for printer at {settings.printer_ip}...")
                online = await self._wait_for_printer(settings.printer_ip)
                if not online:
                    raise TimeoutError("Printer did not come online within timeout.")

            # 3. Send to Printer
            self._log(job, "Sending ZPL to printer...")
            reader, writer = await asyncio.open_connection(settings.printer_ip, settings.printer_port)
            writer.write(job.zpl_content.encode())
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            
            job.status = "COMPLETED"
            self._log(job, "Print job sent successfully.")

        except Exception as e:
            job.status = "ERROR"
            self._log(job, f"CRITICAL FAILURE: {str(e)}")
        finally:
            db.commit()
            db.close()
            # Schedule Off
            if settings.smart_plug_enabled:
                asyncio.create_task(self._delayed_shutdown(settings.shutdown_delay))

    async def _wait_for_printer(self, ip, timeout=120):
        start = time.time()
        while time.time() - start < timeout:
            proc = await asyncio.create_subprocess_exec(
                'ping', '-c', '1', '-W', '1', ip,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await proc.wait()
            if proc.returncode == 0:
                return True
            await asyncio.sleep(1.5) # Gentle polling
        return False

    async def _delayed_shutdown(self, minutes):
        logger.info(f"Scheduling shutdown in {minutes} minutes")
        await asyncio.sleep(minutes * 60)
        
        db = SessionLocal()
        settings = db.query(Settings).first()
        if settings.smart_plug_enabled and settings.smart_plug_off_webhook:
            try:
                requests.get(settings.smart_plug_off_webhook, timeout=5)
                logger.info("Smart Plug turned OFF via webhook.")
            except Exception as e:
                logger.error(f"Failed to turn off plug: {e}")
        db.close()

    def _log(self, job, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}\n"
        job.log = (job.log or "") + entry
        logger.info(f"Job {job.id}: {message}")

# --- 3. EMAIL POLLER ---
class EmailPoller:
    def __init__(self):
        self.running = False

    async def start(self):
        self.running = True
        logger.info("Email Poller Started")
        while self.running:
            try:
                await self.check()
            except Exception as e:
                logger.error(f"Email Poller Crashed: {e}")
            await asyncio.sleep(60) # Configurable in real impl, keeping simple here

    def stop(self):
        self.running = False

    async def check(self):
        db = SessionLocal()
        settings = db.query(Settings).first()
        
        if not settings.email_enabled or not settings.email_user:
            db.close()
            return

        # Run blocking IMAP in executor to not block asyncio loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._sync_imap, settings)
        db.close()

    def _sync_imap(self, settings):
        try:
            mail = imaplib.IMAP4_SSL(settings.imap_server)
            mail.login(settings.email_user, settings.email_pass)
            mail.select("inbox")
            
            # Search for Unseen emails with "label" in body
            status, messages = mail.search(None, '(UNSEEN BODY "label")')
            
            for num in messages[0].split():
                status, msg_data = mail.fetch(num, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])
                
                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart': continue
                    if part.get('Content-Disposition') is None: continue
                    
                    filename = part.get_filename()
                    if filename and filename.lower().endswith('.pdf'):
                        pdf_data = part.get_payload(decode=True)
                        
                        # Create Job
                        zpl = convert_pdf_to_zpl(pdf_data)
                        db = SessionLocal()
                        new_job = Job(filename=filename, source="EMAIL", zpl_content=zpl)
                        db.add(new_job)
                        db.commit()
                        
                        # Trigger Printer Manager (Fire and Forget)
                        mgr = PrinterManager()
                        asyncio.create_task(mgr.run_job(new_job.id))
                        db.close()
                        break # Only process first label per email
            
            mail.close()
            mail.logout()
        except Exception as e:
            logger.error(f"IMAP Error: {e}")
