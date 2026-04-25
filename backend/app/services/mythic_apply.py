from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import gql
from mythic import mythic, mythic_utilities

from app.core.config import settings
from app.schemas.chain import ApplyRequest, ApplyResult, ApplyStageResult, GraphDocument
from app.services.component_catalog import _parse_mythic_connection
from app.services import settings_service


class MythicApplyError(RuntimeError):
    pass


class MythicApplyStageError(MythicApplyError):
    def __init__(self, message: str, *, stage_label: str | None = None, suggestion: str | None = None):
        super().__init__(message)
        self.stage_label = stage_label
        self.suggestion = suggestion


async def _login_to_mythic(db=None):
    """Login using DB settings first, then fall back to env vars."""
    from urllib.parse import urlparse

    mythic_url = None
    mythic_username = None
    mythic_password = None

    if db is not None:
        stored = settings_service.get_all(db)
        mythic_url = stored.get('mythic_url')
        mythic_username = stored.get('mythic_username')
        mythic_password = stored.get('mythic_password')

    mythic_url = mythic_url or settings.mythic_url
    mythic_username = mythic_username or settings.mythic_username
    mythic_password = mythic_password or settings.mythic_password

    if not mythic_url:
        raise MythicApplyError('Mythic URL is not configured. Set it in the Settings page.')
    if not mythic_username or not mythic_password:
        raise MythicApplyError('Mythic credentials are incomplete. Set them in the Settings page.')

    parsed = urlparse(mythic_url)
    if not parsed.hostname:
        raise MythicApplyError(f'Invalid Mythic URL: {mythic_url}')

    ssl = parsed.scheme == 'https'
    port = parsed.port or (7443 if ssl else 80)

    try:
        return await mythic.login(
            username=mythic_username,
            password=mythic_password,
            server_ip=parsed.hostname,
            server_port=port,
            ssl=ssl,
        )
    except Exception as exc:
        raise MythicApplyError(
            'Could not log in to Mythic. Check the Settings page and server reachability.'
        ) from exc


def _build_parameter_list(parameters: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the build_parameters list for Mythic.
    Parameters with None or empty-string values are skipped
    (Mythic errors on empty File UUIDs and some other types).
    """
    output: list[dict[str, Any]] = []
    for key, value in parameters.items():
        # Skip null/empty values — Mythic errors on empty File params especially
        if value is None or value == '':
            continue
        # Mythic expects certain types natively:
        # - Arrays must be a JSON string OR a real list, not a Python list
        # - Booleans as Python bool are fine
        # - Numbers as int/float are fine
        # - Strings as str
        if isinstance(value, list):
            # Lists must be passed as native Python lists — the SDK does json.dumps internally
            normalized = value
        elif isinstance(value, dict):
            normalized = value
        elif isinstance(value, str):
            # JSON array/object strings must be parsed to native Python types
            # so the SDK serialises them correctly (not as escaped strings)
            stripped = value.strip()
            if stripped.startswith('[') or stripped.startswith('{'):
                try:
                    normalized = json.loads(stripped)
                except Exception:
                    normalized = value
            else:
                normalized = value
        else:
            normalized = value
        output.append({'name': key, 'value': normalized})
    return output


def _normalize_c2_profiles(c2_profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize C2 profile parameter values for Mythic.
    
    Arrays must be passed as Python lists (Mythic serializes them internally).
    Strings that look like JSON arrays/objects are parsed into native types.
    """
    output = []
    for profile in c2_profiles:
        params = profile.get('c2_profile_parameters') or {}
        normalized_params: dict[str, Any] = {}
        for key, value in params.items():
            # Skip null/empty values — Mythic errors on empty File params (e.g. raw_c2_config)
            if value is None or value == '':
                continue
            if isinstance(value, list):
                normalized_params[key] = value
            elif isinstance(value, dict):
                normalized_params[key] = value
            elif isinstance(value, str):
                stripped = value.strip()
                if stripped.startswith('[') or stripped.startswith('{'):
                    try:
                        normalized_params[key] = json.loads(stripped)
                    except Exception:
                        normalized_params[key] = value
                else:
                    normalized_params[key] = value
            else:
                normalized_params[key] = value
        output.append({**profile, 'c2_profile_parameters': normalized_params})
    return output


def _resolve_payload_type(label: str, payload_type: str | None) -> str:
    resolved = (payload_type or '').strip()
    if not resolved:
        raise MythicApplyStageError(
            f'{label}: select a payload type before applying this stage to Mythic.',
            stage_label=label,
            suggestion='Pick a Mythic payload type in the inspector before retrying.',
        )
    return resolved


def _ordered_node_ids(graph: GraphDocument) -> list[str]:
    node_map = {node.id: node for node in graph.nodes}
    indegree = defaultdict(int)
    children: dict[str, list[str]] = defaultdict(list)

    for edge in graph.edges:
        if edge.source not in node_map or edge.target not in node_map:
            raise MythicApplyError('The graph contains an invalid edge reference.')
        indegree[edge.target] += 1
        indegree.setdefault(edge.source, 0)
        children[edge.source].append(edge.target)

    queue = sorted([node_id for node_id in node_map if indegree[node_id] == 0])
    ordered: list[str] = []
    while queue:
        current = queue.pop(0)
        ordered.append(current)
        for child in sorted(children[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
                queue.sort()

    if len(ordered) != len(graph.nodes):
        raise MythicApplyError('The graph contains a cycle or an invalid reference.')

    return ordered


def _normalize_mythic_error(raw: Any, *, label: str, stage_type: str) -> str:
    text = str(raw or '').strip()
    lowered = text.lower()
    prefix = f'{stage_type.capitalize()} stage {label}'

    if not text:
        return f'{prefix} failed in Mythic without returning an error message.'
    if 'status code 401' in lowered or 'unauthorized' in lowered or 'forbidden' in lowered:
        return f'{prefix} could not authenticate to Mythic. Verify the configured username and password.'
    if 'timed out' in lowered or 'timeout' in lowered:
        return f'{prefix} timed out while Mythic was building it. Check Mythic tasking/build worker status and retry.'
    if 'connection refused' in lowered or 'failed to establish a new connection' in lowered or 'max retries exceeded' in lowered:
        return f'{prefix} could not reach Mythic. Check the server URL, port, TLS setting, and network path.'
    if 'payload type' in lowered and ('not found' in lowered or 'unknown' in lowered):
        return f'{prefix} references a payload type that Mythic does not know about.'
    if 'c2' in lowered and ('profile' in lowered or 'parameter' in lowered):
        return f'{prefix} has an invalid or incomplete C2 profile configuration for Mythic.'
    if 'bad type' in lowered or 'parameter_type' in lowered:
        return f'{prefix} has a parameter type mismatch: {text}'
    # Return raw text — better than generic message
    return f'{prefix} failed: {text}'


def _format_stage_error(message: str, *, stage_label: str | None = None, suggestion: str | None = None) -> str:
    parts = [message]
    if suggestion:
        parts.append(f'Next step: {suggestion}')
    if stage_label and stage_label not in message:
        parts.insert(0, f'{stage_label}:')
    return ' '.join(parts)


async def _execute_mythic_call(operation, *, label: str, stage_type: str):
    try:
        result = await operation()
    except MythicApplyStageError:
        raise
    except Exception as exc:
        raise MythicApplyStageError(
            _normalize_mythic_error(exc, label=label, stage_type=stage_type),
            stage_label=label,
            suggestion='Review the stage parameters and Mythic server status, then retry the apply.',
        ) from exc

    # create_payload returns build_phase, not status
    build_phase = result.get('build_phase')
    if build_phase == 'error' or (result.get('status') not in (None, 'success') and result.get('status') != 'success'):
        # Collect best available error message from all possible fields
        error = (
            result.get('build_stderr')
            or result.get('build_stdout')
            or result.get('error')
            or result.get('message')
            or result.get('stdout')
            or f'Build failed (phase={build_phase})'
        )
        raise MythicApplyStageError(
            _normalize_mythic_error(error, label=label, stage_type=stage_type),
            stage_label=label,
            suggestion='Open the preflight summary to confirm the exact stage order and inputs, then retry.',
        )

    return result


async def _upload_local_files_to_mythic(parameters: dict[str, Any], mythic_client, db) -> dict[str, Any]:
    """For any File parameter value that is a filename (not a UUID), upload it to Mythic.
    - Skip null/empty values
    - If a cached entry with the same sha256 already has a Mythic UUID → reuse it
    - Otherwise upload and store the UUID
    """
    import re, hashlib
    _UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
    if not parameters or db is None:
        return parameters
    from app.models.file_cache import FileCache
    resolved = dict(parameters)
    for key, val in parameters.items():
        if not isinstance(val, str) or not val or _UUID_RE.match(val):
            continue  # already a UUID, empty, or non-string
        # Look up by filename, prefer already-uploaded entries
        cached = (
            db.query(FileCache)
            .filter(FileCache.filename == val)
            .order_by(FileCache.mythic_file_uuid.desc())  # NULLs last
            .first()
        )
        if not cached:
            continue  # unknown value, not a file param, skip
        # Deduplicate by sha256: look for any entry with same content already uploaded
        if cached.sha256:
            uploaded = (
                db.query(FileCache)
                .filter(FileCache.sha256 == cached.sha256, FileCache.mythic_file_uuid != None)  # noqa: E711
                .first()
            )
            if uploaded:
                resolved[key] = uploaded.mythic_file_uuid
                continue
        if cached.mythic_file_uuid:
            resolved[key] = cached.mythic_file_uuid
            continue
        # Upload to Mythic
        file_uuid = await mythic.register_file(
            mythic=mythic_client,
            filename=cached.filename,
            contents=cached.content,
        )
        if file_uuid:
            cached.mythic_file_uuid = file_uuid
            db.commit()
            resolved[key] = file_uuid
    return resolved


def _resolve_vars(value: Any, variables: dict[str, str]) -> Any:
    """Replace {{VAR_NAME}} placeholders in string values with their resolved values."""
    if not variables or not isinstance(value, str):
        return value
    import re
    def replace(m):
        return variables.get(m.group(1), m.group(0))  # keep {{VAR}} if not found
    return re.sub(r'\{\{(\w+)\}\}', replace, value)


def _resolve_vars_in_params(params: dict[str, Any], variables: dict[str, str]) -> dict[str, Any]:
    """Recursively resolve {{VAR}} in all string values of a parameter dict."""
    if not variables:
        return params
    return {k: _resolve_vars(v, variables) for k, v in params.items()}


async def apply_graph_to_mythic(
    payload: ApplyRequest,
    db=None,
    mythic_tag: str | None = None,
    progress_cb=None,
) -> ApplyResult:
    """Deploy a chain graph to Mythic. Optional progress_cb(event_dict) is called at each step."""
    async def _emit(event: dict):
        if progress_cb:
            await progress_cb(event)

    mythic_client = await _login_to_mythic(db=db)

    node_map = {node.id: node for node in payload.graph.nodes}
    incoming: dict[str, list[str]] = defaultdict(list)
    for edge in payload.graph.edges:
        incoming[edge.target].append(edge.source)

    created_payloads: dict[str, dict[str, Any]] = {}
    stage_results: list[ApplyStageResult] = []

    # Build a description prefix that embeds the chain tag for easy filtering
    tag_prefix = f'[chain:{mythic_tag}] ' if mythic_tag else f'[chain:{payload.name}] '
    base_description = payload.description or ''

    total_stages = len(payload.graph.nodes)
    for stage_idx, node_id in enumerate(_ordered_node_ids(payload.graph), 1):
        node = node_map[node_id]
        data = node.data
        payload_type_name = _resolve_payload_type(data.label, data.payload)
        # Resolve vars in stage label (used as filename in Mythic)
        resolved_label = _resolve_vars(data.label, variables)
        if resolved_label != data.label:
            data = data.model_copy(update={'label': resolved_label})
        await _emit({'type': 'stage_start', 'level': 'info',
                     'msg': f'[{stage_idx}/{total_stages}] Building {data.stage_type} stage "{data.label}" ({payload_type_name})...',
                     'stage': data.label, 'stage_type': data.stage_type, 'idx': stage_idx, 'total': total_stages})
        # Resolve {{VAR}} placeholders in all params before processing
        variables = payload.variables or {}
        raw_params = _resolve_vars_in_params(data.parameters or {}, variables)
        # Upload any locally-cached files (build params)
        resolved_params = await _upload_local_files_to_mythic(raw_params, mythic_client, db)
        build_parameters = _build_parameter_list(resolved_params)
        # Upload locally-cached files in C2 profile params too (with var resolution)
        resolved_c2_profiles = []
        for prof in (data.c2_profiles or []):
            raw_c2 = _resolve_vars_in_params(prof.get('c2_profile_parameters') or {}, variables)
            resolved_c2_params = await _upload_local_files_to_mythic(raw_c2, mythic_client, db)
            resolved_c2_profiles.append({**prof, 'c2_profile_parameters': resolved_c2_params})
        if resolved_c2_profiles:
            # Also resolve vars in profile_url and c2_profile for downloader
            updates = {'c2_profiles': resolved_c2_profiles}
            if variables:
                if data.profile_url:
                    updates['profile_url'] = _resolve_vars(data.profile_url, variables)
                if data.base_url:
                    updates['base_url'] = _resolve_vars(data.base_url, variables)
                if data.c2_profile:
                    updates['c2_profile'] = _resolve_vars(data.c2_profile, variables)
            data = data.model_copy(update=updates)
        elif variables and (data.profile_url or data.base_url or data.c2_profile):
            updates = {}
            if data.profile_url:
                updates['profile_url'] = _resolve_vars(data.profile_url, variables)
            if data.base_url:
                updates['base_url'] = _resolve_vars(data.base_url, variables)
            if data.c2_profile:
                updates['c2_profile'] = _resolve_vars(data.c2_profile, variables)
            if updates:
                data = data.model_copy(update=updates)
        stage_description = f'{tag_prefix}{base_description}'.strip()

        if data.stage_type == 'base':
            if not data.c2_profiles:
                raise MythicApplyStageError(
                    f'Payload stage {data.label} must include at least one C2 profile for live Mythic apply.',
                    stage_label=data.label,
                    suggestion='Add a C2 profile in the inspector or export YAML instead of running live apply.',
                )

            c2_profiles_normalized = _normalize_c2_profiles(data.c2_profiles or [])

            async def operation():
                return await mythic.create_payload(
                    mythic=mythic_client,
                    payload_type_name=payload_type_name,
                    filename=data.label,
                    operating_system=data.os,
                    c2_profiles=c2_profiles_normalized,
                    commands=data.commands or [],
                    build_parameters=build_parameters,
                    description=stage_description,
                    return_on_complete=True,
                )

            result = await _execute_mythic_call(operation, label=data.label, stage_type=data.stage_type)
        elif data.stage_type == 'wrapper':
            upstream_ids = incoming.get(node_id, [])
            if len(upstream_ids) != 1:
                raise MythicApplyStageError(
                    f'Wrapper stage {data.label} requires exactly one upstream payload.',
                    stage_label=data.label,
                    suggestion='Connect one payload or wrapper into this stage before retrying.',
                )
            upstream_node = node_map.get(upstream_ids[0])
            if upstream_node and upstream_node.data.stage_type not in {'base', 'wrapper'}:
                raise MythicApplyStageError(
                    f'Wrapper stage {data.label} can only wrap payload or wrapper stages, not {upstream_node.data.stage_type}.',
                    stage_label=data.label,
                    suggestion='Reconnect the wrapper so it points to a payload or another wrapper.',
                )
            upstream = created_payloads.get(upstream_ids[0])
            wrapped_uuid = upstream.get('uuid') if upstream else None
            if not wrapped_uuid:
                raise MythicApplyStageError(
                    f'Wrapper stage {data.label} could not resolve the wrapped payload UUID.',
                    stage_label=data.label,
                    suggestion='Rebuild the upstream payload first or rerun the apply from the beginning.',
                )

            async def operation():
                return await mythic.create_wrapper_payload(
                    mythic=mythic_client,
                    payload_type_name=payload_type_name,
                    filename=data.label,
                    operating_system=data.os,
                    wrapped_payload_uuid=wrapped_uuid,
                    build_parameters=build_parameters,
                    description=stage_description,
                    return_on_complete=True,
                )

            result = await _execute_mythic_call(operation, label=data.label, stage_type=data.stage_type)
        elif data.stage_type == 'downloader':
            # Downloader = wrapper that hosts the wrapped payload on a C2 URL,
            # then passes that URL as a build parameter to the wrapper payload.
            # Implementation mirrors mythic_payload_automation/main.py create_stage().

            if not data.downloaded_payload:
                raise MythicApplyStageError(
                    f'Downloader stage {data.label} has no target payload configured.',
                    stage_label=data.label,
                    suggestion='Set the "Downloads payload" field to point to a base stage.',
                )
            if not data.c2_profile:
                raise MythicApplyStageError(
                    f'Downloader stage {data.label} requires a C2 profile to host the payload.',
                    stage_label=data.label,
                    suggestion='Set the C2 profile in the downloader stage settings.',
                )
            if not data.profile_url:
                raise MythicApplyStageError(
                    f'Downloader stage {data.label} requires a profile_url (e.g. /monster.txt).',
                    stage_label=data.label,
                    suggestion='Set the Profile URL field in the downloader stage.',
                )
            if not data.url_parameter:
                raise MythicApplyStageError(
                    f'Downloader stage {data.label} requires a url_parameter (build param name for the URL).',
                    stage_label=data.label,
                    suggestion='Set the URL Parameter field in the downloader stage.',
                )

            # 1. Find the downloaded payload UUID and file UUID in Mythic
            downloaded_name = data.downloaded_payload

            # First check payloads we just created in this run
            target_node_id = None
            for nid, node in node_map.items():
                if node.data.label == downloaded_name:
                    target_node_id = nid
                    break

            if target_node_id and target_node_id in created_payloads:
                target_result = created_payloads[target_node_id]
                payload_uuid_dl = target_result.get('uuid')
                file_uuid_dl = target_result.get('file_uuid') or target_result.get('agent_file_id')
                # create_wrapper_payload doesn't return file_uuid — fetch it from Mythic
                if payload_uuid_dl and not file_uuid_dl:
                    try:
                        fmeta = await mythic_utilities.graphql_post(
                            mythic=mythic_client,
                            gql_query=gql.gql(
                                'query GetFileUUID($uuid: String!) { payload(where: {uuid: {_eq: $uuid}}) { filemetum { agent_file_id } } }'
                            ),
                            variables={'uuid': payload_uuid_dl},
                        )
                        payloads_list = fmeta.get('payload') or []
                        if payloads_list:
                            file_uuid_dl = (payloads_list[0].get('filemetum') or {}).get('agent_file_id')
                    except Exception:
                        pass
            else:
                # Look in existing Mythic payloads
                try:
                    existing = await mythic.get_all_payloads(mythic=mythic_client)
                except Exception as exc:
                    raise MythicApplyStageError(
                        f'Downloader stage {data.label} could not query existing Mythic payloads: {exc}',
                        stage_label=data.label,
                    ) from exc

                payload_uuid_dl = None
                file_uuid_dl = None
                from datetime import datetime
                best_dt = None
                for p in existing:
                    if p.get('deleted') or p.get('build_phase') != 'success':
                        continue
                    fname = (p.get('filemetum') or {}).get('filename_utf8', '')
                    if fname == downloaded_name:
                        dt_str = p.get('creation_time', '')
                        try:
                            dt = datetime.fromisoformat(dt_str)
                        except Exception:
                            dt = None
                        if best_dt is None or (dt and dt > best_dt):
                            best_dt = dt
                            payload_uuid_dl = p['uuid']
                            file_uuid_dl = (p.get('filemetum') or {}).get('agent_file_id')

            if not payload_uuid_dl or not file_uuid_dl:
                raise MythicApplyStageError(
                    f'Downloader stage {data.label}: could not find payload "{downloaded_name}" in Mythic. Build it first.',
                    stage_label=data.label,
                    suggestion=f'Make sure the stage "{downloaded_name}" was deployed before this downloader stage.',
                )

            # 2. Get the C2 profile id
            try:
                c2_profiles_info = await mythic_utilities.graphql_post(
                    mythic=mythic_client,
                    gql_query=gql.gql(
                        'query getC2Profiles { c2profile(where: {deleted: {_eq: false}, container_running: {_eq: true}, is_p2p: {_eq: false}}) { id name } }'
                    ),
                )
            except Exception as exc:
                raise MythicApplyStageError(
                    f'Downloader stage {data.label}: failed to query C2 profiles: {exc}',
                    stage_label=data.label,
                ) from exc

            c2_profile_id = None
            for profile in c2_profiles_info.get('c2profile', []):
                if profile['name'] == data.c2_profile:
                    c2_profile_id = profile['id']
                    break

            if not c2_profile_id:
                raise MythicApplyStageError(
                    f'Downloader stage {data.label}: C2 profile "{data.c2_profile}" not found or not running.',
                    stage_label=data.label,
                    suggestion=f'Make sure the {data.c2_profile} C2 container is running in Mythic.',
                )

            # 3. Host the payload file on the C2 at profile_url
            try:
                host_result = await mythic_utilities.graphql_post(
                    mythic=mythic_client,
                    gql_query=gql.gql(
                        'mutation hostFileMutation($c2_id: Int!, $file_uuid: String!, $host_url: String!, $alert_on_download: Boolean, $remove: Boolean) {'
                        ' c2HostFile(c2_id: $c2_id file_uuid: $file_uuid host_url: $host_url alert_on_download: $alert_on_download remove: $remove) {'
                        ' status error __typename } }'
                    ),
                    variables={
                        'c2_id': c2_profile_id,
                        'file_uuid': file_uuid_dl,
                        'host_url': data.profile_url,
                        'alert_on_download': False,
                        'remove': False,
                    },
                )
            except Exception as exc:
                raise MythicApplyStageError(
                    f'Downloader stage {data.label}: failed to host payload on C2: {exc}',
                    stage_label=data.label,
                ) from exc

            if (host_result.get('c2HostFile') or {}).get('status') != 'success':
                err = (host_result.get('c2HostFile') or {}).get('error', 'unknown error')
                raise MythicApplyStageError(
                    f'Downloader stage {data.label}: c2HostFile failed: {err}',
                    stage_label=data.label,
                )

            # 4. Build the download URL: base_url (with vars resolved) + profile_url
            base_url = _resolve_vars(data.base_url or '', variables).rstrip('/')
            if not base_url:
                raise MythicApplyStageError(
                    f'Downloader stage {data.label}: Base URL is empty.'
                    f' Set it in the stage (e.g. https://{{{{DOMAIN1}}}}).',
                    stage_label=data.label,
                    suggestion='Fill the Base URL field in the downloader stage.',
                )

            download_url = f'{base_url}{data.profile_url}'

            # 5. Add url_parameter to build params
            build_parameters.append({'name': data.url_parameter, 'value': download_url})

            # 6. Create the wrapper payload with the URL injected
            _payload_uuid_dl = payload_uuid_dl  # capture for closure

            async def operation():
                return await mythic.create_wrapper_payload(
                    mythic=mythic_client,
                    payload_type_name=payload_type_name,
                    filename=data.label,
                    operating_system=data.os,
                    wrapped_payload_uuid=_payload_uuid_dl,
                    build_parameters=build_parameters,
                    description=stage_description,
                    return_on_complete=True,
                )

            result = await _execute_mythic_call(operation, label=data.label, stage_type=data.stage_type)
        else:
            raise MythicApplyStageError(
                f'Unsupported stage type: {data.stage_type}',
                stage_label=data.label,
            )

        created_payloads[node_id] = result
        stage_result = ApplyStageResult(
            node_id=node_id,
            label=data.label,
            stage_type=data.stage_type,
            mythic_uuid=result.get('uuid'),
            mythic_filename=result.get('filename') or data.label,
            status=result.get('status', 'success'),
            detail=result.get('build_phase') or result.get('message') or 'Build queued successfully.',
        )
        stage_results.append(stage_result)
        build_ok = result.get('build_phase') in ('success', None) or result.get('status') == 'success'
        await _emit({
            'type': 'stage_done',
            'level': 'success' if build_ok else 'warning',
            'msg': f'  ✓ {data.label} — {stage_result.detail}' if build_ok else f'  ⚠ {data.label} — {stage_result.detail}',
            'stage': data.label,
            'uuid': result.get('uuid'),
        })

    await _emit({'type': 'log', 'level': 'success', 'msg': f'Deploy complete — {len(stage_results)} stage(s) built.'})
    return ApplyResult(ok=True, chain_name=payload.name, stages=stage_results)


def describe_mythic_apply_error(exc: MythicApplyError) -> str:
    if isinstance(exc, MythicApplyStageError):
        return _format_stage_error(str(exc), stage_label=exc.stage_label, suggestion=exc.suggestion)
    return str(exc)
