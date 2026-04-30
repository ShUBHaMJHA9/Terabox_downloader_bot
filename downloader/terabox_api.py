"""
TeraBox API integration module.
Handles fetching download links and metadata from TeraBox files.
"""

import asyncio
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
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "platform": "terabox",
                        "link": terabox_url,
                        "media_type": "video",
                        "quality": "best"
                    }
                    
                    logger.info(f"[TeraBox API] Fetching download info for: {terabox_url}")
                    
                    async with session.post(
                        f"{self.api_url}/terabox/download/v1",
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=120, sock_connect=30, sock_read=30)
                    ) as resp:
                        logger.debug(f"[TeraBox API] Response status: {resp.status}")
                        
                        if resp.status == 200:
                            data = await resp.json()
                            logger.debug(f"[TeraBox API] Response data: {data}")
                            
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
                                
                                logger.info(f"[TeraBox API] ✅ Got download info: {result.get('filename')} ({size} bytes)")
                                
                                return {
                                    "direct_link": result.get("direct_link"),
                                    "filename": result.get("filename", "file.mp4"),
                                    "size": size,
                                    "thumbnail": result.get("thumbnail"),
                                    "title": result.get("title", "Download"),
                                }
                            else:
                                # Status 200 but no result field
                                error_msg = data.get("error", "Unknown error")
                                logger.error(f"[TeraBox API] ❌ API returned status 200 but no result field. Error: {error_msg}. Full response: {data}")
                                log_error(user_id, "terabox_api_error", f"No result in API response: {error_msg}")
                                return None
                        else:
                            # Non-200 status code
                            error_text = ""
                            try:
                                error_data = await resp.json()
                                error_text = str(error_data)
                            except:
                                error_text = await resp.text()
                            
                            error_msg = f"HTTP {resp.status}: {error_text}"
                            if attempt < max_retries - 1:
                                wait_time = 2 ** attempt
                                logger.warning(f"[TeraBox API] {error_msg}, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                                await asyncio.sleep(wait_time)
                                continue
                            
                            logger.error(f"[TeraBox API] ❌ API request failed: {error_msg}")
                            log_error(user_id, "terabox_api_error", error_msg)
                            return None
                            
            except asyncio.TimeoutError as e:
                error_msg = f"Request timeout: {e}"
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"[TeraBox API] {error_msg}, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"[TeraBox API] ❌ {error_msg}")
                    log_error(user_id, "terabox_api_error", error_msg)
                    return None
            except Exception as e:
                error_msg = f"{type(e).__name__}: {e}"
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"[TeraBox API] {error_msg}, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"[TeraBox API] ❌ Exception during API call: {error_msg}", exc_info=True)
                    log_error(user_id, "terabox_api_error", error_msg)
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
