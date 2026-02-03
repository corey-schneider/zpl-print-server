#!/bin/bash
# Docker entrypoint script - handles startup tasks

set -e

# Check if .env exists in workspace, if not generate it
ENV_FILE="/app/.env"
MARKER_FILE="/app/data/.env.firstrun"

if [ ! -f "$ENV_FILE" ]; then
    echo "🔐 Generating encryption key for first-time setup..."
    
    # Generate the key
    ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    
    # Save to mounted .env location so it persists
    echo "ENCRYPTION_KEY=$ENCRYPTION_KEY" > "$ENV_FILE"
    
    echo "✅ Generated and saved to .env"
    echo ""
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║  🔐 ENCRYPTION KEY GENERATED - SAVE THIS SAFELY!           ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""
    echo "Key: $ENCRYPTION_KEY"
    echo ""
    echo "⚠️  IMPORTANT:"
    echo "   • This key encrypts your email passwords in the database"
    echo "   • Back it up securely (it's in .env in the project root)"
    echo "   • If lost, encrypted passwords cannot be recovered"
    echo "   • Keep it with your database backups"
    echo ""
    echo "The web UI will show more details on first load."
    echo ""
    
    # Create a flag file to indicate first-time setup
    mkdir -p /app/data
    touch "$MARKER_FILE"
else
    if [ -f "$MARKER_FILE" ]; then
        rm "$MARKER_FILE"
    fi
fi

# Start the application
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
