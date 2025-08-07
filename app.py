from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, HttpUrl
from playwright.async_api import async_playwright
import asyncio
import os
from typing import Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="HTML Scraper API", version="1.0.0")
security = HTTPBearer()

# Configuration
VALID_TOKEN = os.getenv("SCRAPER_AUTH_TOKEN", "your-secret-token-here")
REQUEST_TIMEOUT = 30000  # 30 seconds
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

class ScrapeRequest(BaseModel):
    url: HttpUrl
    wait_for_selector: Optional[str] = None  # Optional CSS selector to wait for
    wait_time: Optional[int] = 3  # Seconds to wait after page load
    timeout: Optional[int] = 30  # Request timeout in seconds

class ScrapeResponse(BaseModel):
    html: str
    url: str
    status_code: int
    success: bool
    error: Optional[str] = None

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify the bearer token"""
    if credentials.credentials != VALID_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials

@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_url(
    request: ScrapeRequest,
    token: str = Depends(verify_token)
):
    """
    Scrape a URL and return the fully rendered HTML after JavaScript execution
    """
    try:
        async with async_playwright() as p:
            # Launch browser with optimized settings
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--no-first-run',
                    '--no-zygote',
                    '--disable-gpu'
                ]
            )
            
            try:
                # Create a new page
                page = await browser.new_page(user_agent=USER_AGENT)
                
                # Set viewport
                await page.set_viewport_size({"width": 1920, "height": 1080})
                
                # Navigate to the URL
                response = await page.goto(
                    str(request.url),
                    timeout=request.timeout * 1000,
                    wait_until="networkidle"
                )
                
                if response is None:
                    raise HTTPException(
                        status_code=400,
                        detail="Failed to load the page"
                    )
                
                # Wait for specific selector if provided
                if request.wait_for_selector:
                    try:
                        await page.wait_for_selector(
                            request.wait_for_selector,
                            timeout=request.timeout * 1000
                        )
                    except Exception as e:
                        logger.warning(f"Selector {request.wait_for_selector} not found: {e}")
                
                # Additional wait time for any remaining JavaScript
                if request.wait_time and request.wait_time > 0:
                    await asyncio.sleep(request.wait_time)
                
                # Get the final HTML content
                html_content = await page.content()
                
                return ScrapeResponse(
                    html=html_content,
                    url=str(request.url),
                    status_code=response.status,
                    success=True
                )
                
            finally:
                await browser.close()
                
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=408,
            detail=f"Request timeout after {request.timeout} seconds"
        )
    except Exception as e:
        logger.error(f"Scraping error for {request.url}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Scraping failed: {str(e)}"
        )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "HTML Scraper API"}

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "HTML Scraper API",
        "version": "1.0.0",
        "endpoints": {
            "POST /scrape": "Scrape a URL and return rendered HTML",
            "GET /health": "Health check",
        },
        "authentication": "Bearer token required"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
