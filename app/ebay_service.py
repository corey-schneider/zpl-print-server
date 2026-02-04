"""
eBay API integration for fetching shipping labels directly from eBay.
Handles OAuth, label download, and ZPL format retrieval.
"""
import os
import logging
import requests
import asyncio
from datetime import datetime, timedelta
from app.database import SessionLocal, Settings, Job

logger = logging.getLogger(__name__)

class EBayAPI:
    """Secure eBay API client for shipping label retrieval."""
    
    # Production eBay endpoints
    OAUTH_ENDPOINT = "https://api.ebay.com/identity/v1/oauth2/token"
    FULFILLMENT_ENDPOINT = "https://api.ebay.com/sell/fulfillment/v1"
    LOGISTICS_ENDPOINT = "https://api.ebay.com/sell/logistics/v1"
    
    def __init__(self, app_id: str, cert_id: str, user_token: str, refresh_token: str = None):
        self.app_id = app_id
        self.cert_id = cert_id
        self.user_token = user_token
        self.refresh_token = refresh_token
        self.access_token = None
        self.token_expiration = None
    
    async def test_connection(self) -> dict:
        """Test the eBay API connection with current credentials."""
        try:
            # Try to refresh token and make a simple API call
            if await self._refresh_access_token_if_needed():
                # Verify token works by calling a simple endpoint
                headers = self._get_headers()
                response = requests.get(
                    f"{self.FULFILLMENT_ENDPOINT}/order?limit=1",
                    headers=headers,
                    timeout=5
                )
                
                if response.status_code == 200:
                    return {
                        "status": "connected",
                        "message": "✅ eBay API connection successful"
                    }
                elif response.status_code == 401:
                    return {
                        "status": "auth_failed",
                        "message": "❌ Authentication failed - check your credentials"
                    }
                else:
                    return {
                        "status": "error",
                        "message": f"❌ API error: {response.status_code}"
                    }
            else:
                return {
                    "status": "error",
                    "message": "❌ Could not refresh access token"
                }
        except requests.exceptions.Timeout:
            return {
                "status": "error",
                "message": "❌ Connection timeout - check your internet"
            }
        except Exception as e:
            logger.error(f"eBay connection test failed: {e}")
            return {
                "status": "error",
                "message": f"❌ Connection error: {str(e)}"
            }
    
    async def _refresh_access_token_if_needed(self) -> bool:
        """Refresh access token if expired or not set."""
        try:
            # If no token or expired, refresh it
            if not self.access_token or not self.token_expiration or datetime.now() > self.token_expiration:
                return await self._refresh_access_token()
            return True
        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            return False
    
    async def _refresh_access_token(self) -> bool:
        """Get new access token using refresh token or user token."""
        try:
            # Use refresh token if available, otherwise use user token
            token_to_use = self.refresh_token or self.user_token
            
            data = {
                "grant_type": "refresh_token" if self.refresh_token else "authorization_code",
                "refresh_token": token_to_use if self.refresh_token else None,
                "code": token_to_use if not self.refresh_token else None
            }
            
            response = requests.post(
                self.OAUTH_ENDPOINT,
                auth=(self.app_id, self.cert_id),
                data={k: v for k, v in data.items() if v},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                self.access_token = result.get("access_token")
                # Token expires in seconds, set expiration to 5 min before actual expiry
                expires_in = result.get("expires_in", 3600)
                self.token_expiration = datetime.now() + timedelta(seconds=expires_in - 300)
                
                # Update refresh token if provided
                if "refresh_token" in result:
                    self.refresh_token = result["refresh_token"]
                
                return True
            else:
                logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Token refresh exception: {e}")
            return False
    
    def _get_headers(self) -> dict:
        """Get headers for eBay API requests."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    async def fetch_recent_labels(self, minutes: int = 30) -> list:
        """
        Fetch recently purchased shipping labels from eBay.
        Returns list of labels with order info and label URLs.
        """
        try:
            if not await self._refresh_access_token_if_needed():
                logger.error("Failed to refresh access token")
                return []
            
            headers = self._get_headers()
            
            # Get orders from the past X minutes
            created_date_min = (datetime.now() - timedelta(minutes=minutes)).isoformat() + "Z"
            
            params = {
                "filter": f"creationDate:[{created_date_min},]",
                "limit": 50
            }
            
            response = requests.get(
                f"{self.FULFILLMENT_ENDPOINT}/order",
                headers=headers,
                params=params,
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch orders: {response.status_code}")
                return []
            
            orders = response.json().get("orders", [])
            labels = []
            
            for order in orders:
                order_id = order.get("orderId")
                fulfillments = order.get("fulfillments", [])
                
                for fulfillment in fulfillments:
                    shipments = fulfillment.get("shippingFulfillment", {}).get("shippingPackages", [])
                    
                    for shipment in shipments:
                        label_info = shipment.get("shippingLabel")
                        if label_info:
                            labels.append({
                                "order_id": order_id,
                                "shipment_id": shipment.get("shipmentId"),
                                "label_download_url": label_info.get("downloadLabelFile"),
                                "tracking_number": label_info.get("trackingNumber"),
                                "carrier_code": label_info.get("carrierCode")
                            })
            
            return labels
        except Exception as e:
            logger.error(f"Error fetching labels: {e}")
            return []
    
    async def download_label(self, label_download_url: str, format: str = "ZPL") -> dict:
        """
        Download label file from eBay in specified format.
        Formats: PDF, ZPL, PNG, JPEG
        """
        try:
            if not await self._refresh_access_token_if_needed():
                return {"status": "error", "message": "Authentication failed"}
            
            headers = self._get_headers()
            
            # Add format parameter to URL
            url = f"{label_download_url}?labelFormat={format}"
            
            response = requests.get(
                url,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return {
                    "status": "success",
                    "content": response.content,
                    "format": format
                }
            else:
                logger.error(f"Label download failed: {response.status_code}")
                return {
                    "status": "error",
                    "message": f"Download failed: {response.status_code}"
                }
        except Exception as e:
            logger.error(f"Error downloading label: {e}")
            return {"status": "error", "message": str(e)}
    
    async def fetch_and_save_label(self, order_id: str, label_info: dict) -> dict:
        """
        Fetch both PDF and ZPL formats and save to disk, create Job record.
        """
        try:
            db = SessionLocal()
            
            # Download PDF
            pdf_result = await self.download_label(label_info["label_download_url"], "PDF")
            if pdf_result["status"] != "success":
                return {"status": "error", "message": "Failed to download PDF"}
            
            # Download ZPL
            zpl_result = await self.download_label(label_info["label_download_url"], "ZPL")
            if zpl_result["status"] != "success":
                return {"status": "error", "message": "Failed to download ZPL"}
            
            # Create Job record
            job = Job(
                filename=f"eBay_Order_{order_id}.pdf",
                source="eBay API",
                status="READY",
                log=f"Tracking: {label_info.get('tracking_number', 'N/A')}"
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            job_id = job.id
            db.close()
            
            # Save files
            pdf_path = f"/app/data/{job_id}.pdf"
            zpl_path = f"/app/data/{job_id}.zpl"
            
            with open(pdf_path, "wb") as f:
                f.write(pdf_result["content"])
            
            with open(zpl_path, "wb") as f:
                f.write(zpl_result["content"])
            
            logger.info(f"eBay label saved: {job_id} (Order: {order_id})")
            
            return {
                "status": "success",
                "job_id": job_id,
                "message": f"Label fetched and saved for order {order_id}"
            }
        except Exception as e:
            logger.error(f"Error saving label: {e}")
            return {"status": "error", "message": str(e)}
