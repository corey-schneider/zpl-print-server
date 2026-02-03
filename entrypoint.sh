#!/bin/bash
# Docker entrypoint script - handles startup tasks

set -e

# Check if .env exists, if not generate it
if [ ! -f ".env" ]; then
    echo "🔐 Generating encryption key for first-time setup..."
    
    # Generate the key
    ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    
    # Save to .env
    echo "ENCRYPTION_KEY=$ENCRYPTION_KEY" > .env
    
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
    echo "   • Back it up securely (it's in .env in the container)"
    echo "   • If lost, encrypted passwords cannot be recovered"
    echo "   • Keep it with your database backups"
    echo ""
    echo "The web UI will show more details on first load."
    echo ""
    
    # Create a flag file to indicate first-time setup
    touch .env.firstrun
else
    if [ -f ".env.firstrun" ]; then
        rm .env.firstrun
    fi
fi

# Start the application
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
