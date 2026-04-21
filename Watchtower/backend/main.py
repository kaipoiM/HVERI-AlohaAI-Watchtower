"""
AlohaAI Emergency Watchtower - FastAPI Backend
Serves the frontend and provides API endpoints for citizen submissions
and AI-powered emergency report generation.
"""

import os
import json
import asyncio
import requests as http_requests
from pathlib import Path
from datetime import datetime
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from weasyprint import HTML as WeasyprintHTML
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from backend.watchtower import EmergencyReportGenerator, DatabaseManager

# Load environment variables
load_dotenv()

app = FastAPI(title="AlohaAI Emergency Watchtower", version="2.0.0")

# Rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=[])
app.state.limiter = limiter
def rate_limit_handler(req, exc):
    path = req.url.path
    if "submit" in path:
        msg = "Too many submissions from your location. Please wait 10 minutes before trying again."
    else:
        msg = "Too many attempts. Please wait a minute and try again."
    return JSONResponse(status_code=429, content={"detail": msg})

app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS — update to your domain once you have one
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://watchtower.kaipoi.site"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared DB instance (thread-safe via per-call connections in DatabaseManager)
db = DatabaseManager()

# ── Auth setup ────────────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY  = os.getenv("SECRET_KEY", "change-me-in-env")
serializer  = URLSafeTimedSerializer(SECRET_KEY)
SESSION_MAX_AGE = 8 * 60 * 60  # 8 hours in seconds


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def make_session(admin_id: int) -> str:
    return serializer.dumps(admin_id, salt="session")


def read_session(token: str) -> Optional[int]:
    try:
        return serializer.loads(token, salt="session", max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def get_current_admin(request: Request) -> Optional[dict]:
    token = request.cookies.get("session")
    if not token:
        return None
    admin_id = read_session(token)
    if not admin_id:
        return None
    return db.get_admin_by_id(admin_id)


def require_admin(request: Request) -> dict:
    admin = get_current_admin(request)
    if not admin:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return admin


# ── Turnstile verification ────────────────────────────────────────────────────
TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET_KEY", "")
TURNSTILE_URL    = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

def verify_turnstile(token: str, remote_ip: str) -> bool:
    """Verify a Turnstile token with Cloudflare. Returns True if valid."""
    if not TURNSTILE_SECRET:
        return True  # Skip verification if secret not configured
    try:
        resp = http_requests.post(TURNSTILE_URL, data={
            "secret":   TURNSTILE_SECRET,
            "response": token,
            "remoteip": remote_ip,
        }, timeout=5)
        return resp.json().get("success", False)
    except Exception:
        return False

# ── Static files ──────────────────────────────────────────────────────────────
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def serve_user_form():
    return FileResponse(str(FRONTEND_DIR / "user.html"))


@app.get("/admin/login")
async def serve_login(request: Request):
    # Already logged in — go straight to admin
    if get_current_admin(request):
        return RedirectResponse("/admin", status_code=302)
    return FileResponse(str(FRONTEND_DIR / "login.html"))


@app.get("/admin/change-password")
async def serve_change_password(request: Request):
    admin = get_current_admin(request)
    if not admin:
        return RedirectResponse("/admin/login", status_code=302)
    return FileResponse(str(FRONTEND_DIR / "change_password.html"))


@app.get("/admin")
async def serve_admin(request: Request):
    admin = get_current_admin(request)
    if not admin:
        return RedirectResponse("/admin/login", status_code=302)
    if admin["must_change_password"]:
        return RedirectResponse("/admin/change-password", status_code=302)
    return FileResponse(str(FRONTEND_DIR / "admin.html"))


# ── Models ────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    login: str       # email or username
    password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str

class SubmitRequest(BaseModel):
    incident_type: str
    district: str
    location: str = ""
    description: str
    severity: str = "low"
    evacuation: str = ""
    reporter_name: str = ""
    timestamp: str = ""
    ref_code: str = ""
    turnstile_token: str = ""


class SaveRequest(BaseModel):
    content: str


# ── SSE Helper ────────────────────────────────────────────────────────────────

def sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"

# ── Auth endpoints ────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
@limiter.limit("5/minute")
async def login(request: Request, req: LoginRequest):
    admin = db.get_admin_by_login(req.login.strip())
    if not admin or not verify_password(req.password, admin["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    db.update_last_login(admin["id"])
    token = make_session(admin["id"])

    response = JSONResponse({
        "ok": True,
        "must_change_password": bool(admin["must_change_password"]),
    })
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=SESSION_MAX_AGE,
    )
    return response


@app.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie("session")
    return JSONResponse({"ok": True})


@app.post("/api/auth/change-password")
async def change_password(req: ChangePasswordRequest, request: Request):
    admin = get_current_admin(request)
    if not admin:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    if not verify_password(req.current_password, admin["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    if req.new_password != req.confirm_password:
        raise HTTPException(status_code=400, detail="New passwords do not match.")

    if len(req.new_password) < 10:
        raise HTTPException(status_code=400, detail="Password must be at least 10 characters.")

    db.update_password(admin["id"], hash_password(req.new_password), must_change=0)
    return JSONResponse({"ok": True})


@app.get("/api/auth/me")
async def me(request: Request):
    admin = get_current_admin(request)
    if not admin:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return JSONResponse({
        "id": admin["id"],
        "username": admin["username"],
        "email": admin["email"],
        "must_change_password": bool(admin["must_change_password"]),
    })


# ── Citizen Submission ────────────────────────────────────────────────────────

@app.post("/api/submit")
@limiter.limit("3/10minute")
async def submit_report(request: Request, req: SubmitRequest):
    """
    Accept a citizen submission from user.html and store it in SQLite.
    Returns the ref_code so the confirmation screen can display it.
    """
    if not req.incident_type or not req.district or not req.description.strip():
        raise HTTPException(status_code=422, detail="incident_type, district, and description are required.")

    # Verify Turnstile token
    if not verify_turnstile(req.turnstile_token, request.client.host):
        raise HTTPException(status_code=403, detail="Bot verification failed. Please try again.")

    data = req.model_dump()

    # Use client-generated ref_code if provided, otherwise generate one server-side
    if not data.get("ref_code"):
        import random, string
        chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        data["ref_code"] = "HI-" + "".join(random.choices(chars, k=6))

    db.insert_submission(data)
    return JSONResponse({"ref_code": data["ref_code"]})


# ── Submissions List ──────────────────────────────────────────────────────────

@app.get("/api/submissions")
async def get_submissions(request: Request):
    """Return all submissions (newest first) for the admin Submissions tab."""
    require_admin(request)
    submissions = db.get_all()
    return JSONResponse({"submissions": submissions})


@app.get("/api/submissions/counts")
async def get_counts(request: Request):
    """Return pending and total submission counts for the admin status bar."""
    require_admin(request)
    return JSONResponse(db.get_counts())


@app.delete("/api/submissions/{submission_id}")
async def delete_submission(submission_id: int, request: Request):
    """Hard-delete a submission (admin moderation action)."""
    require_admin(request)
    deleted = db.delete_submission(submission_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Submission not found.")
    return JSONResponse({"deleted": True})


# ── Report Generation (SSE streaming) ────────────────────────────────────────

@app.post("/api/generate")
async def generate_report(request: Request):
    require_admin(request)
    """
    Reads all unprocessed (pending) submissions, sends them to Claude,
    and streams progress + the final report back via Server-Sent Events.

    After a successful generation the processed submissions are marked
    in the DB and a context summary is saved for the next cycle.

    Event types:
      log    { type, message, level }   level: info | processing | success | error
      status { type, status, pending, total }
      report { type, content }
      done   { type }
      error  { type, message }
    """

    async def stream() -> AsyncGenerator[str, None]:
        generator = EmergencyReportGenerator()

        # ── Validate credentials ──────────────────────────────────────────
        if not generator.is_valid():
            for err in generator.validation_errors:
                yield sse_event({"type": "log", "message": err, "level": "error"})
            yield sse_event({"type": "error", "message": "Missing API credentials. Check server .env file."})
            return

        # ── Check for pending submissions ─────────────────────────────────
        pending = db.get_pending()
        if not pending:
            yield sse_event({"type": "log", "message": "No pending submissions to process.", "level": "info"})
            yield sse_event({"type": "error", "message": "No pending submissions — nothing to generate a report from."})
            return

        counts = db.get_counts()
        yield sse_event({
            "type": "status",
            "status": "Starting…",
            "pending": counts["pending"],
            "total": counts["total"],
        })
        yield sse_event({
            "type": "log",
            "message": f"Found {len(pending)} pending submission(s). Starting analysis…",
            "level": "info",
        })

        # ── Progress queue for thread → async bridge ──────────────────────
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def progress(msg: str, level: str = "processing"):
            loop.call_soon_threadsafe(queue.put_nowait, ("log", msg, level))

        # ── Run blocking Claude work in thread pool ───────────────────────
        async def run_analysis():
            import concurrent.futures
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

            def blocking_work():
                try:
                    report = generator.generate_report(pending, lambda m: progress(m))

                    if not report:
                        loop.call_soon_threadsafe(
                            queue.put_nowait, ("error", "AI report generation failed.", None)
                        )
                        return

                    progress("Report generated successfully", "success")

                    # Fetch updated counts (pending should now be 0 for this batch)
                    updated = db.get_counts()
                    loop.call_soon_threadsafe(
                        queue.put_nowait, ("report", report, updated)
                    )

                except Exception as e:
                    loop.call_soon_threadsafe(
                        queue.put_nowait, ("error", str(e), None)
                    )
                finally:
                    loop.call_soon_threadsafe(
                        queue.put_nowait, ("done", None, None)
                    )

            return loop.run_in_executor(executor, blocking_work)

        analysis_future = await run_analysis()

        # ── Drain queue and stream events ─────────────────────────────────
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=180.0)
            except asyncio.TimeoutError:
                yield sse_event({"type": "error", "message": "Request timed out."})
                break

            kind, data, extra = item

            if kind == "log":
                level = extra if extra else "processing"
                yield sse_event({"type": "log", "message": data, "level": level})

            elif kind == "report":
                # extra is the updated counts dict
                updated_counts = extra or {}
                yield sse_event({
                    "type": "report",
                    "content": data,
                    "pending": updated_counts.get("pending", 0),
                    "total": updated_counts.get("total", 0),
                })
                yield sse_event({
                    "type": "status",
                    "status": "Complete",
                    "pending": updated_counts.get("pending", 0),
                    "total": updated_counts.get("total", 0),
                })

            elif kind == "error":
                yield sse_event({"type": "error", "message": data})
                break

            elif kind == "done":
                yield sse_event({"type": "done"})
                break

        # Clean up executor future
        try:
            await asyncio.wait_for(analysis_future, timeout=5.0)
        except Exception:
            pass

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Markdown → HTML helper ────────────────────────────────────────────────────

def markdown_to_html(md: str) -> str:
    """Minimal markdown converter matching the one in app.js."""
    import re
    html = md
    html = html.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$",  r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.+)$",   r"<h1>\1</h1>", html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\*(.+?)\*",     r"<em>\1</em>", html)
    html = re.sub(r"^- (.+)$",  r"<li>\1</li>", html, flags=re.MULTILINE)
    html = re.sub(r"^• (.+)$",  r"<li>\1</li>", html, flags=re.MULTILINE)
    html = re.sub(r"^---+$", "<hr>", html, flags=re.MULTILINE)
    html = html.replace("\n\n", "</p><p>")
    html = re.sub(r"(<li>.*?</li>)", r"<ul>\1</ul>", html, flags=re.DOTALL)
    html = f"<p>{html}</p>"
    urgent_words = r"\b(URGENT|MANDATORY EVACUATION|EVACUATE|EVACUATIONS|COMPLETELY CLOSED|CLOSED|FATALITIES?|CRITICAL|EMERGENCY|IMMEDIATE)\b"
    html = re.sub(urgent_words, r'<span class="urgent">\1</span>', html, flags=re.IGNORECASE)
    return html


def build_pdf_html(markdown: str, timestamp: str) -> str:
    """Wrap the report body in a styled HTML document for WeasyPrint."""
    body = markdown_to_html(markdown)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  @page {{
    size: A4;
    margin: 2cm 2.2cm;
    @bottom-center {{
      content: "AlohaAI Emergency Watchtower — HVERI — Page " counter(page) " of " counter(pages);
      font-size: 9px;
      color: #888;
      font-family: sans-serif;
    }}
  }}
  body {{
    font-family: Georgia, "Times New Roman", serif;
    font-size: 12px;
    line-height: 1.65;
    color: #1a1a1a;
  }}
  .header {{
    border-bottom: 2px solid #c0392b;
    padding-bottom: 10px;
    margin-bottom: 18px;
  }}
  .header h1 {{
    font-size: 20px;
    color: #c0392b;
    margin: 0 0 2px 0;
    font-family: sans-serif;
    letter-spacing: 0.04em;
  }}
  .header .meta {{
    font-size: 10px;
    color: #666;
    font-family: monospace;
  }}
  h2 {{ font-size: 14px; color: #c0392b; margin: 18px 0 6px; font-family: sans-serif; }}
  h3 {{ font-size: 12px; color: #333; margin: 14px 0 4px; font-family: sans-serif; }}
  ul {{ margin: 4px 0 10px 18px; padding: 0; }}
  li {{ margin-bottom: 4px; }}
  p  {{ margin: 0 0 8px; }}
  hr {{ border: none; border-top: 1px solid #ddd; margin: 14px 0; }}
  .urgent {{
    color: #c0392b;
    font-weight: bold;
  }}
  .footer-note {{
    margin-top: 24px;
    padding-top: 8px;
    border-top: 1px solid #ddd;
    font-size: 9px;
    color: #999;
    font-family: monospace;
  }}
</style>
</head>
<body>
  <div class="header">
    <h1>AlohaAI Emergency Watchtower</h1>
    <div class="meta">
      Hawaiian Volcano Education &amp; Resilience Institute (HVERI)&nbsp;&nbsp;·&nbsp;&nbsp;Generated: {timestamp} HST
    </div>
  </div>
  {body}
  <div class="footer-note">
    This report was generated automatically from citizen submissions and reviewed by AI.
    All information should be verified with Hawaii County Civil Defense before operational use.
  </div>
</body>
</html>"""


# ── Save Report ───────────────────────────────────────────────────────────────

REPORTS_DIR = Path("/var/www/HVERI-AlohaAI-Watchtower/watchtower_reports")

@app.post("/api/save")
async def save_report(req: SaveRequest, request: Request):
    """
    Convert the markdown report to a styled PDF, save it on the server,
    and return a download URL so the browser can fetch it immediately.
    """
    require_admin(request)
    REPORTS_DIR.mkdir(exist_ok=True)

    file_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"emergency_report_{file_timestamp}.pdf"
    filepath = REPORTS_DIR / filename

    hst_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html_source = build_pdf_html(req.content.strip(), hst_timestamp)

    WeasyprintHTML(string=html_source).write_pdf(str(filepath))

    return JSONResponse({
        "filename": filename,
        "path": str(filepath),
        "download_url": f"/api/reports/download/{filename}",
    })


# ── Download Report ───────────────────────────────────────────────────────────

@app.get("/api/reports/download/{filename}")
async def download_report(filename: str, request: Request):
    require_admin(request)
    """Serve a saved PDF report as a browser download."""
    # Sanitise — no path traversal
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    filepath = REPORTS_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Report not found.")
    return FileResponse(
        path=str(filepath),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Health Check ──────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    generator = EmergencyReportGenerator()
    counts = db.get_counts()
    return {
        "status": "ok",
        "credentials_valid": generator.is_valid(),
        "missing": generator.validation_errors,
        "pending_submissions": counts["pending"],
        "total_submissions": counts["total"],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
