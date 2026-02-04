"""
Encryption utilities for sensitive database fields.
Uses Fernet (symmetric encryption) from the cryptography library.
"""
import os
from cryptography.fernet import Fernet

# Generate or load encryption key from environment
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    # Try to load from .env file
    env_file = "/app/.env"
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("ENCRYPTION_KEY="):
                    ENCRYPTION_KEY = line.split("=", 1)[1]
                    os.environ["ENCRYPTION_KEY"] = ENCRYPTION_KEY
                    break
    
    # If still not found, generate and save it
    if not ENCRYPTION_KEY:
        ENCRYPTION_KEY = Fernet.generate_key().decode()
        os.environ["ENCRYPTION_KEY"] = ENCRYPTION_KEY
        
        # Persist the key to .env file
        try:
            with open(env_file, "a") as f:
                f.write(f"ENCRYPTION_KEY={ENCRYPTION_KEY}\n")
            print(f"✅ Generated and saved ENCRYPTION_KEY to .env")
        except Exception as e:
            print(f"⚠️  Could not save ENCRYPTION_KEY to .env: {e}")
    else:
        print(f"✅ Loaded ENCRYPTION_KEY from .env")

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
