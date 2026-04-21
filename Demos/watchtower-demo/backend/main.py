"""
AlohaAI Emergency Watchtower - FastAPI Backend
Serves the frontend and provides API endpoints for report generation
"""

import os
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from watchtower import EmergencyReportGenerator

# Load environment variables
load_dotenv()

app = FastAPI(title="AlohaAI Emergency Watchtower", version="1.0.0")

# CORS - allow your domain (update this after deployment)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten to your domain in production: ["https://yourdomain.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files ──────────────────────────────────────────────────────────────
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def serve_frontend():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


# ── Models ────────────────────────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    url: str


# ── SSE Helper ────────────────────────────────────────────────────────────────
def sse_event(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


# ── Report Generation Endpoint (SSE streaming) ────────────────────────────────
@app.post("/api/generate")
async def generate_report(req: GenerateRequest):
    """
    Streams progress events and the final report via Server-Sent Events.
    Event types:
      - log      { type, message, level }   level: info | processing | success | error
      - status   { type, status, count }
      - report   { type, content }          final markdown report
      - done     { type }
      - error    { type, message }
    """

    async def stream() -> AsyncGenerator[str, None]:
        generator = EmergencyReportGenerator()

        # ── Validate credentials ──────────────────────────────────────────
        if not generator.is_valid():
            for err in generator.validation_errors:
                yield sse_event({"type": "log", "message": err, "level": "error"})
            yield sse_event({"type": "error", "message": "Missing API credentials. Check server .env file."})
            return

        # ── Validate URL ──────────────────────────────────────────────────
        url = req.url.strip()
        if not url:
            yield sse_event({"type": "error", "message": "Please enter a Facebook post URL."})
            return

        # ── Progress queue for thread → async bridge ──────────────────────
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def progress(msg: str, level: str = "processing"):
            loop.call_soon_threadsafe(queue.put_nowait, ("log", msg, level))

        def status(text: str, count: int = None):
            loop.call_soon_threadsafe(queue.put_nowait, ("status", text, count))

        # ── Run blocking work in thread pool ─────────────────────────────
        async def run_analysis():
            import concurrent.futures
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

            def blocking_work():
                try:
                    # Extract post ID
                    status("Extracting post ID…")
                    progress("Extracting post ID from URL…")

                    post_id = generator.extract_post_id_from_url(url)
                    if not post_id:
                        progress("Could not extract post ID from URL", "error")
                        loop.call_soon_threadsafe(queue.put_nowait, ("error", "Could not extract post ID from URL.", None))
                        return

                    full_post_id = f"{generator.group_id}_{post_id}"
                    progress(f"Post ID: {full_post_id}")

                    # Scrape comments
                    status("Scraping comments…")
                    progress("Connecting to Facebook Graph API…")

                    comments = generator.scrape_comments(full_post_id, lambda m: progress(m))

                    if not comments:
                        progress("No comments retrieved — check your Facebook token and post URL", "error")
                        loop.call_soon_threadsafe(queue.put_nowait, ("error", "No comments retrieved.", None))
                        return

                    count = len(comments)
                    status("Analyzing with AI…", count)
                    progress(f"Retrieved {count} comments total", "success")
                    progress("Sending to Claude AI for analysis…")

                    # Generate report
                    report = generator.generate_report(comments, lambda m: progress(m))

                    if not report:
                        progress("Failed to generate report", "error")
                        loop.call_soon_threadsafe(queue.put_nowait, ("error", "AI report generation failed.", None))
                        return

                    # Done!
                    progress("Report generated successfully", "success")
                    status("Complete", count)
                    loop.call_soon_threadsafe(queue.put_nowait, ("report", report, count))

                except Exception as e:
                    loop.call_soon_threadsafe(queue.put_nowait, ("error", str(e), None))
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, ("done", None, None))

            future = loop.run_in_executor(executor, blocking_work)
            return future

        analysis_future = await run_analysis()

        # ── Drain the queue and stream events ────────────────────────────
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=120.0)
            except asyncio.TimeoutError:
                yield sse_event({"type": "error", "message": "Request timed out."})
                break

            kind, data, extra = item

            if kind == "log":
                level = extra if extra else "processing"
                yield sse_event({"type": "log", "message": data, "level": level})

            elif kind == "status":
                payload = {"type": "status", "status": data}
                if extra is not None:
                    payload["count"] = extra
                yield sse_event(payload)

            elif kind == "report":
                yield sse_event({"type": "report", "content": data, "count": extra})

            elif kind == "error":
                yield sse_event({"type": "error", "message": data})
                break

            elif kind == "done":
                yield sse_event({"type": "done"})
                break

        # Ensure the executor future is cleaned up
        try:
            await asyncio.wait_for(analysis_future, timeout=5.0)
        except Exception:
            pass

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


# ── Save Report Endpoint ──────────────────────────────────────────────────────
class SaveRequest(BaseModel):
    content: str


@app.post("/api/save")
async def save_report(req: SaveRequest):
    """Save the report to disk and return the filename."""
    reports_dir = Path("watchtower_reports")
    reports_dir.mkdir(exist_ok=True)

    file_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"emergency_report_{file_timestamp}.txt"
    filepath = reports_dir / filename

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"Generated: {timestamp}\n")
        f.write("=" * 80 + "\n\n")
        f.write(req.content.strip())

    return JSONResponse({"filename": filename, "path": str(filepath)})


# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    generator = EmergencyReportGenerator()
    return {
        "status": "ok",
        "credentials_valid": generator.is_valid(),
        "missing": generator.validation_errors,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
