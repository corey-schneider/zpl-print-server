from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from app.encryption import encrypt_value, decrypt_value

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
    email_polling_enabled = Column(Boolean, default=False)  # User must explicitly enable polling
    imap_server = Column(String, default="imap.mail.yahoo.com")
    email_user = Column(String, default="")
    _email_pass = Column("email_pass", String, default="")  # Encrypted storage
    scan_interval = Column(Integer, default=60)
    # Email Filters (Configurable)
    email_filter_from = Column(String, default="ebay@ebay.com")
    email_filter_subject = Column(String, default="label")
    email_filter_body = Column(String, default="your shipping label is ready")
    # Smart Plug
    smart_plug_enabled = Column(Boolean, default=False)
    smart_plug_webhook = Column(String, default="") # URL to trigger plug ON
    smart_plug_off_webhook = Column(String, default="") # URL to trigger plug OFF
    shutdown_delay = Column(Integer, default=5) # Minutes

    @property
    def email_pass(self) -> str:
        """Decrypt and return the email password."""
        return decrypt_value(self._email_pass)
    
    @email_pass.setter
    def email_pass(self, value: str):
        """Encrypt and store the email password."""
        self._email_pass = encrypt_value(value) if value else ""

class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    source = Column(String) # "EMAIL" or "WEB"
    status = Column(String, default="PENDING") # PENDING, PRINTING, COMPLETED, ERROR
    log = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)
    zpl_content = Column(Text, default="")

def init_db():
    Base.metadata.create_all(bind=engine)
    # Seed default settings if not exist
    db = SessionLocal()
    if not db.query(Settings).first():
        db.add(Settings())
        db.commit()
    db.close()
