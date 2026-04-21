# AlohaAI Emergency Watchtower

A real-time emergency reporting and AI-powered briefing system built for the **Hawaiian Volcano Education & Resilience Institute (HVERI)**. Deployed at [watchtower.kaipoi.site](https://watchtower.kaipoi.site).

Citizens submit incident reports during natural disasters. Emergency coordinators receive AI-generated briefings organised by district, with priority items surfaced automatically.

---

## Features

**Citizen-facing**
- Structured incident submission form (incident type, district, location, severity, evacuation status)
- Cloudflare Turnstile bot protection
- Rate limited to prevent spam (3 submissions per 10 minutes per IP)
- Reference code generated on submission for follow-up

**Admin panel**
- Protected by username/password login with bcrypt hashing and signed session cookies
- Rate limited login (5 attempts per minute per IP)
- Real-time submission dashboard with district and severity filtering
- One-click report generation via Claude AI
- PDF report download for offline use and distribution

**AI Report Generation**
- Two-stage map/reduce pipeline using Claude Sonnet
- Stage 1: Organises submissions by Hawaii Island district, flags urgent items
- Stage 2: Generates plain-language briefing for mixed audience — civil defense coordinators, first responders, community administrators
- Rolling event context — each report cycle builds on prior summaries without re-processing historical data
- Reports streamed live to admin panel via Server-Sent Events (SSE)

**Security**
- Key-only SSH access
- UFW firewall — ports 80, 443, SSH only
- Fail2Ban on SSH
- Nginx reverse proxy with SSL (Let's Encrypt)
- `ProtectSystem`, `NoNewPrivileges` systemd hardening
- Kernel hardening — SYN flood, IP spoofing, martian packet protection
- auditd logging

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.13, FastAPI, uvicorn |
| AI | Anthropic Claude Sonnet (claude-sonnet-4-5) |
| Database | SQLite |
| PDF generation | WeasyPrint |
| Auth | passlib (bcrypt), itsdangerous (signed cookies) |
| Rate limiting | slowapi |
| Bot protection | Cloudflare Turnstile |
| Frontend | Vanilla HTML/CSS/JS |
| Server | Nginx, Debian 13, DigitalOcean |
| SSL | Let's Encrypt via Certbot |

---

## Project Structure

```
watchtower/
├── backend/
│   ├── main.py          # FastAPI app — routes, auth, SSE streaming
│   └── watchtower.py    # Core logic — SQLite, Claude AI report generation
├── frontend/
│   ├── user.html        # Citizen submission form (public)
│   ├── admin.html       # Admin dashboard
│   ├── login.html       # Admin login page
│   ├── change_password.html  # First-login password change
│   ├── app.js           # Admin panel JavaScript
│   └── styles.css       # Shared styles
├── manage_admins.py     # CLI tool for admin account management
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
├── watchtower.service.txt   # Systemd service unit
└── nginx-watchtower.conf.txt  # Nginx config template
```

---

## Setup

### Prerequisites
- Python 3.11+
- Nginx
- Certbot (for SSL)
- An [Anthropic API key](https://console.anthropic.com)

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/HVERI-AlohaAI-Watchtower.git
cd HVERI-AlohaAI-Watchtower
```

### 2. Create virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example watchtower/.env
nano watchtower/.env
```

Fill in your `ANTHROPIC_API_KEY`, `SECRET_KEY`, and optionally `TURNSTILE_SECRET_KEY`. See `.env.example` for details.

### 4. Create your first admin account

```bash
python manage_admins.py add --username admin --email you@example.com
```

This generates a temporary password. The admin will be prompted to change it on first login.

### 5. Deploy with systemd and Nginx

Copy `watchtower.service.txt` to `/etc/systemd/system/watchtower.service` and `nginx-watchtower.conf.txt` to `/etc/nginx/sites-available/watchtower`. Update paths and domain names as needed.

```bash
sudo systemctl enable --now watchtower
sudo certbot --nginx -d yourdomain.com
```

---

## Admin Account Management

All admin management is done via CLI on the server — no web interface. This keeps account creation behind SSH access.

```bash
# Add a new admin (generates temp password)
python manage_admins.py add --username noah --email noah@example.com

# List all admins
python manage_admins.py list

# Reset a password (generates new temp password)
python manage_admins.py reset --email noah@example.com

# Delete an admin
python manage_admins.py delete --email noah@example.com
```

---

## Security Notes

- **Never commit `.env`** — it contains your API keys and session secret
- The `.gitignore` excludes `.env`, `*.db`, and `watchtower_reports/` automatically
- The SQLite database contains citizen submissions and admin password hashes — keep it off version control and back it up separately
- Session cookies are `httponly`, `secure`, and `samesite=lax` — safe over HTTPS only
- Passwords are bcrypt hashed with a cost factor appropriate for interactive logins

---

## Built By

[kaipoi](https://github.com/kaipoi) — Hawaiian Volcano Education & Resilience Institute (HVERI)
