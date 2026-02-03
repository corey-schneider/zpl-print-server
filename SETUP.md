# ZPL Print Server Setup Guide

## Quick Start

### First Time Setup

Just run:

```bash
docker compose up -d --build
```

That's it! The system will:
- Automatically generate a secure encryption key
- Create a `.env` file to store it
- Initialize the database
- Start the server at `http://localhost:8000`

You'll see a yellow banner on first load confirming the key was generated.

## Security & Backups

### The Encryption Key

The system automatically generates and stores an encryption key in `.env` that encrypts your email passwords in the database.

**This file is critical:**
- ✅ **DO:** Keep `.env` with your database backups
- ❌ **DON'T:** Commit it to git or share it publicly
- ❌ **DON'T:** Use the same key across multiple deployments

### Backing Up Your Setup

```bash
# Back up both the key and database together
cp .env /secure/location/
cp data/printer.db /secure/location/
```

To restore on a new machine:
```bash
cp /secure/location/.env .
cp /secure/location/printer.db data/
docker compose up -d
```

**Important:** The `.env` key must match the database. Keep them together or passwords won't decrypt.

---

## Multiple Machines / Team Deployment

### Sharing Setup Instructions

Provide others with:
- The project code (no need to share `.env` or `data/`)
- Point them to the README - they just run `docker compose up -d --build`
- Each deployment gets its own encryption key automatically

### Moving to Another Machine (Same User)

1. Sync `.env` and `data/printer.db` together to the new machine
2. Run `docker compose up -d`
3. Everything works (passwords decrypt with the migrated key)

### Team Deployment (Shared Infrastructure)

For shared deployments on the same machine:
1. System generates one encryption key per deployment
2. Store `.env` securely (AWS Secrets Manager, Vault, etc.)
3. All users on that deployment share the same encryption

---

## Troubleshooting

**Q: Where is my encryption key?**
A: In `.env` in the project root. Back it up securely!

**Q: What if I lose the `.env` file?**
A: Your stored passwords cannot be recovered. To fix:
   1. Delete `data/printer.db`
   2. Run `docker compose up` (new key generated, fresh database)
   3. Re-enter your email credentials in Settings

**Q: Can I change the encryption key?**
A: Only by resetting the database (see above). Passwords encrypted with the old key won't decrypt with a new key.

**Q: Email login fails after restoring from backup**
A: Verify the `.env` key matches the database file. If using a different key, the passwords are encrypted with the wrong key and must be re-entered.

---

## Encryption Details

- **Algorithm:** Fernet (AES-128 with HMAC)
- **Encrypted Fields:** `email_pass` only  
- **Plaintext Fields:** printer IP, email address, scan interval, etc.
- **Key Generation:** Automatic on first startup
- **Key Storage:** `.env` file in project root

