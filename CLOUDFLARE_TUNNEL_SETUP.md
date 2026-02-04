# Cloudflare Tunnel Setup - Quick Reference

## What You Have & What to Do With It

The command Cloudflare gave you:
```bash
docker run cloudflare/cloudflared:latest tunnel --no-autoupdate run --token [redacted]
```

This is now **automatically integrated** into your `docker-compose.yml`. You don't need to run it manually.

---

## Quick Setup (5 Steps)

### 1. Edit .env File
```bash
# In /zpl-print-server/
# Create file: .env
# Add this line (replace with your actual token):
CLOUDFLARE_TUNNEL_TOKEN=[your-token-here]
```

**Get your token from Cloudflare Dashboard:**
- Go to https://dash.cloudflare.com/
- Click **Zero Trust** → **Networks** → **Tunnels**
- Find **zpl-print-server** tunnel
- Click **Configure**
- Copy the token from the instructions

### 2. Restart Docker
```bash
cd ~/zpl-print-server
docker compose down
docker compose up --build -d
```

### 3. Verify Tunnel Started
```bash
docker compose logs -f cloudflare-tunnel
```

Wait for this message:
```
2026-02-02T12:34:56Z INF Tunnel running at https://zpl-print-server-xxxxx.cfargotunnel.com
```

Press `Ctrl+C` to exit logs.

### 4. Configure Public Hostname in Cloudflare
In Cloudflare Dashboard:
- Go to your tunnel: **Tunnels** → **zpl-print-server** → **Configure**
- Click **+ Add a public hostname**
- Fill in:
  - **Subdomain:** `webhooks`
  - **Domain:** `yourdomain.com` or `cfargotunnel.com`
  - **Type:** `HTTP`
  - **URL:** `zpl-service:8000`
- Click **Save**

Result: Your webhook URL is `https://webhooks.yourdomain.com/webhooks/ebay`

### 5. Test It Works
```bash
curl https://webhooks.yourdomain.com/

# Should show your ZPL Print Server homepage (HTML)
```

---

## What Changed in Your Setup

### docker-compose.yml Changes
- ✅ Port binding changed: `0.0.0.0:8000` → `127.0.0.1:8000`
  - Now only accessible locally, not from network
- ✅ Added `cloudflare-tunnel` service
  - Automatically starts with ZPL server
  - Uses token from `.env`
- ✅ Added `zpl-network` bridge network
  - Connects both containers securely

### Security Improvements
- ✅ NAS IP never exposed to internet
- ✅ Zero open ports on firewall
- ✅ Cloudflare DDoS protection
- ✅ All traffic encrypted (HTTPS)
- ✅ Tunnel initiated from NAS (outbound only)
- ✅ Other services completely isolated

---

## Webhook URL in Settings

The URL is automatically populated in **🔔 Webhooks** tab:
- Shows: `https://webhooks.yourdomain.com/webhooks/ebay`
- This is the URL to give to eBay
- You can copy it with the **📋 Copy** button

---

## Troubleshooting

### Tunnel Won't Start
```bash
# Check logs
docker compose logs cloudflare-tunnel

# Common issue: Wrong token in .env
# Fix: Update .env with correct token, then:
docker compose restart cloudflare-tunnel
```

### Can't Access Webhook URL
```bash
# Test the tunnel
curl https://webhooks.yourdomain.com/

# If connection refused:
# - Verify ZPL service is running: docker compose ps
# - Check Cloudflare dashboard shows "Healthy"
# - Wait 30 seconds for DNS to propagate
```

### Cloudflare Dashboard Status
Go to https://dash.cloudflare.com/:
- **Zero Trust** → **Networks** → **Tunnels** → **zpl-print-server**
- Should show: **Status: Healthy** ✅

---

## Files to Know

| File | Purpose | Action |
|------|---------|--------|
| `.env` | Cloudflare token | **Create this with your token** |
| `.env.cloudflare` | Template | Reference only |
| `docker-compose.yml` | Docker config | Already updated ✅ |
| `WEBHOOK_INTEGRATION.md` | Full docs | Read for details |

---

## Key Points to Remember

1. **Token in `.env`** - Never commit to git, keep private
2. **Port binding** - Now `127.0.0.1:8000` (local only), good for security
3. **Both containers** - ZPL server + Cloudflare tunnel run together
4. **Automatic tunnel** - Starts with docker compose, no manual commands
5. **Your NAS stays safe** - Zero internet exposure, other services protected

---

## Next: eBay Webhook Configuration

Once tunnel is verified working, follow these steps in eBay Developer Console:

1. Go to https://developer.ebay.com/
2. Navigate to **Notification Preferences**
3. Add subscription with:
   - **Delivery URL:** `https://webhooks.yourdomain.com/webhooks/ebay`
   - **Event Type:** `FULFILLMENT.LABEL_DOWNLOADED`
   - **Signature Method:** HMAC-SHA256
   - **Signature Key:** (your webhook secret from ZPL settings)
4. Save and test

---

## Questions?

Refer to **WEBHOOK_INTEGRATION.md** for:
- Detailed architecture
- Security features explained
- Complete troubleshooting guide
- API endpoint reference
- Production monitoring tips

All your NAS ports stay closed. eBay reaches you safely through Cloudflare tunnel. Perfect! 🎉
