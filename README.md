# ZPL Print Server

A FastAPI-based web server that converts PDF documents to ZPL (Zebra Programming Language) format and manages print jobs to Zebra label printers. Features email polling for automatic job processing and smart plug integration for printer power management.

## Features

- **PDF to ZPL Conversion**: Automatically converts uploaded PDF files to Zebra printer-compatible ZPL format
- **Web Interface**: Clean, responsive web UI for uploading files and monitoring print jobs
- **Email Integration**: Polls email inbox for attachments and automatically converts them to print jobs
- **Print Job Management**: Database-backed job tracking with status monitoring and logging
- **Smart Plug Integration**: Supports TP-Link smart plugs for automated printer power control
- **RESTful API**: Comprehensive API endpoints for programmatic access
- **Containerized**: Docker support for easy deployment

## Prerequisites

- Python 3.11+
- Docker (optional, for containerized deployment)
- Zebra printer with network connectivity
- Email account (for email polling feature)
- Smart plug (optional, for power management)

## Installation

### Local Development

1. Clone the repository:
```bash
git clone <repository-url>
cd zpl-print-server
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
uvicorn app.main:app --reload
```

The web server will start at `http://localhost:8000`

### Docker Deployment

1. Build the Docker image:
```bash
docker build -t zpl-print-server .
```

2. Run the container:
```bash
docker run -p 8000:8000 \
  -v zpl-data:/app/data \
  zpl-print-server
```

## Configuration

Configure the application through the web interface at `http://localhost:8000`:

- **Printer IP**: Network address of your Zebra printer
- **Email Settings**: Email username and password for SMTP polling
- **Smart Plug**: Enable/disable smart plug control and set webhook URLs

## API Endpoints

### Web Interface
- `GET /` - Home page with job history and settings
- `POST /upload` - Upload PDF file for conversion and printing
- `POST /settings` - Update application settings
- `GET /api/jobs` - Retrieve recent print jobs (JSON)

## Project Structure

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

## Environment Setup

The application uses a SQLite database for persistent storage. Database files are stored in `/app/data/`.

## Running Print Jobs

### Manual Upload
Upload PDF files directly through the web interface at `/`

### Email Integration
The email poller automatically:
1. Checks configured email account
2. Downloads PDF attachments
3. Converts to ZPL format
4. Creates print jobs

### API Upload
Send PDF files programmatically to `/upload` endpoint

## Smart Plug Integration

The server supports smart plug control via webhooks:
- **TP-Link Kasa Plugs**: Direct local control
- **Amazon/Other Plugs**: Webhook-based control

Configure webhook URLs in settings for automated printer power management.

## Troubleshooting

- **PDF Conversion Fails**: Ensure `poppler-utils` is installed
- **Printer Connection**: Verify printer IP is accessible via ping
- **Email Not Polling**: Check email credentials and SMTP settings in UI
- **Docker Persistence**: Use volume mounting to preserve database between restarts

