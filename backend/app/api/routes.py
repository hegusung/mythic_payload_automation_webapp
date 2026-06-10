from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.models.chain import ChainModel
from app.models.settings import SettingsModel
from app.schemas.chain import (
    ApplyRequest,
    ApplyResult,
    ChainCreate,
    ChainRead,
    ChainMythicPayloadsResponse,
    ChainStatusResponse,
    ChainUpdate,
    ComponentCatalogDebugResponse,
    ComponentsResponse,
    ConnectionTestResult,
    DeployRequest,
    ImportRequest,
    MythicPayloadInfo,
    MythicCallbackInfo,
    PreflightResult,
    SettingsRead,
    SettingsWrite,
    StatsResponse,
    PayloadTypeStat,
    ValidationResult,
)
from app.services.chain_codec import graph_to_json, graph_to_yaml, yaml_to_graph
from app.services.component_catalog import MythicCatalogError, fetch_component_catalog_debug, fetch_components, fetch_components_with_creds
from app.services.graph_validation import build_apply_preflight, validate_graph
from app.services.mythic_apply import MythicApplyError, apply_graph_to_mythic, describe_mythic_apply_error
from app.services import settings_service

router = APIRouter()


# ─── Health ───────────────────────────────────────────────────────────────────

@router.get('/health')
def health():
    return {'status': 'ok'}


# ─── Settings ─────────────────────────────────────────────────────────────────

def _effective_settings(db_data: dict) -> dict:
    """Merge DB settings with .env fallbacks (DB wins if set)."""
    return {
        'mythic_url':           db_data.get('mythic_url')           or settings.mythic_url,
        'mythic_username':      db_data.get('mythic_username')      or settings.mythic_username,
        'mythic_password':      db_data.get('mythic_password')      or settings.mythic_password,
        'payload_server_url':   db_data.get('payload_server_url')   or settings.payload_server_url,
        'payload_server_token': db_data.get('payload_server_token') or settings.payload_server_token,
    }


@router.get('/settings', response_model=SettingsRead)
def get_settings(db: Session = Depends(get_db)):
    data = _effective_settings(settings_service.get_all(db))
    return SettingsRead(
        mythic_url=data.get('mythic_url'),
        mythic_username=data.get('mythic_username'),
        mythic_password_set=bool(data.get('mythic_password')),
        payload_server_url=data.get('payload_server_url'),
        payload_server_token_set=bool(data.get('payload_server_token')),
    )


@router.put('/settings', response_model=SettingsRead)
def update_settings(payload: SettingsWrite, db: Session = Depends(get_db)):
    current = settings_service.get_all(db)
    # Only overwrite a field if it was explicitly provided (not None)
    # This allows each section (Mythic / Payload Server) to save independently
    update_data: dict[str, str | None] = dict(current)  # start from current values
    if payload.mythic_url           is not None: update_data['mythic_url']           = payload.mythic_url
    if payload.mythic_username      is not None: update_data['mythic_username']      = payload.mythic_username
    if payload.mythic_password      is not None: update_data['mythic_password']      = payload.mythic_password
    if payload.payload_server_url   is not None: update_data['payload_server_url']   = payload.payload_server_url
    if payload.payload_server_token is not None: update_data['payload_server_token'] = payload.payload_server_token
    settings_service.set_all(db, update_data)
    updated = _effective_settings(settings_service.get_all(db))
    return SettingsRead(
        mythic_url=updated.get('mythic_url'),
        mythic_username=updated.get('mythic_username'),
        mythic_password_set=bool(updated.get('mythic_password')),
        payload_server_url=updated.get('payload_server_url'),
        payload_server_token_set=bool(updated.get('payload_server_token')),
    )


@router.post('/settings/test', response_model=ConnectionTestResult)
async def test_connection(payload: SettingsWrite, db: Session = Depends(get_db)):
    from urllib.parse import urlparse
    from mythic import mythic as mythic_sdk

    # Fallback to stored/env values for any field not provided
    stored = settings_service.get_all(db)
    effective = _effective_settings(stored)
    url      = payload.mythic_url      or effective.get('mythic_url')
    username = payload.mythic_username or effective.get('mythic_username')
    password = payload.mythic_password or effective.get('mythic_password')

    if not url or not username or not password:
        return ConnectionTestResult(ok=False, message='URL, username and password are required. Save them first.')

    try:
        parsed = urlparse(url)
        if not parsed.hostname:
            return ConnectionTestResult(ok=False, message=f'Invalid URL: {url}')

        ssl = parsed.scheme == 'https'
        port = parsed.port or (7443 if ssl else 80)

        instance = await mythic_sdk.login(
            username=username,
            password=password,
            server_ip=parsed.hostname,
            server_port=port,
            ssl=ssl,
        )
        return ConnectionTestResult(ok=True, message='Connected successfully to Mythic.')
    except Exception as exc:
        return ConnectionTestResult(ok=False, message=f'Connection failed: {exc}')


from pydantic import BaseModel as _BaseModel
class PayloadServerTestIn(_BaseModel):
    payload_server_url: str | None = None
    payload_server_token: str | None = None


@router.post('/settings/test-payload-server', response_model=ConnectionTestResult)
async def test_payload_server(payload: PayloadServerTestIn, db: Session = Depends(get_db)):
    import httpx
    url = payload.payload_server_url
    token = payload.payload_server_token

    # Fallback to stored values if not provided
    if not url or not token:
        stored = _effective_settings(settings_service.get_all(db))
        url = url or stored.get('payload_server_url')
        token = token or stored.get('payload_server_token')

    if not url:
        return ConnectionTestResult(ok=False, message='Payload server URL is required.')
    if not token:
        return ConnectionTestResult(ok=False, message='Payload server token is required.')

    try:
        health_url = url.rstrip('/') + '/api/health'
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(health_url)
        if r.status_code != 200:
            return ConnectionTestResult(ok=False, message=f'Health check returned HTTP {r.status_code}.')

        # Verify token by hitting a protected endpoint
        files_url = url.rstrip('/') + '/api/files'
        async with httpx.AsyncClient(timeout=5) as client:
            r2 = await client.get(files_url, headers={'X-Token': token})
        if r2.status_code == 401:
            return ConnectionTestResult(ok=False, message='Server reachable but token is invalid (401).')
        if not r2.is_success:
            return ConnectionTestResult(ok=False, message=f'Auth check returned HTTP {r2.status_code}.')

        return ConnectionTestResult(ok=True, message='Connected successfully to payload-server.')
    except httpx.ConnectError:
        return ConnectionTestResult(ok=False, message=f'Cannot reach {url} — connection refused.')
    except httpx.TimeoutException:
        return ConnectionTestResult(ok=False, message=f'Connection to {url} timed out.')
    except Exception as exc:
        return ConnectionTestResult(ok=False, message=f'Connection failed: {exc}')


# ─── Stats ────────────────────────────────────────────────────────────────────

@router.get('/stats', response_model=StatsResponse)
async def stats(db: Session = Depends(get_db)):
    from app.core.config import settings as app_settings

    stored = settings_service.get_all(db)
    mythic_url = stored.get('mythic_url') or app_settings.mythic_url
    mythic_username = stored.get('mythic_username') or app_settings.mythic_username
    mythic_password = stored.get('mythic_password') or app_settings.mythic_password

    warnings: list[str] = []
    source = 'not_configured'
    components = []

    if mythic_url and mythic_username and mythic_password:
        try:
            source, components, warnings = await fetch_components_with_creds(
                mythic_url, mythic_username, mythic_password
            )
        except MythicCatalogError as exc:
            warnings.append(str(exc))
            source = 'error' 

    os_distribution: dict[str, int] = {}
    base_count = 0
    wrapper_count = 0
    running_count = 0
    stopped_count = 0
    payload_types: list[PayloadTypeStat] = []

    for comp in components:
        if comp.stage_type == 'wrapper':
            wrapper_count += 1
        else:
            base_count += 1

        is_running = True
        if 'container stopped' in (comp.description or '').lower():
            is_running = False
        if is_running:
            running_count += 1
        else:
            stopped_count += 1

        # Extract OS from description or default
        os_list: list[str] = []
        if 'OS:' in (comp.description or ''):
            os_part = comp.description.split('OS:')[1].split('|')[0].strip()
            os_list = [o.strip() for o in os_part.split(',') if o.strip()]
        if not os_list:
            os_list = ['Windows']

        for os_name in os_list:
            os_distribution[os_name] = os_distribution.get(os_name, 0) + 1

        payload_types.append(PayloadTypeStat(
            name=comp.type,
            stage_type=comp.stage_type,
            container_running=is_running,
            supported_os=os_list,
            description=comp.description or '',
        ))

    return StatsResponse(
        source=source,
        total=len(components),
        base=base_count,
        wrapper=wrapper_count,
        running=running_count,
        stopped=stopped_count,
        os_distribution=os_distribution,
        payload_types=payload_types,
        warnings=warnings,
    )


# ─── Payload Download ─────────────────────────────────────────────────────────────

@router.get('/payloads/{agent_file_id}/download')
async def download_mythic_payload(agent_file_id: str, filename: str | None = None, db: Session = Depends(get_db)):
    """Download a payload file from Mythic by its agent_file_id."""
    from urllib.parse import urlparse
    from mythic import mythic as mythic_sdk
    from app.core.config import settings as app_settings
    from fastapi.responses import Response

    stored = settings_service.get_all(db)
    mythic_url = stored.get('mythic_url') or app_settings.mythic_url
    mythic_username = stored.get('mythic_username') or app_settings.mythic_username
    mythic_password = stored.get('mythic_password') or app_settings.mythic_password

    if not mythic_url or not mythic_username or not mythic_password:
        raise HTTPException(status_code=400, detail='Mythic not configured.')

    try:
        parsed = urlparse(mythic_url)
        ssl_val = parsed.scheme == 'https'
        port = parsed.port or (7443 if ssl_val else 80)
        inst = await mythic_sdk.login(
            username=mythic_username, password=mythic_password,
            server_ip=parsed.hostname, server_port=port, ssl=ssl_val,
        )
        content = await mythic_sdk.download_file(mythic=inst, file_uuid=agent_file_id)
        if content is None:
            raise HTTPException(status_code=404, detail='File not found in Mythic.')
        # Resolve filename: query param > local cache > agent_file_id
        from app.models.file_cache import FileCache
        dl_filename = filename
        if not dl_filename:
            cached = db.query(FileCache).filter(FileCache.mythic_file_uuid == agent_file_id).first()
            if cached:
                dl_filename = cached.filename
        if not dl_filename:
            dl_filename = agent_file_id
        import re as _re
        safe = _re.sub(r'[^\w\-.]', '_', dl_filename)
        return Response(
            content=content,
            media_type='application/octet-stream',
            headers={'Content-Disposition': f'attachment; filename="{safe}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f'Download from Mythic failed: {exc}') from exc


# ─── Chain Status ─────────────────────────────────────────────────────────────

async def _get_chain_payload_count(row, db: Session) -> tuple[int, int]:
    """Returns (payload_count, active_callbacks). Returns (0,0) if Mythic unavailable."""
    from urllib.parse import urlparse
    from mythic import mythic as mythic_sdk
    from app.core.config import settings as app_settings
    import json as _json

    stored = settings_service.get_all(db)
    mythic_url = stored.get('mythic_url') or app_settings.mythic_url
    mythic_username = stored.get('mythic_username') or app_settings.mythic_username
    mythic_password = stored.get('mythic_password') or app_settings.mythic_password

    if not mythic_url or not mythic_username or not mythic_password:
        return 0, 0
    try:
        graph_data = _json.loads(row.graph_json)
        stage_names = {node['data']['label'] for node in graph_data.get('nodes', [])}
        chain_tag = row.mythic_tag or row.name
        tag_prefix = f'[chain:{chain_tag}]'

        parsed = urlparse(mythic_url)
        ssl_val = parsed.scheme == 'https'
        port = parsed.port or (7443 if ssl_val else 80)
        inst = await mythic_sdk.login(
            username=mythic_username, password=mythic_password,
            server_ip=parsed.hostname, server_port=port, ssl=ssl_val,
        )
        result = await mythic_sdk.execute_custom_query(mythic=inst, query=PAYLOADS_QUERY)
        count = 0
        callbacks = 0
        for p in result.get('payload', []):
            if p.get('deleted'):
                continue
            desc = p.get('description') or ''
            filename = (p.get('filemetum') or {}).get('filename_utf8', '')
            if tag_prefix in desc or any(s == filename or filename.startswith(s) for s in stage_names):
                count += 1
                callbacks += sum(1 for cb in (p.get('callbacks') or []) if cb.get('active'))
        return count, callbacks
    except Exception:
        return 0, 0


@router.get('/chains/{chain_id}/status', response_model=ChainStatusResponse)
async def chain_status(chain_id: int, db: Session = Depends(get_db)):
    row = db.get(ChainModel, chain_id)
    if not row:
        raise HTTPException(status_code=404, detail='Chain not found')
    count, cbs = await _get_chain_payload_count(row, db)
    return ChainStatusResponse(
        chain_id=chain_id, deployed=count > 0, payload_count=count, active_callbacks=cbs,
    )


# ─── File Upload ─────────────────────────────────────────────────────────────

@router.post('/files/upload')
async def upload_file_to_mythic(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload a file to Mythic and return its agent_file_id."""
    from urllib.parse import urlparse
    from mythic import mythic as mythic_sdk
    from app.core.config import settings as app_settings

    stored = settings_service.get_all(db)
    mythic_url = stored.get('mythic_url') or app_settings.mythic_url
    mythic_username = stored.get('mythic_username') or app_settings.mythic_username
    mythic_password = stored.get('mythic_password') or app_settings.mythic_password

    if not mythic_url or not mythic_username or not mythic_password:
        raise HTTPException(status_code=400, detail='Mythic not configured. Set credentials in Settings.')

    try:
        parsed = urlparse(mythic_url)
        ssl = parsed.scheme == 'https'
        port = parsed.port or (7443 if ssl else 80)
        inst = await mythic_sdk.login(
            username=mythic_username,
            password=mythic_password,
            server_ip=parsed.hostname,
            server_port=port,
            ssl=ssl,
        )
        contents = await file.read()
        file_id = await mythic_sdk.register_file(
            mythic=inst,
            filename=file.filename,
            contents=contents,
        )
        if not file_id:
            raise HTTPException(status_code=502, detail='Mythic returned no file_id after upload.')
        # Cache locally with sha256 for deduplication
        from app.models.file_cache import FileCache
        digest = _sha256(contents)
        existing = db.query(FileCache).filter(FileCache.sha256 == digest).first()
        if existing:
            existing.mythic_file_uuid = file_id
            existing.filename = file.filename
        else:
            db.add(FileCache(
                filename=file.filename,
                mythic_file_uuid=file_id,
                sha256=digest,
                content=contents,
                size=len(contents),
            ))
        db.commit()
        return {'file_id': file_id, 'filename': file.filename, 'size': len(contents)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f'File upload to Mythic failed: {exc}') from exc


# ─── Local File Store (no Mythic upload yet) ───────────────────────────

import hashlib as _hashlib

def _sha256(data: bytes) -> str:
    return _hashlib.sha256(data).hexdigest()

@router.post('/files/local')
async def store_file_locally(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Store a file in the local cache only — does NOT upload to Mythic.
    Returns {file_id: 'local:<sha256>', filename, size}.
    The file_id is stored in the graph and resolved at export/deploy time.
    """
    from app.models.file_cache import FileCache
    contents = await file.read()
    fname = file.filename or 'unnamed'
    digest = _sha256(contents)
    local_id = f'local:{digest}'
    # Upsert by sha256
    existing = db.query(FileCache).filter(FileCache.sha256 == digest).first()
    if existing:
        existing.filename = fname
    else:
        db.add(FileCache(
            filename=fname,
            mythic_file_uuid=None,
            sha256=digest,
            content=contents,
            size=len(contents),
        ))
    db.commit()
    return {'file_id': local_id, 'filename': fname, 'size': len(contents)}


# ─── File name resolution ───────────────────────────────────────────────────

from pydantic import BaseModel as _BaseModelFR
class FileRefsIn(_BaseModelFR):
    refs: list[str]

@router.post('/files/names')
def resolve_file_names(payload: FileRefsIn, db: Session = Depends(get_db)):
    """Resolve a list of file refs (local:<sha256> or Mythic UUID) to {ref: filename} map."""
    from app.models.file_cache import FileCache
    result: dict[str, str] = {}
    for ref in payload.refs:
        if not ref:
            continue
        if ref.startswith('local:'):
            sha = ref[len('local:'):]
            cached = db.query(FileCache).filter(FileCache.sha256 == sha).first()
            if cached:
                result[ref] = cached.filename
        else:
            # Mythic UUID
            cached = db.query(FileCache).filter(FileCache.mythic_file_uuid == ref).first()
            if cached:
                result[ref] = cached.filename
    return result


# ─── Export / Import ZIP ────────────────────────────────────────────────────

import io
import re
import zipfile

_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
_LOCAL_RE = re.compile(r'^local:[0-9a-f]{64}$')  # local:<sha256>


def _is_file_ref(val: str) -> bool:
    """Return True if val is a Mythic UUID or a local:<sha256> file reference."""
    return bool(_UUID_RE.match(val) or _LOCAL_RE.match(val))


def _find_file_uuids_in_graph(graph: dict) -> dict[str, str | None]:
    """Walk a chain graph and return {ref: None} for every file-param value (UUID or local:sha256).
    Searches both build parameters and C2 profile parameters.
    """
    refs: dict[str, str | None] = {}
    for node in (graph.get('nodes') or []):
        d = node.get('data') or {}
        # Build parameters
        for val in d.get('parameters', {}).values():
            if isinstance(val, str) and _is_file_ref(val):
                refs[val] = None
        # C2 profile parameters
        for prof in (d.get('c2_profiles') or []):
            for val in (prof.get('c2_profile_parameters') or {}).values():
                if isinstance(val, str) and _is_file_ref(val):
                    refs[val] = None
    return refs


@router.get('/chains/{chain_id}/export')
async def export_chain_zip(chain_id: int, db: Session = Depends(get_db)):
    """Export a chain as a ZIP: chain.yaml + referenced files + manifest.json."""
    from urllib.parse import urlparse
    from mythic import mythic as mythic_sdk
    from app.core.config import settings as app_settings
    from app.models.file_cache import FileCache
    import yaml as _yaml

    chain = db.query(ChainModel).filter(ChainModel.id == chain_id).first()
    if not chain:
        raise HTTPException(status_code=404, detail='Chain not found.')

    graph = json.loads(chain.graph_json) if isinstance(chain.graph_json, str) else (chain.graph_json or {})
    file_uuids = _find_file_uuids_in_graph(graph)

    # Resolve files: local cache first, then Mythic
    inst = None
    file_contents: dict[str, bytes] = {}   # uuid -> bytes
    uuid_to_name: dict[str, str] = {}      # uuid -> filename

    if file_uuids:
        stored = settings_service.get_all(db)
        mythic_url = stored.get('mythic_url') or app_settings.mythic_url
        mythic_username = stored.get('mythic_username') or app_settings.mythic_username
        mythic_password = stored.get('mythic_password') or app_settings.mythic_password

        for uuid in file_uuids:
            # Local file reference (local:<sha256>) — resolve from cache by sha256
            if uuid.startswith('local:'):
                sha = uuid[len('local:'):]
                cached = db.query(FileCache).filter(FileCache.sha256 == sha).first()
                if cached:
                    file_contents[uuid] = cached.content
                    uuid_to_name[uuid] = cached.filename
                else:
                    uuid_to_name[uuid] = f'{sha[:8]}.bin'
                continue
            cached = db.query(FileCache).filter(FileCache.mythic_file_uuid == uuid).first()
            if cached:
                file_contents[uuid] = cached.content
                uuid_to_name[uuid] = cached.filename
            elif mythic_url and mythic_username and mythic_password:
                # Fetch from Mythic
                if inst is None:
                    parsed = urlparse(mythic_url)
                    ssl_val = parsed.scheme == 'https'
                    port = parsed.port or (7443 if ssl_val else 80)
                    inst = await mythic_sdk.login(
                        username=mythic_username, password=mythic_password,
                        server_ip=parsed.hostname, server_port=port, ssl=ssl_val,
                    )
                try:
                    # Resolve filename from Mythic metadata
                    import gql as _gql
                    from mythic import mythic_utilities as _mu
                    meta = await _mu.graphql_post(
                        mythic=inst,
                        gql_query=_gql.gql('query GetFilename($uuid: String!) { filemeta(where: {agent_file_id: {_eq: $uuid}}) { filename } }'),
                        variables={'uuid': uuid},
                    )
                    raw_fname = ((meta.get('filemeta') or [{}])[0]).get('filename') or ''
                    # Mythic stores filenames as hex-escaped strings
                    if raw_fname.startswith('\\x'):
                        fname = bytes.fromhex(raw_fname[2:]).decode('utf-8', errors='replace')
                    else:
                        fname = raw_fname or f'{uuid[:8]}.bin'
                    content = await mythic_sdk.download_file(mythic=inst, file_uuid=uuid)
                    if content:
                        file_contents[uuid] = content
                        uuid_to_name[uuid] = fname
                        # Populate cache for future exports
                        existing = db.query(FileCache).filter(FileCache.mythic_file_uuid == uuid).first()
                        if not existing:
                            db.add(FileCache(filename=fname, mythic_file_uuid=uuid, content=content, size=len(content)))
                            db.commit()
                    else:
                        uuid_to_name[uuid] = fname
                except Exception:
                    uuid_to_name[uuid] = f'{uuid[:8]}.bin'
            else:
                uuid_to_name[uuid] = f'{uuid[:8]}.bin'

    # Build clean stages list (ordered by x position, no UI metadata)
    nodes = sorted(graph.get('nodes') or [], key=lambda n: n.get('position', {}).get('x', 0))

    stages = []
    for node in nodes:
        d = node.get('data') or {}
        # Replace file UUIDs with filenames
        params = {}
        for k, v in (d.get('parameters') or {}).items():
            params[k] = uuid_to_name[v] if isinstance(v, str) and _is_file_ref(v) and v in uuid_to_name else v

        stage: dict = {'label': d.get('label', ''), 'type': d.get('stage_type', 'base')}
        if d.get('payload'):         stage['payload'] = d['payload']
        if d.get('os'):              stage['os'] = d['os']
        # C2 profiles — substitute file refs in c2_profile_parameters
        c2p = d.get('c2_profiles') or []
        if c2p:
            resolved_c2p = []
            for prof in c2p:
                resolved_params = {
                    k: (uuid_to_name[v] if isinstance(v, str) and _is_file_ref(v) and v in uuid_to_name else v)
                    for k, v in (prof.get('c2_profile_parameters') or {}).items()
                }
                resolved_c2p.append({**prof, 'c2_profile_parameters': resolved_params})
            stage['c2_profiles'] = resolved_c2p
        elif d.get('c2_profile'):
            stage['c2_profile'] = d['c2_profile']
        # Downloader-specific
        if d.get('stage_type') == 'downloader':
            if d.get('base_url'):         stage['base_url'] = d['base_url']
            if d.get('profile_url'):      stage['profile_url'] = d['profile_url']
            if d.get('downloaded_payload'): stage['downloads'] = d['downloaded_payload']
        # Wrapper-specific
        if d.get('stage_type') == 'wrapper':
            if d.get('wrapped_payload'):  stage['wraps'] = d['wrapped_payload']
        if d.get('commands'):        stage['commands'] = d['commands']
        if params:                   stage['parameters'] = params
        stages.append(stage)

    chain_vars = json.loads(chain.variables) if chain.variables else {}
    chain_yaml = _yaml.dump({
        'name': chain.name,
        'mythic_tag': chain.mythic_tag or '',
        'description': chain.description or '',
        'variables': chain_vars,
        'stages': stages,
    }, allow_unicode=True, default_flow_style=False, sort_keys=False)

    manifest = {
        'chain_name': chain.name,
        'files': [{'filename': name, 'original_uuid': uuid} for uuid, name in uuid_to_name.items()],
    }

    # Build ZIP
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('chain.yaml', chain_yaml)
        zf.writestr('manifest.json', json.dumps(manifest, indent=2))
        for uuid, content in file_contents.items():
            name = uuid_to_name.get(uuid, f'{uuid[:8]}.bin')
            zf.writestr(f'files/{name}', content)
    buf.seek(0)

    from fastapi.responses import Response
    safe_name = re.sub(r'[^\w\-.]', '_', chain.name)
    return Response(
        content=buf.read(),
        media_type='application/zip',
        headers={'Content-Disposition': f'attachment; filename="{safe_name}.zip"'},
    )


@router.post('/chains/import')
async def import_chain_zip(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Import a chain ZIP: re-upload files to Mythic, substitute UUIDs, create chain."""
    from urllib.parse import urlparse
    from mythic import mythic as mythic_sdk
    from app.core.config import settings as app_settings
    from app.models.file_cache import FileCache
    import yaml as _yaml

    contents = await file.read()
    try:
        buf = io.BytesIO(contents)
        zf = zipfile.ZipFile(buf, 'r')
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail='Not a valid ZIP file.')

    names = zf.namelist()
    if 'chain.yaml' not in names:
        raise HTTPException(status_code=400, detail='Missing chain.yaml in ZIP.')

    chain_data = _yaml.safe_load(zf.read('chain.yaml'))
    manifest = json.loads(zf.read('manifest.json')) if 'manifest.json' in names else {'files': []}

    # Re-upload files to Mythic
    stored = settings_service.get_all(db)
    mythic_url = stored.get('mythic_url') or app_settings.mythic_url
    mythic_username = stored.get('mythic_username') or app_settings.mythic_username
    mythic_password = stored.get('mythic_password') or app_settings.mythic_password

    filename_to_new_uuid: dict[str, str] = {}
    if mythic_url and mythic_username and mythic_password:
        parsed = urlparse(mythic_url)
        ssl_val = parsed.scheme == 'https'
        port = parsed.port or (7443 if ssl_val else 80)
        inst = await mythic_sdk.login(
            username=mythic_username, password=mythic_password,
            server_ip=parsed.hostname, server_port=port, ssl=ssl_val,
        )
        for entry in manifest.get('files', []):
            fname = entry.get('filename')
            zip_path = f'files/{fname}'
            if fname and zip_path in names:
                file_bytes = zf.read(zip_path)
                new_uuid = await mythic_sdk.register_file(
                    mythic=inst, filename=fname, contents=file_bytes,
                )
                if new_uuid:
                    filename_to_new_uuid[fname] = new_uuid
                    cached = db.query(FileCache).filter(FileCache.mythic_file_uuid == new_uuid).first()
                    if not cached:
                        db.add(FileCache(
                            filename=fname,
                            mythic_file_uuid=new_uuid,
                            content=file_bytes,
                            size=len(file_bytes),
                        ))
        db.commit()

    # Rebuild graph from stages (new format) or legacy graph key
    import time as _time
    if 'stages' in chain_data:
        nodes = []
        # uuid_to_filename: reverse map for file_names reconstruction
        uuid_to_filename = {v: k for k, v in filename_to_new_uuid.items()}
        for i, stage in enumerate(chain_data.get('stages') or []):
            params = {}
            file_names: dict[str, str] = {}
            for k, v in (stage.get('parameters') or {}).items():
                if isinstance(v, str) and v in filename_to_new_uuid:
                    new_uuid = filename_to_new_uuid[v]
                    params[k] = new_uuid
                    file_names[k] = v  # original filename
                else:
                    params[k] = v
                    # If value is a UUID already known, restore its filename
                    if isinstance(v, str) and v in uuid_to_filename:
                        file_names[k] = uuid_to_filename[v]
            # Derive c2_profile string from c2_profiles array if not set
            c2_profiles_list = stage.get('c2_profiles') or []
            c2_profile_str = stage.get('c2_profile') or (c2_profiles_list[0].get('c2_profile') if c2_profiles_list else None)
            node_data = {
                'label': stage.get('label', f'stage_{i+1}'),
                'stage_type': stage.get('type', 'base'),
                'payload': stage.get('payload'),
                'os': stage.get('os', 'Windows'),
                'c2_profile': c2_profile_str,
                'c2_profiles': c2_profiles_list,
                'wrapped_payload': stage.get('wraps'),
                'downloaded_payload': stage.get('downloads'),
                'base_url': stage.get('base_url'),
                'profile_url': stage.get('profile_url'),
                'url_parameter': stage.get('url_parameter'),
                'commands': stage.get('commands', []),
                'parameters': params,
                'file_names': file_names,
            }
            nodes.append({
                'id': f'n{int(_time.time()*1000)+i}',
                'type': 'default',
                'position': {'x': 340 + i * 320, 'y': 100},
                'data': node_data,
            })
        # Rebuild edges from wrapped_payload/downloaded_payload references
        label_to_id = {n['data']['label']: n['id'] for n in nodes if n.get('data', {}).get('label')}
        edges = []
        for n in nodes:
            d = n.get('data', {})
            ref = d.get('wrapped_payload') or d.get('downloaded_payload')
            if ref and ref in label_to_id:
                src = label_to_id[ref]
                tgt = n['id']
                edges.append({'id': f'{src}->{tgt}', 'source': src, 'target': tgt})
        graph = {'nodes': nodes, 'edges': edges}
    else:
        # Legacy format with 'graph' key
        graph = chain_data.get('graph', {})
        for node in (graph.get('nodes') or []):
            d = node.get('data') or {}
            params = d.get('parameters', {})
            for key, val in params.items():
                if isinstance(val, str) and val in filename_to_new_uuid:
                    params[key] = filename_to_new_uuid[val]
            # Ensure c2_profile string is derived from c2_profiles array if absent
            if not d.get('c2_profile'):
                c2p = d.get('c2_profiles') or []
                if c2p and c2p[0].get('c2_profile'):
                    d['c2_profile'] = c2p[0]['c2_profile']

    # Deduplicate name
    base_name = chain_data.get('name', 'Imported chain')
    existing_names = {r[0] for r in db.query(ChainModel.name).all()}
    final_name = base_name
    suffix = 1
    while final_name in existing_names:
        final_name = f'{base_name} ({suffix})'
        suffix += 1

    imported_vars = chain_data.get('variables') or {}
    new_chain = ChainModel(
        name=final_name,
        mythic_tag=chain_data.get('mythic_tag') or None,
        description=chain_data.get('description', ''),
        variables=json.dumps(imported_vars) if imported_vars else None,
        graph_json=json.dumps(graph),
        yaml_content='',
    )
    db.add(new_chain)
    db.commit()
    db.refresh(new_chain)
    return {'id': new_chain.id, 'name': new_chain.name}


# ─── C2 Profiles ─────────────────────────────────────────────────────────────

@router.get('/c2profiles')
async def list_c2profiles(db: Session = Depends(get_db)):
    """List running non-P2P C2 profiles from Mythic."""
    from urllib.parse import urlparse
    from mythic import mythic as mythic_sdk, mythic_utilities
    import gql
    from app.core.config import settings as app_settings

    stored = settings_service.get_all(db)
    mythic_url = stored.get('mythic_url') or app_settings.mythic_url
    mythic_username = stored.get('mythic_username') or app_settings.mythic_username
    mythic_password = stored.get('mythic_password') or app_settings.mythic_password

    if not mythic_url or not mythic_username or not mythic_password:
        return {'profiles': [], 'warning': 'Mythic not configured.'}

    try:
        parsed = urlparse(mythic_url)
        ssl_val = parsed.scheme == 'https'
        port = parsed.port or (7443 if ssl_val else 80)
        inst = await mythic_sdk.login(
            username=mythic_username, password=mythic_password,
            server_ip=parsed.hostname, server_port=port, ssl=ssl_val,
        )
        result = await mythic_utilities.graphql_post(
            mythic=inst,
            gql_query=gql.gql(
                'query getC2Profiles { c2profile(where: {deleted: {_eq: false}, container_running: {_eq: true}, is_p2p: {_eq: false}}) { id name description } }'
            ),
        )
        profiles = [{'name': p['name'], 'description': p.get('description', '')} for p in result.get('c2profile', [])]
        return {'profiles': profiles}
    except Exception as exc:
        return {'profiles': [], 'warning': str(exc)}


# ─── Components ───────────────────────────────────────────────────────────────

@router.get('/components')
async def components(db: Session = Depends(get_db)):
    from fastapi.responses import JSONResponse
    from app.core.config import settings as app_settings

    stored = settings_service.get_all(db)
    mythic_url = stored.get('mythic_url') or app_settings.mythic_url
    mythic_username = stored.get('mythic_username') or app_settings.mythic_username
    mythic_password = stored.get('mythic_password') or app_settings.mythic_password

    no_cache_headers = {'Cache-Control': 'no-store, no-cache, must-revalidate'}

    if mythic_url and mythic_username and mythic_password:
        try:
            source, comps, warnings = await fetch_components_with_creds(
                mythic_url, mythic_username, mythic_password
            )
            resp = ComponentsResponse(source=source, components=comps, warnings=warnings)
        except MythicCatalogError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    else:
        try:
            source, comps, warnings = await fetch_components()
            resp = ComponentsResponse(source=source, components=comps, warnings=warnings)
        except MythicCatalogError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return JSONResponse(content=resp.model_dump(), headers=no_cache_headers)


@router.get('/components/debug', response_model=ComponentCatalogDebugResponse)
async def components_debug():
    try:
        source, raw_payload_types, warnings = await fetch_component_catalog_debug()
        return ComponentCatalogDebugResponse(source=source, raw_payload_types=raw_payload_types, warnings=warnings)
    except MythicCatalogError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ─── Chains ───────────────────────────────────────────────────────────────────

@router.get('/chains', response_model=list[ChainRead])
def list_chains(db: Session = Depends(get_db)):
    rows = db.query(ChainModel).order_by(ChainModel.updated_at.desc()).all()
    return [
        ChainRead(
            id=row.id,
            name=row.name,
            description=row.description,
            mythic_tag=row.mythic_tag,
            variables=json.loads(row.variables) if row.variables else {},
            yaml_content=row.yaml_content,
            graph=json.loads(row.graph_json),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.post('/chains', response_model=ChainRead)
def create_chain(payload: ChainCreate, db: Session = Depends(get_db)):
    yaml_content = graph_to_yaml(payload.graph)
    row = ChainModel(
        name=payload.name,
        description=payload.description,
        mythic_tag=payload.mythic_tag,
        variables=json.dumps(payload.variables) if payload.variables else None,
        yaml_content=yaml_content,
        graph_json=graph_to_json(payload.graph),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ChainRead(
        id=row.id,
        name=row.name,
        description=row.description,
        mythic_tag=row.mythic_tag,
        variables=payload.variables,
        yaml_content=row.yaml_content,
        graph=payload.graph,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.put('/chains/{chain_id}', response_model=ChainRead)
def update_chain(chain_id: int, payload: ChainUpdate, db: Session = Depends(get_db)):
    row = db.get(ChainModel, chain_id)
    if not row:
        raise HTTPException(status_code=404, detail='Chain not found')
    row.name = payload.name
    row.description = payload.description
    row.mythic_tag = payload.mythic_tag
    row.variables = json.dumps(payload.variables) if payload.variables else None
    row.graph_json = graph_to_json(payload.graph)
    row.yaml_content = graph_to_yaml(payload.graph)
    db.add(row)
    db.commit()
    db.refresh(row)
    return ChainRead(
        id=row.id,
        name=row.name,
        description=row.description,
        mythic_tag=row.mythic_tag,
        variables=payload.variables,
        yaml_content=row.yaml_content,
        graph=payload.graph,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.delete('/chains/{chain_id}')
def delete_chain(chain_id: int, db: Session = Depends(get_db)):
    row = db.get(ChainModel, chain_id)
    if not row:
        raise HTTPException(status_code=404, detail='Chain not found')
    db.delete(row)
    db.commit()
    return {'ok': True}


@router.get('/chains/{chain_id}/deploy/stream')
async def deploy_chain_stream(chain_id: int, db: Session = Depends(get_db)):
    """Deploy a chain with SSE streaming of progress events."""
    from fastapi.responses import StreamingResponse
    from urllib.parse import urlparse
    from mythic import mythic as mythic_sdk
    from app.core.config import settings as app_settings
    from app.schemas.chain import GraphDocument
    import json as _json
    import asyncio

    row = db.get(ChainModel, chain_id)
    if not row:
        raise HTTPException(status_code=404, detail='Chain not found')

    stored = settings_service.get_all(db)
    mythic_url = stored.get('mythic_url') or app_settings.mythic_url
    mythic_username = stored.get('mythic_username') or app_settings.mythic_username
    mythic_password = stored.get('mythic_password') or app_settings.mythic_password

    async def event_stream():
        def sse(data: dict) -> str:
            return f'data: {_json.dumps(data)}\n\n'

        try:
            yield sse({'type': 'log', 'level': 'info', 'msg': f'Starting deploy of chain "{row.name}"...'})

            if not mythic_url or not mythic_username or not mythic_password:
                yield sse({'type': 'error', 'msg': 'Mythic not configured. Set credentials in Settings.'})
                return

            parsed = urlparse(mythic_url)
            ssl_val = parsed.scheme == 'https'
            port = parsed.port or (7443 if ssl_val else 80)

            yield sse({'type': 'log', 'level': 'info', 'msg': 'Connecting to Mythic...'})
            inst = await mythic_sdk.login(
                username=mythic_username, password=mythic_password,
                server_ip=parsed.hostname, server_port=port, ssl=ssl_val,
            )
            yield sse({'type': 'log', 'level': 'success', 'msg': f'Connected to {mythic_url}'})

            # Delete previous payloads
            yield sse({'type': 'log', 'level': 'info', 'msg': 'Removing previous payloads...'})
            del_result = await _delete_chain_payloads_from_mythic(row, inst, db)
            if del_result['deleted'] > 0:
                yield sse({'type': 'log', 'level': 'info', 'msg': f'  Deleted {del_result["deleted"]} old payload(s)'})
            else:
                yield sse({'type': 'log', 'level': 'info', 'msg': '  No previous payloads found'})

            # Build graph
            graph_data = _json.loads(row.graph_json)
            graph = GraphDocument(**graph_data)
            _vars = _json.loads(row.variables) if row.variables else {}
            apply_req = ApplyRequest(name=row.name, description=row.description, graph=graph, variables=_vars)

            # Progress callback
            async def on_progress(event: dict):
                yield_queue.put_nowait(sse(event))

            yield_queue: asyncio.Queue = asyncio.Queue()

            async def run_deploy():
                from app.services.mythic_apply import MythicApplyError, apply_graph_to_mythic, describe_mythic_apply_error
                try:
                    result = await apply_graph_to_mythic(
                        apply_req, db=db, mythic_tag=row.mythic_tag,
                        progress_cb=on_progress,
                    )
                    yield_queue.put_nowait(sse({'type': 'done', 'result': result.model_dump()}))
                except MythicApplyError as exc:
                    yield_queue.put_nowait(sse({'type': 'error', 'msg': describe_mythic_apply_error(exc)}))
                except Exception as exc:
                    yield_queue.put_nowait(sse({'type': 'error', 'msg': str(exc)}))
                finally:
                    yield_queue.put_nowait(None)  # sentinel

            deploy_task = asyncio.create_task(run_deploy())

            while True:
                item = await yield_queue.get()
                if item is None:
                    break
                yield item

        except Exception as exc:
            yield sse({'type': 'error', 'msg': f'Deploy failed: {exc}'})

    return StreamingResponse(
        event_stream(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )


@router.post('/chains/{chain_id}/deploy', response_model=ApplyResult)
async def deploy_chain(chain_id: int, db: Session = Depends(get_db)):
    """Deploy a saved chain to Mythic — creates payloads stage by stage."""
    row = db.get(ChainModel, chain_id)
    if not row:
        raise HTTPException(status_code=404, detail='Chain not found')

    import json as _json
    graph_data = _json.loads(row.graph_json)
    from app.schemas.chain import GraphDocument
    graph = GraphDocument(**graph_data)

    variables = json.loads(row.variables) if row.variables else {}
    apply_req = ApplyRequest(name=row.name, description=row.description, graph=graph, variables=variables)

    try:
        # Delete previous payloads before redeploying
        from urllib.parse import urlparse
        from mythic import mythic as mythic_sdk
        from app.core.config import settings as app_settings
        stored = settings_service.get_all(db)
        mythic_url = stored.get('mythic_url') or app_settings.mythic_url
        mythic_username = stored.get('mythic_username') or app_settings.mythic_username
        mythic_password = stored.get('mythic_password') or app_settings.mythic_password
        if mythic_url and mythic_username and mythic_password:
            parsed = urlparse(mythic_url)
            ssl_val = parsed.scheme == 'https'
            port = parsed.port or (7443 if ssl_val else 80)
            inst = await mythic_sdk.login(
                username=mythic_username, password=mythic_password,
                server_ip=parsed.hostname, server_port=port, ssl=ssl_val,
            )
            await _delete_chain_payloads_from_mythic(row, inst, db)

        result = await apply_graph_to_mythic(apply_req, db=db, mythic_tag=row.mythic_tag)
        return result
    except MythicApplyError as exc:
        raise HTTPException(status_code=400, detail=describe_mythic_apply_error(exc)) from exc


PAYLOADS_QUERY = """
query GetPayloads {
  payload(order_by: {creation_time: desc}) {
    uuid
    description
    build_phase
    os
    deleted
    creation_time
    filemetum {
      agent_file_id
      filename_utf8
      md5
      sha1
    }
    payloadtype {
      name
    }
    callbacks {
      id
      agent_callback_id
      last_checkin
      active
      host
      user
    }
  }
}
"""


DELETE_PAYLOAD_MUTATION = """
mutation DeletePayload($uuid: String!) {
  updatePayload(payload_uuid: $uuid, deleted: true) {
    status
    error
  }
}
"""


async def _delete_chain_payloads_from_mythic(row: ChainModel, inst, db) -> dict:
    """Delete all Mythic payloads belonging to a chain. Requires an authenticated Mythic client."""
    from mythic import mythic as mythic_sdk
    import json as _json

    graph_data = _json.loads(row.graph_json)
    stage_names = {node['data']['label'] for node in graph_data.get('nodes', [])}
    chain_tag = row.mythic_tag or row.name
    tag_prefix = f'[chain:{chain_tag}]'

    result = await mythic_sdk.execute_custom_query(mythic=inst, query=PAYLOADS_QUERY)
    all_payloads = result.get('payload', [])

    to_delete = []
    for p in all_payloads:
        if p.get('deleted'):
            continue
        desc = p.get('description') or ''
        filename = (p.get('filemetum') or {}).get('filename_utf8', '')
        if tag_prefix in desc or any(s == filename or filename.startswith(s) for s in stage_names):
            to_delete.append(p['uuid'])

    deleted_uuids = []
    errors = []
    for uuid in to_delete:
        try:
            del_result = await mythic_sdk.execute_custom_query(
                mythic=inst,
                query=DELETE_PAYLOAD_MUTATION,
                variables={'uuid': uuid},
            )
            status = (del_result.get('updatePayload') or {}).get('status')
            if status == 'success':
                deleted_uuids.append(uuid)
            else:
                err = (del_result.get('updatePayload') or {}).get('error', 'unknown error')
                errors.append(f'{uuid[:8]}...: {err}')
        except Exception as exc:
            errors.append(f'{uuid[:8]}...: {exc}')

    return {'deleted': len(deleted_uuids), 'uuids': deleted_uuids, 'errors': errors}


@router.delete('/chains/{chain_id}/payloads')
async def delete_chain_mythic_payloads(chain_id: int, db: Session = Depends(get_db)):
    """Mark all Mythic payloads belonging to this chain as deleted."""
    from urllib.parse import urlparse
    from mythic import mythic as mythic_sdk
    from app.core.config import settings as app_settings

    row = db.get(ChainModel, chain_id)
    if not row:
        raise HTTPException(status_code=404, detail='Chain not found')

    stored = settings_service.get_all(db)
    mythic_url = stored.get('mythic_url') or app_settings.mythic_url
    mythic_username = stored.get('mythic_username') or app_settings.mythic_username
    mythic_password = stored.get('mythic_password') or app_settings.mythic_password

    if not mythic_url or not mythic_username or not mythic_password:
        raise HTTPException(status_code=400, detail='Mythic not configured.')

    try:
        parsed = urlparse(mythic_url)
        ssl = parsed.scheme == 'https'
        port = parsed.port or (7443 if ssl else 80)
        inst = await mythic_sdk.login(
            username=mythic_username, password=mythic_password,
            server_ip=parsed.hostname, server_port=port, ssl=ssl,
        )
        result = await _delete_chain_payloads_from_mythic(row, inst, db)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f'Failed to delete payloads: {exc}') from exc

    if result['deleted'] == 0 and not result.get('uuids'):
        return {'deleted': 0, 'uuids': [], 'message': 'No matching payloads found in Mythic.'}
    return {
        **result,
        'message': f'Deleted {result["deleted"]} payload(s) from Mythic.',
    }


@router.get('/chains/{chain_id}/payloads', response_model=ChainMythicPayloadsResponse)
async def chain_mythic_payloads(chain_id: int, db: Session = Depends(get_db)):
    """Fetch Mythic payloads that belong to this chain (matched by chain tag in description or stage filenames)."""
    from urllib.parse import urlparse
    from mythic import mythic as mythic_sdk
    from app.core.config import settings as app_settings

    row = db.get(ChainModel, chain_id)
    if not row:
        raise HTTPException(status_code=404, detail='Chain not found')

    stored = settings_service.get_all(db)
    mythic_url = stored.get('mythic_url') or app_settings.mythic_url
    mythic_username = stored.get('mythic_username') or app_settings.mythic_username
    mythic_password = stored.get('mythic_password') or app_settings.mythic_password

    warnings: list[str] = []

    if not mythic_url or not mythic_username or not mythic_password:
        return ChainMythicPayloadsResponse(
            chain_name=row.name,
            mythic_tag=row.mythic_tag,
            payloads=[],
            warnings=['Mythic not configured. Set credentials in Settings.'],
        )

    # Build match criteria: chain tag prefix OR stage filenames
    import json as _json
    graph_data = _json.loads(row.graph_json)
    stage_names = {node['data']['label'] for node in graph_data.get('nodes', [])}
    chain_tag = row.mythic_tag or row.name
    tag_prefix = f'[chain:{chain_tag}]'

    try:
        parsed = urlparse(mythic_url)
        ssl = parsed.scheme == 'https'
        port = parsed.port or (7443 if ssl else 80)

        inst = await mythic_sdk.login(
            username=mythic_username,
            password=mythic_password,
            server_ip=parsed.hostname,
            server_port=port,
            ssl=ssl,
        )
        result = await mythic_sdk.execute_custom_query(mythic=inst, query=PAYLOADS_QUERY)
        all_payloads = result.get('payload', [])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f'Failed to query Mythic: {exc}') from exc

    matched: list[MythicPayloadInfo] = []
    for p in all_payloads:
        if p.get('deleted'):
            continue
        desc = p.get('description') or ''
        filename = (p.get('filemetum') or {}).get('filename_utf8', '')
        # Match by chain tag in description OR by stage name matching filename
        is_match = (
            tag_prefix in desc
            or any(s == filename or filename.startswith(s) for s in stage_names)
        )
        if not is_match:
            continue

        callbacks = [
            MythicCallbackInfo(
                id=cb['id'],
                agent_callback_id=cb.get('agent_callback_id', ''),
                last_checkin=str(cb.get('last_checkin', '')) if cb.get('last_checkin') else None,
                active=bool(cb.get('active')),
                host=cb.get('host'),
                user=cb.get('user'),
            )
            for cb in (p.get('callbacks') or [])
        ]

        matched.append(MythicPayloadInfo(
            uuid=p['uuid'],
            agent_file_id=(p.get('filemetum') or {}).get('agent_file_id'),
            filename=filename,
            payload_type=(p.get('payloadtype') or {}).get('name', '?'),
            build_phase=p.get('build_phase', '?'),
            os=p.get('os'),
            description=desc,
            creation_time=str(p.get('creation_time', '')) if p.get('creation_time') else None,
            md5=(p.get('filemetum') or {}).get('md5'),
            sha1=(p.get('filemetum') or {}).get('sha1'),
            callbacks=callbacks,
        ))

    if not matched:
        warnings.append(f'No Mythic payloads found matching chain tag "{tag_prefix}" or stage names {sorted(stage_names)}.')

    return ChainMythicPayloadsResponse(
        chain_name=row.name,
        mythic_tag=row.mythic_tag,
        payloads=matched,
        warnings=warnings,
    )


# ─── Import / Validate / Apply ────────────────────────────────────────────────

@router.post('/import', response_model=ValidationResult)
def import_yaml(payload: ImportRequest):
    try:
        graph = yaml_to_graph(payload.yaml_content)
        yaml_content = graph_to_yaml(graph)
        return ValidationResult(valid=True, warnings=[], errors=[], yaml_content=yaml_content, graph=graph)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/validate', response_model=ValidationResult)
def validate(payload: ChainCreate):
    validation = validate_graph(payload.graph, for_apply=False)
    try:
        yaml_content = graph_to_yaml(payload.graph)
    except Exception as exc:
        validation.errors.append(str(exc))
        yaml_content = ''

    return ValidationResult(
        valid=validation.valid,
        warnings=validation.warnings,
        errors=validation.errors,
        yaml_content=yaml_content,
        graph=payload.graph,
    )


@router.post('/preflight', response_model=PreflightResult)
def preflight(payload: ApplyRequest):
    try:
        yaml_content = graph_to_yaml(payload.graph)
    except Exception:
        yaml_content = ''
    return build_apply_preflight(payload.graph, yaml_content=yaml_content)


@router.post('/apply', response_model=ApplyResult)
async def apply_to_mythic(payload: ApplyRequest):
    preflight_result = build_apply_preflight(payload.graph)
    if not preflight_result.can_apply:
        raise HTTPException(status_code=400, detail=' | '.join(preflight_result.blockers))

    try:
        return await apply_graph_to_mythic(payload)
    except MythicApplyError as exc:
        raise HTTPException(status_code=400, detail=describe_mythic_apply_error(exc)) from exc


@router.get('/samples')
def samples():
    root = Path(__file__).resolve().parents[3] / 'samples' / 'original_examples'
    output = []
    for path in sorted(root.glob('*.yml')):
        content = path.read_text(encoding='utf-8')
        output.append({'name': path.name, 'yaml_content': content})
    return output
