# ZPL Print Server

A FastAPI web server that converts PDF documents to ZPL (Zebra Programming Language) format and manages print jobs to Zebra thermal printers. Features intelligent job queueing, email automation, and a modern dark/light theme UI.

## ✨ Features

- **📄 Universal File Upload**: Auto-detects PDF or ZPL files via drag-and-drop or file picker
- **🔄 PDF to ZPL Conversion**: High-quality conversion using PyMuPDF with adaptive thresholding
- **🌐 Modern Web Interface**: Responsive dark/light theme UI with real-time job monitoring
- **📧 Email Automation**: Polls Yahoo Mail for eBay shipping labels and auto-prints them
- **📋 Job Queue System**: Automatic queueing when printer offline, auto-processes when online
- **❌ Job Cancellation**: Cancel queued jobs before they print
- **🖼️ Live Previews**: PNG preview generation for all ZPL labels
- **🔒 Security Hardened**: File type validation, size limits, AES password encryption
- **💾 Database Tracking**: SQLite-backed job history with status logging
- **🔌 Smart Plug Support**: Optional TP-Link smart plug integration (untested)
- **🏥 Health Monitoring**: `/health` endpoint for container orchestration
- **🐳 Docker Ready**: Optimized container with resource limits

## 📋 Prerequisites

- **Docker & Docker Compose** (recommended deployment method)
- **Zebra Thermal Printer** with network connectivity (tested on GX420t, port 9100)
- **Optional**: Yahoo Mail account (for email automation)
- **Optional**: TP-Link smart plug (for power management - untested)

## 🚀 Quick Start (Docker)

### 1. Deploy Container

```bash
git clone <repository-url>
cd zpl-print-server
docker compose up -d
```

The server starts at **http://localhost:8000**

### 2. First-Time Setup

On first startup, the system automatically:
- ✅ Generates AES encryption key (stored in `.env`)
- ✅ Initializes SQLite database (`data/printer.db`)
- ✅ Shows yellow banner in UI confirming setup

**⚠️ Important**: Backup the `.env` file - it's needed to decrypt saved email passwords!

### 3. Configure Printer

1. Open **http://localhost:8000**
2. Click **⚙️ Settings** button
3. Enter your printer's IP address (e.g., `192.168.1.111`)
4. Click **Save Settings**
5. Verify green checkmark for printer connectivity

You're ready to print! 🎉

---

## 💻 Alternative: Local Development

If you prefer running without Docker:
⚙️ Configuration

All settings are managed through the web UI at **http://localhost:8000**

### Printer Settings
- **Printer IP Address**: Local network IP of your Zebra printer (e.g., `192.168.1.111`)
- **Printer Port**: Default is `9100` (Zebra standard)
- **Status Check**: Live connectivity indicator

### Email Automation (Optional)
1. **Enable Email Polling**: Toggle checkbox to activate
2. **Yahoo Email**: Your Yahoo Mail address
3. **App Password**: Generate one at [Yahoo Security Settings](https://login.yahoo.com/account/security)
4. **Scan Interval**: How often to check (minimum 10 seconds)
5. **Email Filters**: Configure sender, subject, and body text filters

### Advanced Settings
- **Smart Plug Integration**: Configure webhooks for TP-Link plugs (untested)
- **Timezone**: Set via `TZ` environment variable in `docker-compose.yml`

---

## 📡 API Endpoints

### Core Endpoints
- `GET /` - Web UI home page with job table
- `GET /help` - Comprehensive FAQ and documentation
- `📁 Project Structure

```
zpl-print-server/
├── app/
│   ├── main.py              # FastAPI app, routes, file handling
│   ├── database.py          # SQLAlchemy models (Settings, Job)
│   ├── services.py          # PrinterManager, EmailPoller, LabelConverter
│   ├── encryption.py        # AES encryption for passwords
│   └── templates/
│       ├── index.html       # Main UI with drag-drop upload
│       └── help.html        # FAQ and documentation
├── data/                    # SQLite DB and uploaded files (persisted)
├── docker-compose.yml       # Container orchestration
├── Dockerfile              # Python 3.12-slim container
├── requirements.txt        # Python dependencies
├── SECURITY_AUDIT.md       # Security review and recommendations
└── DEPLOYMENT_GUIDE.md     # Production deployment checklist
```

## 🔧 Core Dependencies

- **FastAPI** `0.109.0` - Modern async web framework
- **SQLAlchemy** `2.0.25` - Database ORM with connection pooling
- **PyMuPDF** `1.23.22` - High-quality PDF rendering and conversion
- **Pillow** `10.2.0` - Image processing and manipulation
- **cryptography** `41.0.7` - AES encryption (Fernet) for passwords
- **uvicorn** `0.27.0` - ASGI web server
- **Jinja2** `3.1.3` - Template rendering
- **numpy** `1.26.3` - Image array processing

### Container Environment
- **Base Image**: `python:3.12-slim`
- **System Packages**: `libzbar0`, `poppler-utils`
- **Data Persistence**: `/app/data` volume mount
- **Resource Limits**: 512MB RAM, 0.5 CPU
```
zpl-print-server/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application and routes
│   ├── config.py            # Configuration management
│   ├── database.py          # SQLAlchemy models and database setup
│   ├── services.py          # Print management and PDF conversion
│   ├── templates/
│   │   └── index.html       # Web UI template
│   └── static/              # Static assets
├── requirements.txt         # Python dependencies
├── Dockerfile              # Docker configuration
└── README.md              # This file
```

## Dependencies

- **fastapi** - Modern Python web framework
- **uvicorn** - ASGI web server
- **sqlalchemy** - ORM and database toolkit
- **pdf2image** - PDF to image conversion
- **Pillow** - Image processing
- **python-kasa** - TP-Link smart plug control
- **jinja2** - Template engine
🖨️ How It Works

### Job Processing Flow

1. **Upload**: Drag PDF/ZPL file to web UI or upload via API
2. **Detection**: Server auto-detects file type based on content
3. **Conversion** (PDF only): Converts to ZPL using PyMuPDF at 203 DPI
4. **Preview**: Generates PNG preview for verification
5. **Queue**: Job marked "READY" and queued for printing
6. **Print**: Sends ZPL directly to printer via raw TCP socket (port 9100)
7. **Status**: Updates to "COMPLETED" or "FAILED" with detailed logs

### Job Queue Behavior

- **Printer Online**: Jobs print immediately
- **Printer Offline**: Jobs automatically queue with "QUEUED" status
- **Auto-Resume**: Queue processor checks every 10 seconds, auto-prints when printer returns
- **Cancellation**: Click red ❌ button to cancel queued jobs

### Email Automation (Optional)

When enabled, the server:
1. Polls Yahoo Mail every 60 seconds (configurable)
2. Filters emails by sender, subject, and body text
3. Downloads first PDF attachment from matching emails
4. Converts to ZPL and queues for printing
5. Marks email as read to prevent reprocessing

**Perfect for**: Auto-printing eBay shipping labels from `ebay@ebay.com` emails

---

## 🔒 Security Features

- ✅ **File Upload Limits**: 2MB maximum (configurable via `MAX_FILE_SIZE_MB`)
- ✅ **File Type Validation**: Only `.pdf`, `.zpl`, `.txt` allowed
- ✅ **Path Traversal Protection**: Job ID validation on all endpoints
- ✅ **Password Encryption**: AES (Fernet) encryption for email passwords
- ✅ **SQL Injection Prevention**: SQLAlchemy ORM with parameterized queries
- ✅ **Connection Pooling**: Prevents database connection leaks
- ✅ **Error Sanitization**: No internal details exposed in error messages

### Production Recommendations
- Add rate limiting for `/upload` endpoint (see `SECURITY_AUDIT.md`)
- Deploy behind HTTPS reverse proxy (Nginx/Traefik)
- Configure firewall rules for printer port access
- Regular backups of `data/` directory and `.env` file

---

## 🛠️ Troubleshooting

### Printer Connection Issues
```bash
# Test printer connectivity
ping 192.168.1.111

# Check if port 9100 is open
nc -zv 192.168.1.111 9100

# View logs
docker compose logs -f
```

### Email Polling Not Working
1. Verify Yahoo Mail credentials in Settings
2. Generate app-specific password (not your Yahoo password!)
3. Enable polling toggle in Email tab
4. Check logs: `docker compose logs -f | grep Email`
5. Test manually via "Test Email Connection" button

### Jobs Stuck in QUEUED Status
- Verify printer IP is correct in Settings
- Check printer is powered on and connected to network
- Printer must be on same network as server
- Queue processor checks every 10 seconds automatically

### Database Corruption
```bash
# Backup current database
cp data/printer.db data/printer.db.backup

# Rebuild from scratch
rm data/printer.db
docker compose restart
```

### Container Won't Start
```bash
# Check logs for errors
docker compose logs

# Rebuild from scratch
docker compose down
docker compose build --no-cache
docker compose up -d
```

---

## 📊 Monitoring

### Health Check Endpoint
```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "service": "zpl-print-server",
  "timestamp": "2026-02-04T12:00:00.123456"
}
```

### Docker Health Check
Add to `docker-compose.yml`:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 3s
  retries: 3
  start_period: 5s
```

### Log Monitoring
```bash
# Follow logs in real-time
docker compose logs -f

# Last 100 lines
docker compose logs --tail=100

# Filter by service
docker compose logs zpl-service
```

---

## 📚 Additional Documentation

- **Help Page** - Access at `http://localhost:8000/help` for in-app documentation

---

## 🤝 Contributing

This is a personal project, but suggestions and improvements are welcome!

---

## 📄 License

See repository for license information.

---

## 🎯 Tested Configuration

- **Printer**: Zebra GX420t thermal printer (4x6" labels at 203 DPI)
- **Platform**: Docker on macOS ARM64 (M1/M2)
- **Network**: Local LAN with static printer IP
- **Email**: Yahoo Mail with app-specific password
- **Production**: Security hardened and ready for deployment

- **PDF Conversion Fails**: Ensure `poppler-utils` is installed
- **Printer Connection**: Verify printer IP is accessible via ping
- **Email Not Polling**: Check email credentials and SMTP settings in UI
- **Docker Persistence**: Use volume mounting to preserve database between restarts

