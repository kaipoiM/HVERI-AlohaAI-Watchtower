# AlohaAI Emergency Watchtower

A real-time emergency reporting and AI-powered briefing system built for the **Hawaiian Volcano Education & Resilience Institute (HVERI)**. Deployed at (subject to change) [https://watchtower.hveri.org](https://watchtower.kaipoi.site).

Citizens submit incident reports during natural disasters. Emergency coordinators receive AI-generated briefings organised by district, with priority items surfaced automatically.

---

## Features

**Citizen UI**
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
- Stage 2: Generates plain-language briefing for mixed audience (civil defense coordinators, first responders, community administrators)
- Rolling event context (each report cycle builds on prior summaries without re-processing historical data)
- Reports streamed live to admin panel via Server-Sent Events (SSE)

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
HVERI-AlohaAI-Watchtower/
├── Demos/                        # Early HTML demos and prototypes
├── Prototype/                    # Original Kivy desktop app prototype
├── Scripts/                      # Utility scripts and Graph API tools
├── Watchtower/                   # <-- Full production application
│   ├── backend/
│   │   ├── main.py               # FastAPI app (routes, auth, SSE streaming)
│   │   └── watchtower.py         # Core logic (SQLite, Claude AI report generation)
│   ├── frontend/
│   │   ├── user.html             # Citizen submission form (public)
│   │   ├── admin.html            # Admin dashboard
│   │   ├── login.html            # Admin login page
│   │   ├── change_password.html  # First-login password change
│   │   ├── app.js                # Admin panel JavaScript
│   │   └── styles.css            # Shared styles (light + dark mode)
│   ├── manage_admins.py          # CLI tool for admin account management
│   ├── requirements.txt          # Python dependencies
│   ├── .env.example              # Environment variable template
│   ├── watchtower.service.txt    # Systemd service unit
│   └── nginx-watchtower.conf.txt # Nginx reverse proxy config
└── README.md
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
git clone https://github.com/kaipoiM/HVERI-AlohaAI-Watchtower.git
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

All admin management is done via CLI on the server, no web interface. This keeps account creation behind SSH access.

```bash
# Add a new admin (generates temp password)
python manage_admins.py add --username name --email name@example.com

# List all admins
python manage_admins.py list

# Reset a password (generates new temp password)
python manage_admins.py reset --email name@example.com

# Delete an admin
python manage_admins.py delete --email name@example.com
```

## Built By

[Kaipoi M.](https://github.com/kaipoiM) and [Noah G.](https://github.com/NoahGamble) for Hawaiian Volcano Education & Resilience Institute (HVERI)
