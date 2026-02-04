"""
Encryption utilities for sensitive database fields.
Uses Fernet (symmetric encryption) from the cryptography library.
"""
import os
from cryptography.fernet import Fernet

# Generate or load encryption key from environment
# If not set, generate a default (for development only - should be set in production)
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    # Generate a new key for development
    ENCRYPTION_KEY = Fernet.generate_key().decode()
    print(f"⚠️  ENCRYPTION_KEY not set. Generated: {ENCRYPTION_KEY}")
    print("⚠️  Set the ENCRYPTION_KEY environment variable in production!")

cipher = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)

# Check if this is first-time setup (marker file created by entrypoint.sh)
IS_FIRST_RUN = os.path.exists("/app/data/.env.firstrun")


def encrypt_value(value: str) -> str:
    """Encrypt a string value."""
    if not value:
        return value
    return cipher.encrypt(value.encode()).decode()


def decrypt_value(value: str) -> str:
    """Decrypt an encrypted string value."""
    if not value:
        return value
    try:
        return cipher.decrypt(value.encode()).decode()
    except Exception as e:
        # If decryption fails, return empty string
        # This prevents showing encrypted gibberish in forms
        return ""
