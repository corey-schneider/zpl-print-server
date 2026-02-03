"""
eBay Webhook Service - Handles HMAC-SHA256 signature verification, timestamp validation, and idempotency.

Security Features:
- HMAC-SHA256 signature verification (industry standard)
- Timestamp validation (prevents replay attacks)
- Idempotency check (prevents duplicate processing)
- Request logging for audit trail
"""

import hmac
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
from app.database import SessionLocal, WebhookEvent

logger = logging.getLogger(__name__)


class WebhookVerificationError(Exception):
    """Raised when webhook verification fails."""
    pass


class WebhookVerifier:
    """Verify and process eBay webhooks with enterprise-grade security."""
    
    # eBay allows up to 5 minutes clock skew
    MAX_TIMESTAMP_AGE_SECONDS = 300
    
    @staticmethod
    def verify_signature(
        webhook_secret: str,
        request_body: str,
        x_ebay_signature: str
    ) -> bool:
        """
        Verify eBay webhook signature using HMAC-SHA256.
        
        Args:
            webhook_secret: The shared secret with eBay
            request_body: Raw request body (must be exact bytes)
            x_ebay_signature: X-EBAY-SIGNATURE header value
            
        Returns:
            True if signature is valid, False otherwise
            
        Reference:
            https://developer.ebay.com/api-docs/user-defined-subscriptions/webhooks
        """
        try:
            # eBay uses HMAC-SHA256
            expected_signature = hmac.new(
                webhook_secret.encode('utf-8'),
                request_body.encode('utf-8') if isinstance(request_body, str) else request_body,
                hashlib.sha256
            ).hexdigest()
            
            # Use constant-time comparison to prevent timing attacks
            return hmac.compare_digest(expected_signature, x_ebay_signature)
        except Exception as e:
            logger.error(f"Signature verification error: {e}")
            return False
    
    @staticmethod
    def verify_timestamp(timestamp_str: str) -> bool:
        """
        Verify webhook timestamp is within acceptable age (prevents replay attacks).
        
        Args:
            timestamp_str: ISO 8601 timestamp from webhook
            
        Returns:
            True if timestamp is recent, False if too old
            
        Raises:
            ValueError: If timestamp format is invalid
        """
        try:
            # Parse ISO 8601 timestamp
            webhook_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            current_time = datetime.now(webhook_time.tzinfo)
            age = current_time - webhook_time
            
            if age.total_seconds() < 0:
                logger.warning(f"Webhook timestamp in future: {timestamp_str}")
                return False
            
            if age.total_seconds() > WebhookVerifier.MAX_TIMESTAMP_AGE_SECONDS:
                logger.warning(f"Webhook timestamp too old ({age.total_seconds()}s): {timestamp_str}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Timestamp verification error: {e}")
            raise ValueError(f"Invalid timestamp format: {timestamp_str}")
    
    @staticmethod
    def check_idempotency(event_id: str) -> Tuple[bool, Optional[str]]:
        """
        Check if webhook has already been processed (idempotency).
        
        Args:
            event_id: Unique event ID from eBay
            
        Returns:
            Tuple of (is_new, existing_job_id)
            - (True, None) = first time seeing this event
            - (False, job_id) = already processed, here's the job ID
            
        This prevents duplicate processing if eBay retries webhook delivery.
        """
        db = SessionLocal()
        try:
            existing = db.query(WebhookEvent).filter(
                WebhookEvent.event_id == event_id
            ).first()
            
            if existing:
                logger.info(f"Webhook event already processed: {event_id} (job_id={existing.job_id})")
                return False, str(existing.job_id) if existing.job_id else None
            
            return True, None
        finally:
            db.close()
    
    @staticmethod
    def record_webhook_event(
        event_id: str,
        event_type: str,
        order_id: str,
        shipment_id: str,
        payload: Dict,
        status: str = "RECEIVED"
    ) -> WebhookEvent:
        """
        Record webhook event in database for audit trail and debugging.
        
        Args:
            event_id: Unique event ID from eBay
            event_type: Type of event (e.g., "LABEL_DOWNLOADED")
            order_id: eBay order ID
            shipment_id: eBay shipment ID
            payload: Full webhook payload
            status: Event status
            
        Returns:
            WebhookEvent record
        """
        db = SessionLocal()
        try:
            event = WebhookEvent(
                event_id=event_id,
                event_type=event_type,
                order_id=order_id,
                shipment_id=shipment_id,
                payload=json.dumps(payload),
                status=status
            )
            db.add(event)
            db.commit()
            db.refresh(event)
            return event
        finally:
            db.close()
    
    @staticmethod
    def update_webhook_event(
        event_id: str,
        status: str,
        job_id: Optional[int] = None,
        error_message: str = ""
    ) -> None:
        """
        Update webhook event status after processing.
        
        Args:
            event_id: Unique event ID from eBay
            status: New status (PROCESSING, COMPLETED, FAILED)
            job_id: Associated job ID if created
            error_message: Error details if failed
        """
        db = SessionLocal()
        try:
            event = db.query(WebhookEvent).filter(
                WebhookEvent.event_id == event_id
            ).first()
            
            if event:
                event.status = status
                event.job_id = job_id
                event.error_message = error_message
                event.processed_at = datetime.now()
                db.commit()
                logger.info(f"Updated webhook event {event_id}: {status}")
        except Exception as e:
            logger.error(f"Failed to update webhook event {event_id}: {e}")
        finally:
            db.close()


def parse_ebay_webhook(payload: Dict) -> Tuple[str, str, str, str]:
    """
    Parse eBay webhook payload and extract key information.
    
    eBay label webhooks contain nested fulfillment data.
    
    Returns:
        Tuple of (event_id, event_type, order_id, shipment_id)
    """
    try:
        # eBay webhook structure varies by event type
        # Common structure includes metadata and data fields
        metadata = payload.get("metadata", {})
        event_id = metadata.get("eventId", "")
        event_type = metadata.get("eventType", "")
        
        # Label data is typically in the data section
        data = payload.get("data", {})
        order_id = data.get("orderId", "")
        shipment_id = data.get("shipmentId", "")
        
        if not all([event_id, event_type, order_id, shipment_id]):
            logger.warning(f"Incomplete webhook payload: {payload}")
            raise ValueError("Missing required fields in webhook payload")
        
        return event_id, event_type, order_id, shipment_id
    except Exception as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        raise ValueError(f"Invalid webhook payload: {e}")
