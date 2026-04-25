# Mythic Payload Builder

A web interface for building, managing, and deploying multi-stage payload chains to [Mythic C2](https://github.com/its-a-feature/Mythic).

> Built on top of the concepts from [mythic_payload_automation](https://github.com/hegusung/mythic_payload_automation).

---

## Features

- **Visual chain builder** — ordered stage cards (collapse/expand for a compact view)
- **Three stage types**:
  - **Base** — a Mythic agent (e.g. `netscan_agent`)
  - **Wrapper** — wraps a base or another wrapper (e.g. `netscan_packer`)
  - **Downloader** — hosts the wrapped payload on a C2 URL and delivers the download URL as a build parameter
- **Real-time deploy log** — Server-Sent Events stream showing each build step as it happens
- **Auto-cleanup** — previous payloads are deleted from Mythic before each redeploy
- **File parameters** — files are stored locally and uploaded to Mythic only at deploy time, with SHA-256 deduplication
- **Chain variables** — define `{{VAR_NAME}}` in chain variables, use them in any parameter value (resolved at deploy time)
- **ZIP export/import** — portable chain archives including referenced files, variables, and metadata
- **Payload download** — download built payloads directly from Mythic through the UI

---

## Requirements

- Docker & Docker Compose
- A running [Mythic C2](https://github.com/its-a-feature/Mythic) instance (v3+)

---

## Quick Start

```bash
git clone <repo-url>
cd mythic-payload-webapp
docker compose up -d
```

Open [http://localhost:7080](http://localhost:7080) in your browser.

Then go to **Settings** and configure your Mythic instance:
- **Mythic URL** — e.g. `https://192.168.1.100:7443`
- **Username / Password** — your Mythic credentials
- Click **Test Connection** to verify

---

## Architecture

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.13, FastAPI, SQLAlchemy, SQLite |
| Frontend | React 18, Vite, Tailwind CSS |
| Deployment | Docker Compose (nginx + uvicorn) |

**Ports:**
- `7080` — Frontend (nginx, public)
- `7081` — Backend API (localhost only, proxied through nginx at `/api/`)

---

## Chain Editor

### Stage Types

**Base stage** — deploys a Mythic payload type directly (must have a C2 profile configured).

**Wrapper stage** — wraps an upstream base or wrapper stage. Set the *Wraps* field to the label of the upstream stage.

**Downloader stage** — a special wrapper that:
1. Hosts the wrapped payload file on the C2 (via `c2HostFile`)
2. Builds a download URL from `Base URL + Profile URL`
3. Injects that URL into a build parameter (auto-detected as `downloader_url`)

### Chain Variables

Define key/value pairs in the **Variables** section of a chain. Reference them anywhere with `{{VAR_NAME}}`:

```
Variables:
  DOMAIN  = mytarget.example.com
  C2_HOST = https://mytarget.example.com:443

Usage in parameters:
  callback_domains = ["{{C2_HOST}}"]
  base_url         = {{C2_HOST}}
  label            = {{DOMAIN}}_agent.exe
```

Variables are resolved at deploy time — not stored in Mythic.

### File Parameters

When a build parameter is of type `File`:
1. Select the file in the UI → stored locally in the app's database
2. At deploy time → uploaded to Mythic, UUID substituted automatically
3. Same file content (same SHA-256) → reused, not re-uploaded

### Downloader Stage Fields

| Field | Description |
|-------|-------------|
| **Base URL** | Root URL of the C2 hosting endpoint, e.g. `https://{{DOMAIN}}` |
| **Profile URL** | URI path where the payload will be hosted, e.g. `/jquery.js` |
| **C2 Profile** | Which C2 profile handles the hosting |
| **Downloads** | Label of the upstream stage whose payload will be hosted |

Full download URL = `Base URL` + `Profile URL`

---

## ZIP Export / Import

Each chain can be exported as a `.zip` file containing:
- `chain.yaml` — human-readable chain definition (filenames instead of Mythic UUIDs, variables included)
- `files/` — all referenced file parameters
- `manifest.json` — file mapping metadata

On import, files are re-uploaded to the target Mythic instance and UUIDs are substituted automatically.

---

## Development

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev   # Vite dev server on :5173
```

For local dev, the frontend proxies `/api/` to `http://localhost:8000`.

---

## Docker Compose Reference

```yaml
# docker-compose.yml (summary)
services:
  backend:
    build: ./backend
    ports: ["127.0.0.1:7081:8000"]
    volumes: [backend_data:/data]

  frontend:
    build: ./frontend
    ports: ["0.0.0.0:7080:80"]
    depends_on: [backend]
```

Data is persisted in the `backend_data` Docker volume (SQLite database + uploaded files).

---

## Mythic Payload Type Detection

The app queries your Mythic instance to discover available payload types and classifies them automatically:

| Classification | Rule |
|---------------|------|
| **Base** | `wrapper = false` in Mythic |
| **Wrapper** | `wrapper = true`, no build param named `downloader_url` |
| **Downloader** | `wrapper = true`, has a build param named exactly `downloader_url` |

---

## License

MIT
