from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from app.encryption import encrypt_value, decrypt_value
import secrets

DATABASE_URL = "sqlite:///./data/printer.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Settings(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True, index=True)
    # Printer
    printer_ip = Column(String, default="192.168.1.111")
    printer_port = Column(Integer, default=9100)
    # Email
    email_enabled = Column(Boolean, default=False)
    imap_server = Column(String, default="imap.mail.yahoo.com")
    email_user = Column(String, default="")
    _email_pass = Column("email_pass", String, default="")  # Encrypted storage
    scan_interval = Column(Integer, default=60)
    # Email Filters (Configurable)
    email_filter_from = Column(String, default="ebay@ebay.com")
    email_filter_subject = Column(String, default="label")
    email_filter_body = Column(String, default="your shipping label is ready")
    # eBay API
    ebay_enabled = Column(Boolean, default=False)
    _ebay_app_id = Column("ebay_app_id", String, default="")  # Encrypted
    _ebay_cert_id = Column("ebay_cert_id", String, default="")  # Encrypted
    _ebay_user_token = Column("ebay_user_token", String, default="")  # Encrypted
    _ebay_refresh_token = Column("ebay_refresh_token", String, default="")  # Encrypted
    ebay_token_expiration = Column(DateTime, default=None)
    ebay_last_check = Column(DateTime, default=None)
    # Smart Plug
    smart_plug_enabled = Column(Boolean, default=False)
    smart_plug_webhook = Column(String, default="") # URL to trigger plug ON
    smart_plug_off_webhook = Column(String, default="") # URL to trigger plug OFF
    shutdown_delay = Column(Integer, default=5) # Minutes
    # eBay Webhooks
    ebay_webhook_enabled = Column(Boolean, default=False)
    _ebay_webhook_secret = Column("ebay_webhook_secret", String, default="")  # Encrypted
    ebay_webhook_url = Column(String, default="")  # Public URL where eBay sends events
    ebay_webhook_registered = Column(DateTime, default=None)  # When webhook was registered with eBay

    @property
    def email_pass(self) -> str:
        """Decrypt and return the email password."""
        return decrypt_value(self._email_pass)
    
    @email_pass.setter
    def email_pass(self, value: str):
        """Encrypt and store the email password."""
        self._email_pass = encrypt_value(value) if value else ""

    @property
    def ebay_app_id(self) -> str:
        """Decrypt and return the eBay app ID."""
        return decrypt_value(self._ebay_app_id)
    
    @ebay_app_id.setter
    def ebay_app_id(self, value: str):
        """Encrypt and store the eBay app ID."""
        self._ebay_app_id = encrypt_value(value) if value else ""

    @property
    def ebay_cert_id(self) -> str:
        """Decrypt and return the eBay cert ID."""
        return decrypt_value(self._ebay_cert_id)
    
    @ebay_cert_id.setter
    def ebay_cert_id(self, value: str):
        """Encrypt and store the eBay cert ID."""
        self._ebay_cert_id = encrypt_value(value) if value else ""

    @property
    def ebay_user_token(self) -> str:
        """Decrypt and return the eBay user token."""
        return decrypt_value(self._ebay_user_token)
    
    @ebay_user_token.setter
    def ebay_user_token(self, value: str):
        """Encrypt and store the eBay user token."""
        self._ebay_user_token = encrypt_value(value) if value else ""

    @property
    def ebay_refresh_token(self) -> str:
        """Decrypt and return the eBay refresh token."""
        return decrypt_value(self._ebay_refresh_token)
    
    @ebay_refresh_token.setter
    def ebay_refresh_token(self, value: str):
        """Encrypt and store the eBay refresh token."""
        self._ebay_refresh_token = encrypt_value(value) if value else ""

    @property
    def ebay_webhook_secret(self) -> str:
        """Decrypt and return the eBay webhook secret."""
        return decrypt_value(self._ebay_webhook_secret)
    
    @ebay_webhook_secret.setter
    def ebay_webhook_secret(self, value: str):
        """Encrypt and store the eBay webhook secret."""
        self._ebay_webhook_secret = encrypt_value(value) if value else ""
    
    def generate_webhook_secret(self) -> str:
        """Generate and store a new webhook secret (256-bit = 32 bytes)."""
        secret = secrets.token_urlsafe(32)
        self.ebay_webhook_secret = secret
        return secret

class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    source = Column(String) # "EMAIL" or "WEB" or "EBAY_WEBHOOK"
    status = Column(String, default="PENDING") # PENDING, PRINTING, COMPLETED, ERROR
    log = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)
    zpl_content = Column(Text, default="")

class WebhookEvent(Base):
    """Track all webhook events for debugging and idempotency."""
    __tablename__ = "webhook_events"
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String, unique=True, index=True)  # eBay event ID for idempotency
    event_type = Column(String)  # "LABEL_DOWNLOADED", "FULFILLMENT_READY", etc.
    order_id = Column(String)
    shipment_id = Column(String)
    payload = Column(Text)  # Full JSON payload for debugging
    status = Column(String, default="RECEIVED")  # RECEIVED, PROCESSING, COMPLETED, FAILED
    job_id = Column(Integer, ForeignKey("jobs.id"), default=None)  # Linked job record
    error_message = Column(Text, default="")
    received_at = Column(DateTime, default=datetime.now)
    processed_at = Column(DateTime, default=None)

def init_db():
    Base.metadata.create_all(bind=engine)
    # Seed default settings if not exist
    db = SessionLocal()
    if not db.query(Settings).first():
        db.add(Settings())
        db.commit()
    db.close()
