# eBay Webhook Integration - Complete Guide

## Overview

Your ZPL Print Server now supports **enterprise-grade webhook integration** with eBay for fully automatic label printing. When you purchase a shipping label on eBay, it's automatically downloaded and sent to your printer within seconds—no manual clicks needed.

## ⚠️ Important: Network Security

**DO NOT expose port 8000 directly to the internet.** Instead, use **Cloudflare Tunnel** to:
- Keep your NAS completely hidden from the internet
- Route eBay webhooks through an encrypted tunnel
- Maintain zero open ports on your firewall
- Get free DDoS protection

This guide includes complete Cloudflare Tunnel setup instructions below.

---

## Architecture

### Security Features (Professional-Grade)

All webhook security follows industry best practices:

1. **HMAC-SHA256 Signature Verification**
   - Every webhook from eBay is cryptographically signed
   - Server verifies the signature using your webhook secret
   - Prevents spoofed or tampered requests from fake sources
   - Uses constant-time comparison to prevent timing attacks

2. **Timestamp Validation**
   - Webhook timestamp must be within 5 minutes of current time
   - Prevents replay attacks (old webhooks can't be replayed)
   - Automatically validated on every request

3. **Idempotency Protection**
   - Each webhook event has a unique `event_id` from eBay
   - Duplicate events are detected and ignored
   - If eBay retries a webhook, it's only processed once
   - Prevents duplicate label printing if network causes retries

4. **Encrypted Credential Storage**
   - Webhook secret is encrypted at rest in the database using Fernet (AES-128 HMAC)
   - Same encryption as email passwords—never stored in plaintext
   - Only decrypted when verifying incoming webhooks

### Event Flow

```
1. You purchase label on eBay website
   ↓
2. eBay API signs webhook with HMAC-SHA256 using your secret
   ↓
3. Webhook POST request sent to: https://your-server/webhooks/ebay
   ↓
4. Server verifies signature and timestamp
   ↓
5. Server checks if event was already processed (idempotency)
   ↓
6. If valid & new: Background task immediately fetches label from eBay
   ↓
7. PDF + ZPL saved to disk
   ↓
8. Job record created in database
   ↓
9. Automatic printer queue picks up job and prints
```

**Total time:** ~2-5 seconds from label purchase to printing (depending on network)

## Setup Instructions

### Step 0: Cloudflare Tunnel (Required - Keeps Your NAS Safe)

#### 0a. Create Cloudflare Tunnel

1. Go to https://dash.cloudflare.com/
2. Sign up for free account (if you don't have one)
3. Go to **Zero Trust** → **Networks** → **Tunnels**
4. Click **Create a tunnel**
5. Choose **Cloudflared** (the default)
6. Name it: `zpl-print-server`
7. Click **Save tunnel**
8. Copy the token (looks like: `ey...`)

#### 0b. Configure Tunnel Token

1. In your project directory, create/edit `.env` file:
```bash
CLOUDFLARE_TUNNEL_TOKEN=ey[paste-your-token-here]
```

2. **IMPORTANT:** This file contains your private token
   - Add `.env` to `.gitignore` (it should already be there)
   - Never commit it to git
   - Never share it with anyone

#### 0c. Verify Docker Setup

Your `docker-compose.yml` should now include the Cloudflare tunnel service. Check it has:
- `cloudflare-tunnel` service defined
- `zpl-network` network defined
- `CLOUDFLARE_TUNNEL_TOKEN` environment variable

If you need to update it manually:
```yaml
cloudflare-tunnel:
  image: cloudflare/cloudflared:latest
  container_name: zpl-cloudflare-tunnel
  restart: unless-stopped
  command: tunnel --no-autoupdate run --token ${CLOUDFLARE_TUNNEL_TOKEN}
  networks:
    - zpl-network
```

#### 0d. Start the Tunnel

```bash
cd ~/zpl-print-server
docker compose down
docker compose up --build -d
docker compose logs -f cloudflare-tunnel
```

Wait until you see a message like:
```
2026-02-02T12:34:56Z INF Tunnel running at https://zpl-print-server-xxxxx.cfargotunnel.com
```

That's your **tunnel URL** - eBay will send webhooks to this domain.

#### 0e. Configure Public Hostname in Cloudflare

1. Go back to https://dash.cloudflare.com/
2. Find your tunnel: **Zero Trust** → **Networks** → **Tunnels** → `zpl-print-server`
3. Click **Configure**
4. Under **Public Hostname**, click **Add a public hostname**
5. Fill in:
   - **Subdomain:** `webhooks` (or any name you want)
   - **Domain:** Select your domain (or use `cfargotunnel.com` for testing)
   - **Type:** `HTTP`
   - **URL:** `zpl-service:8000` (Docker container hostname)
6. Click **Save**

**Result:** Your webhook URL is now: `https://webhooks.yourdomain.com/webhooks/ebay`
(or `https://webhooks.yourname.cfargotunnel.com/webhooks/ebay` if using free tunnel domain)

#### 0f. Verify Tunnel is Working

```bash
# From your local machine, test the tunnel
curl -v https://webhooks.yourdomain.com/

# You should see your ZPL Print Server homepage
```

If it works, proceed. If not, check:
- `.env` file has correct token
- Cloudflare dashboard shows "Healthy" status
- Docker logs: `docker compose logs cloudflare-tunnel`

---

### Step 1: Generate Webhook Secret

In the **🔔 Webhooks** tab:
1. Click **🔑 Generate New Secret**
2. A 256-bit (32-byte) cryptographically secure secret is generated
3. The secret is encrypted and stored in your database
4. Copy it (but keep it private!)

### Step 2: Get Your Webhook URL

In the **🔔 Webhooks** tab:
1. Your webhook URL is automatically populated from Cloudflare Tunnel
2. It will show: `https://webhooks.yourdomain.com/webhooks/ebay`
3. This is the URL to give to eBay
4. Copy it with the **📋 Copy** button

> **Note:** This URL is now safe because:
> - Your real IP is never exposed
> - All traffic goes through Cloudflare's encrypted tunnel
> - Your NAS has zero open ports to the internet
> - DDoS protection is automatic

### Step 3: Register with eBay Developer Console

1. Go to [eBay Developer Console](https://developer.ebay.com/)
2. Navigate to **Keys & Tokens** → **Notification Preferences**
3. Click **Add New Subscription**
4. Configure:
   - **Delivery URL:** Paste your webhook URL
   - **Event Type:** Select `FULFILLMENT.LABEL_DOWNLOADED`
   - **Authentication:** Enable HMAC-SHA256 verification
   - **Signature Key:** Paste your webhook secret
5. Save and test

### Step 4: Enable in Settings

In the **🔔 Webhooks** tab:
1. Check **Enable eBay Webhooks (Automatic Printing)**
2. Verify webhook URL is populated (from Cloudflare)
3. Click **Save Settings**

### Step 5: Verify Webhooks

1. Go to **🔔 Webhooks** tab → **View Recent Events**
2. Once you purchase a label on eBay, it will appear within seconds
3. Check the status:
   - ✅ **COMPLETED** - Label downloaded and printed successfully
   - 🔴 **FAILED** - Check error message for troubleshooting
   - ⏳ **PROCESSING** - Currently fetching label

---

## Cloudflare Tunnel Troubleshooting

### Tunnel Status Check

```bash
# View tunnel logs
docker compose logs -f cloudflare-tunnel

# Look for messages like:
# INF Tunnel running at https://...
# INF +---+--+---+--+
# INF Metrics server running at http://127.0.0.1:7844
```

### Common Issues

**"Tunnel is not available"**
- Restart tunnel: `docker compose restart cloudflare-tunnel`
- Check token in `.env` is correct
- Verify Cloudflare dashboard shows "Healthy"

**"Can't reach webhooks.yourdomain.com"**
- Ensure you configured "Public Hostname" in Cloudflare dashboard
- Verify hostname points to `zpl-service:8000`
- Wait 30 seconds for DNS to propagate

**"Connection refused from Cloudflare"**
- ZPL service must be running: `docker compose ps`
- Both containers must be on same network: `docker network ls`
- Check firewall isn't blocking Docker networks

**Webhook events aren't arriving**
- Verify Cloudflare tunnel is healthy (logs show "running")
- Test webhook URL manually: `curl https://webhooks.yourdomain.com/`
- Should see your ZPL Print Server homepage

### Testing Without eBay

```bash
# Test your webhook endpoint through the tunnel
curl -X POST https://webhooks.yourdomain.com/webhooks/ebay \
  -H "X-EBAY-SIGNATURE: test" \
  -H "X-EBAY-DELIVERY-TIMESTAMP: $(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
  -H "Content-Type: application/json" \
  -d '{
    "metadata": {"eventId": "test-123", "eventType": "FULFILLMENT.LABEL_DOWNLOADED"},
    "data": {"orderId": "test-order", "shipmentId": "test-shipment"}
  }'

# You should get a response (even if signature fails, connection works)
```

---

### Step 4: Enable in Settings

In the **🔔 Webhooks** tab:
1. Check **Enable eBay Webhooks (Automatic Printing)**
2. Click **Save Settings**

## API Endpoints

### Receive Webhook (eBay calls this)
```
POST /webhooks/ebay
Header: X-EBAY-SIGNATURE: <hmac-sha256>
Header: X-EBAY-DELIVERY-TIMESTAMP: <iso-8601>
Body: { "metadata": { "eventId": "...", "eventType": "FULFILLMENT.LABEL_DOWNLOADED", ... }, "data": { "orderId": "...", "shipmentId": "..." } }

Returns: { "status": "success" } (200 OK)
```

### Generate Webhook Secret
```
POST /api/generate-webhook-secret
Returns: { "status": "success", "secret": "..." }
```

### Get Webhook Events (for debugging)
```
GET /api/webhook-events?limit=20
Returns: [
  {
    "id": 1,
    "event_id": "ebay-event-123",
    "event_type": "FULFILLMENT.LABEL_DOWNLOADED",
    "order_id": "ebay-order-456",
    "status": "COMPLETED",
    "job_id": 42,
    "received_at": "2026-02-02T12:34:56",
    "processed_at": "2026-02-02T12:34:58"
  }
]
```

## Database Schema

### WebhookEvent Table
```sql
CREATE TABLE webhook_events (
  id INTEGER PRIMARY KEY,
  event_id TEXT UNIQUE,           -- eBay event ID (for idempotency)
  event_type TEXT,                -- Type of event (LABEL_DOWNLOADED, etc.)
  order_id TEXT,                  -- eBay order ID
  shipment_id TEXT,               -- eBay shipment ID
  payload TEXT,                   -- Full JSON for debugging
  status TEXT,                    -- RECEIVED, PROCESSING, COMPLETED, FAILED
  job_id INTEGER,                 -- Reference to Job table (what was printed)
  error_message TEXT,             -- Error details if FAILED
  received_at TIMESTAMP,          -- When webhook arrived
  processed_at TIMESTAMP          -- When processing completed
);
```

### Settings Table Additions
```
ebay_webhook_enabled BOOLEAN      -- Master switch for webhook feature
ebay_webhook_secret TEXT (encrypted) -- Shared secret with eBay
ebay_webhook_url TEXT             -- Public URL where webhooks are delivered
ebay_webhook_registered TIMESTAMP -- When registered with eBay
```

## Database Schema

### WebhookEvent Table
```sql
CREATE TABLE webhook_events (
  id INTEGER PRIMARY KEY,
  event_id TEXT UNIQUE,           -- eBay event ID (for idempotency)
  event_type TEXT,                -- Type of event (LABEL_DOWNLOADED, etc.)
  order_id TEXT,                  -- eBay order ID
  shipment_id TEXT,               -- eBay shipment ID
  payload TEXT,                   -- Full JSON for debugging
  status TEXT,                    -- RECEIVED, PROCESSING, COMPLETED, FAILED
  job_id INTEGER,                 -- Reference to Job table (what was printed)
  error_message TEXT,             -- Error details if FAILED
  received_at TIMESTAMP,          -- When webhook arrived
  processed_at TIMESTAMP          -- When processing completed
);
```

### Settings Table Additions
```
ebay_webhook_enabled BOOLEAN      -- Master switch for webhook feature
ebay_webhook_secret TEXT (encrypted) -- Shared secret with eBay
ebay_webhook_url TEXT             -- Public URL where webhooks are delivered (auto-populated from Cloudflare)
ebay_webhook_registered TIMESTAMP -- When registered with eBay
```

---

## Cloudflare Tunnel Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         INTERNET                                │
│  (eBay API - sends webhooks to your public URL)                │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 │ HTTPS Request to webhooks.yourdomain.com
                 │ (Encrypted, signature verified)
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│              CLOUDFLARE EDGE (Global CDN)                       │
│  - DDoS Protection                                              │
│  - HTTPS/TLS Termination                                        │
│  - Geographical Routing                                         │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 │ Encrypted Tunnel
                 │ (Your NAS initiates outbound connection)
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    YOUR NAS (Private Network)                   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │        Docker Bridge Network (zpl-network)              │  │
│  │                                                          │  │
│  │  ┌────────────────────┐    ┌──────────────────────┐    │  │
│  │  │  ZPL Print Server  │    │ Cloudflare Tunnel    │    │  │
│  │  │                    │    │                      │    │  │
│  │  │ Port: 8000         │◄──►│ Outbound tunnel      │    │  │
│  │  │ (localhost only)   │    │ (to Cloudflare edge) │    │  │
│  │  │                    │    │                      │    │  │
│  │  │ - Webhooks         │    │ No open ports        │    │  │
│  │  │ - Label download   │    │ No port forwarding   │    │  │
│  │  │ - Printing         │    │ Fully encrypted      │    │  │
│  │  └────────────────────┘    └──────────────────────┘    │  │
│  │                                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Other Services (Radarr, Sonarr, Jellyfin, etc.)             │
│  - Completely isolated from Internet                           │
│  - Zero exposure to webhooks                                   │
│  - Strict user permissions maintained                          │
└─────────────────────────────────────────────────────────────────┘


KEY SECURITY BENEFITS:
✅ Your NAS IP is never exposed to the internet
✅ Zero open ports on your firewall
✅ Cloudflare handles DDoS protection
✅ All connections are HTTPS encrypted
✅ Tunnel is initiated by your NAS (outbound only)
✅ No NAT traversal or port forwarding needed
✅ Other services completely isolated
✅ Zero-trust security model
```

---

## Performance & Reliability

**Latency through Cloudflare Tunnel:**
- eBay webhook arrives at Cloudflare edge (typically <50ms)
- Routed through tunnel to your NAS (~50-200ms depending on distance)
- Your server processes and fetches label (~2-5 seconds)
- Label printed (~5-10 seconds total)

**Reliability:**
- Cloudflare tunnel auto-reconnects on network interruption
- Webhooks are retried by eBay if timeout
- Idempotency protection handles duplicate webhooks
- All events logged for debugging

**Uptime:**
- Cloudflare: 99.99% SLA
- Your NAS: As reliable as your power/network
- Tunnel automatically reconnects if network drops

---

## Monitoring in Production

### Health Check

```bash
# Check tunnel status
docker compose ps cloudflare-tunnel

# Should show: Up (running)

# Check tunnel logs
docker compose logs --tail=50 cloudflare-tunnel

# Look for "Tunnel running at https://..."
```

### Cloudflare Dashboard

1. Go to https://dash.cloudflare.com/
2. Navigate to **Zero Trust** → **Networks** → **Tunnels**
3. Find your tunnel, should show:
   - Status: **Healthy** ✅
   - Connected connectors: **1 or more**
   - Recent activity: Shows your webhooks

### Event Monitoring

In ZPL Print Server:
1. Go to **🔔 Webhooks** tab
2. Click **📊 View Recent Events**
3. Displays:
   - Timestamp received
   - Event type and order ID
   - Processing status
   - Linked job ID
   - Any errors

---

## Updating Cloudflare Token

If you need to rotate your token:

1. **In Cloudflare Dashboard:**
   - Generate new token
   - Copy it

2. **Update your .env file:**
   ```bash
   CLOUDFLARE_TUNNEL_TOKEN=ey[new-token]
   ```

3. **Restart tunnel:**
   ```bash
   docker compose restart cloudflare-tunnel
   ```

4. **Verify:**
   ```bash
   docker compose logs -f cloudflare-tunnel
   ```

**Note:** No changes needed in eBay webhook configuration - the URL stays the same.

---

## Cost Summary

| Component | Cost | Notes |
|-----------|------|-------|
| Cloudflare Tunnel | Free | 1 tunnel included |
| eBay API | Free | No API fees |
| Shipping Labels | Varies | Only pay for labels themselves |
| Bandwidth through tunnel | Free | Cloudflare includes it |
| **Total** | **$0** | Completely free setup |

---

### Webhook Event Log
Click **📊 View Recent Events** in the Webhooks tab to see:
- All incoming webhooks (success and failures)
- Timestamps when received and processed
- Associated job IDs
- Error messages if anything failed

### Common Issues

**"Signature verification failed"**
- Ensure the webhook secret in eBay's console matches the one generated in settings
- Check that the secret hasn't been rotated without updating eBay's config

**"Timestamp too old"**
- Your server time is out of sync with eBay's
- Run `ntpdate -u pool.ntp.org` or similar to sync system time
- eBay allows 5 minutes clock skew

**"Label not found"**
- Webhook arrived before eBay's API has the label ready
- The background task retries automatically
- Check webhook event log for status

**No webhooks received**
- Verify eBay webhook subscription is active in Developer Console
- Test webhook delivery with eBay's manual test feature
- Ensure firewall allows inbound traffic on port 8000
- Check server logs: `docker compose logs -f`

### Manual Testing

To test webhook verification (without eBay):

```bash
curl -X POST http://localhost:8000/webhooks/ebay \
  -H "X-EBAY-SIGNATURE: test-signature" \
  -H "X-EBAY-DELIVERY-TIMESTAMP: $(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
  -H "Content-Type: application/json" \
  -d '{
    "metadata": {
      "eventId": "test-event-123",
      "eventType": "FULFILLMENT.LABEL_DOWNLOADED"
    },
    "data": {
      "orderId": "test-order-123",
      "shipmentId": "test-shipment-123"
    }
  }'
```

(Note: This will fail signature verification unless you craft a valid HMAC)

## Monitoring in Production

### Metrics to Track
- Number of webhooks received per day
- Success rate (COMPLETED vs FAILED)
- Average time from webhook to printing
- Signature verification failures

### Logging
Enable verbose logging in your Docker setup:
```bash
docker compose logs -f zpl-print-api | grep webhook
```

All webhook operations are logged with timestamps for audit trail.

## Performance Notes

- **Latency:** 2-5 seconds from label purchase to printed label
- **Scalability:** Webhooks are processed asynchronously in background tasks
- **Reliability:** Idempotency protection handles eBay retries automatically
- **Security:** No polling needed → no API rate limit concerns

## Comparison: Manual Fetch vs. Webhook

| Feature | Manual Fetch | Webhook |
|---------|-------------|---------|
| User action needed | Yes (click button) | No (automatic) |
| Latency | Depends on polling | 2-5 seconds |
| API calls | Every N minutes (polling) | Only when label exists |
| Rate limits | Hit limits quickly | No rate limit concerns |
| Complexity | Simple | Enterprise-grade security |
| Best for | Occasional use | High-volume printing |

## Security Best Practices

1. **Keep webhook secret private** - Never share, don't commit to version control
2. **Use HTTPS in production** - eBay requires HTTPS for webhooks
3. **Regularly rotate secret** - Generate a new secret periodically and update eBay's config
4. **Monitor event log** - Watch for unexpected errors or suspicious activity
5. **Keep server time synced** - Timestamp validation requires accurate system time
6. **Firewall rules** - Only allow necessary inbound traffic

## Advanced: Webhook Registration via API

The system includes methods to automatically register webhooks with eBay:

```python
from app.ebay_service import EBayAPI

ebay = EBayAPI(app_id, cert_id, user_token, refresh_token)
result = await ebay.register_webhook(
    webhook_url="https://your-server/webhooks/ebay",
    webhook_secret="your-webhook-secret"
)
# Returns: { "status": "success", "webhook_id": "..." }
```

Currently this is called manually via admin, but can be integrated into the UI for automated setup.

## Support & Further Help

For issues:
1. Check the webhook event log (timestamps, errors, success rate)
2. Review server logs: `docker compose logs --tail=100`
3. Verify eBay Developer Console webhook subscription is active
4. Ensure system time is synchronized
5. Test with ngrok locally if behind NAT

---

**Your ZPL Print Server now has enterprise-grade webhook integration. Enjoy automatic printing! 🎉**
