"""
TeraBox API integration module.
Handles fetching download links and metadata from TeraBox files.
"""

import aiohttp
from typing import Optional, Dict, Any
from utils.logger import logger, log_error


class TeraBoxAPI:
    """TeraBox API client for fetching download links and file info."""

    def __init__(self, api_url: str):
        """
        Initialize TeraBox API client.
        
        Args:
            api_url: TeraBox API endpoint (e.g., https://api-download-backend.vercel.app)
        """
        self.api_url = api_url

    async def get_download_info(self, terabox_url: str, user_id: int = 0) -> Optional[Dict[str, Any]]:
        """
        Fetch download info and direct link from TeraBox.
        
        Args:
            terabox_url: TeraBox URL
            user_id: User ID for logging
            
        Returns:
            Dict with direct_link, filename, size, thumbnail, title or None
        """
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "platform": "terabox",
                    "link": terabox_url,
                    "media_type": "video",
                    "quality": "best"
                }
                
                async with session.post(
                    f"{self.api_url}/terabox/download/v1",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        if data.get("result"):
                            result = data["result"]
                            
                            # Parse size - might be string like "9.29 MB" or just number
                            size = result.get("size", 0)
                            if isinstance(size, str):
                                try:
                                    # Try to parse "X.XX MB" format
                                    if "MB" in size.upper():
                                        size_mb = float(size.upper().replace("MB", "").strip())
                                        size = int(size_mb * 1024 * 1024)
                                    elif "GB" in size.upper():
                                        size_gb = float(size.upper().replace("GB", "").strip())
                                        size = int(size_gb * 1024 * 1024 * 1024)
                                    else:
                                        size = int(float(size))
                                except:
                                    size = 0
                            else:
                                size = int(size) if size else 0
                            
                            return {
                                "direct_link": result.get("direct_link"),
                                "filename": result.get("filename", "file.mp4"),
                                "size": size,
                                "thumbnail": result.get("thumbnail"),
                                "title": result.get("title", "Download"),
                            }
                    else:
                        log_error(user_id, "terabox_api_error", f"Status {resp.status}")
                        return None
        except Exception as e:
            log_error(user_id, "terabox_api_error", str(e))
            return None

    async def get_direct_link(self, terabox_url: str, user_id: int = 0) -> Optional[str]:
        """
        Get direct download link from TeraBox URL.
        
        Args:
            terabox_url: TeraBox URL
            user_id: User ID for logging
            
        Returns:
            Direct download link or None
        """
        info = await self.get_download_info(terabox_url, user_id)
        return info.get("direct_link") if info else None


# Global TeraBox API instance
terabox_api = None

def init_terabox_api(api_url: str):
    """Initialize TeraBox API client."""
    global terabox_api
    terabox_api = TeraBoxAPI(api_url)
    logger.info(f"TeraBox API initialized: {api_url}")

def get_terabox_api() -> TeraBoxAPI:
    """Get TeraBox API instance."""
    return terabox_api
