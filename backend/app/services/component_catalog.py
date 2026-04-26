from __future__ import annotations

import json
from copy import deepcopy
from typing import Any
from urllib.parse import urlparse

from mythic import mythic

from app.core.config import settings
from app.schemas.chain import BuildParameterDefinition, C2ProfileDefinition, C2ProfileParameterDefinition, ComponentDefinition


class MythicCatalogError(RuntimeError):
    pass


KNOWN_C2_PROFILE_TEMPLATES: dict[str, dict[str, Any]] = {
    'http': {
        'callback_host': 'http://127.0.0.1',
        'callback_interval': 10,
        'callback_jitter': 23,
        'callback_port': 80,
        'AESPSK': 'aes256_hmac',
        'get_uri': 'index',
        'headers': {'User-Agent': 'Mozilla/5.0'},
        'killdate': '11/02/2026',
        'query_path_name': 'q',
        'encrypted_exchange_check': True,
        'post_uri': 'data',
    },
}


def _get_c2_profile_parameter_template(name: str | None) -> dict[str, Any]:
    if not name:
        return {}
    return deepcopy(KNOWN_C2_PROFILE_TEMPLATES.get(str(name).lower(), {}))


FALLBACK_COMPONENTS = [
    ComponentDefinition(
        type='apollo', stage_type='base', label='Apollo', description='Mythic Apollo payload',
        default_parameters={'debug': False, 'adjust_filename': False, 'shellcode_bypass': 'Continue on fail', 'shellcode_format': 'Binary', 'output_type': 'WinExe'},
        example_parameters={'debug': False, 'adjust_filename': False, 'shellcode_bypass': 'Continue on fail', 'shellcode_format': 'Binary', 'output_type': 'WinExe'},
        default_commands=['exit', 'register_file', 'download', 'load', 'ps', 'run', 'shell', 'upload', 'wmiexecute'],
        default_c2_profile={
            'c2_profile': 'http',
            'c2_profile_parameters': _get_c2_profile_parameter_template('http')
        },
        example_c2_profiles=[
            {
                'c2_profile': 'http',
                'c2_profile_parameters': _get_c2_profile_parameter_template('http')
            }
        ],
        available_c2_profiles=['http'],
        c2_profiles_metadata=[
            C2ProfileDefinition(
                name='http',
                description='Fallback HTTP C2 template bundled with the app when live Mythic metadata is unavailable.',
                parameters=[
                    C2ProfileParameterDefinition(name='callback_host', parameter_type='String', default_value='http://127.0.0.1', default_value_decoded='http://127.0.0.1', required=True),
                    C2ProfileParameterDefinition(name='callback_port', parameter_type='Number', default_value='80', default_value_decoded=80),
                    C2ProfileParameterDefinition(name='callback_interval', parameter_type='Number', default_value='10', default_value_decoded=10),
                    C2ProfileParameterDefinition(name='callback_jitter', parameter_type='Number', default_value='23', default_value_decoded=23),
                    C2ProfileParameterDefinition(name='AESPSK', parameter_type='ChooseOne', default_value='aes256_hmac', default_value_decoded='aes256_hmac', choices=['aes256_hmac']),
                ],
            )
        ],
    ),
    ComponentDefinition(type='psh_wraps_shellcode', stage_type='wrapper', label='PowerShell wraps shellcode', description='Wrap a payload inside PowerShell shellcode', supports_wrapper=True),
    ComponentDefinition(type='psh_remote_psh', stage_type='downloader', label='PowerShell remote PSH', description='Download and execute a remote PowerShell script', supports_downloader=True, default_parameters={}, example_parameters={}),
    ComponentDefinition(type='cmd_wraps_powershell', stage_type='wrapper', label='CMD wraps PowerShell', description='Wrap a PS1 payload inside a .cmd launcher', supports_wrapper=True, default_parameters={'mode': 'inline'}, example_parameters={'mode': 'inline'}),
    ComponentDefinition(type='lnk_wraps_cmd', stage_type='wrapper', label='LNK wraps CMD', description='Create a .lnk shortcut that launches a command', supports_wrapper=True, default_parameters={'description': 'Click me plz', 'icon_file': 'C:\\Windows\\System32\\WSReset.exe', 'window_mode': 'Minimized', 'word_dir': 'C:\\'}, example_parameters={'description': 'Click me plz', 'icon_file': 'C:\\Windows\\System32\\WSReset.exe', 'window_mode': 'Minimized', 'word_dir': 'C:\\'}),
    ComponentDefinition(type='packmypayload', stage_type='wrapper', label='Archive packer', description='Wrap a payload inside an archive', supports_wrapper=True, default_parameters={'archive_type': 'zip', 'password': '', 'payload_name': 'payload.bin', 'file1': 'space.jpg', 'file1_content': 'file:image.jpg'}, example_parameters={'archive_type': 'zip', 'password': '', 'payload_name': 'payload.bin', 'file1': 'space.jpg', 'file1_content': 'file:image.jpg'}),
    ComponentDefinition(type='jscript_download_save_execute', stage_type='downloader', label='JScript download+exec', description='Download an executable and launch it through JScript', supports_downloader=True, default_parameters={'download_method': 'Msxml2.XMLHTTP', 'exec_method': 'WScript.Shell_Run', 'path': '%APPDATA%\\sample.exe'}, example_parameters={'download_method': 'Msxml2.XMLHTTP', 'exec_method': 'WScript.Shell_Run', 'path': '%APPDATA%\\sample.exe'}),
    ComponentDefinition(type='sct_wraps_script', stage_type='wrapper', label='SCT wraps script', description='Wrap a script inside an SCT container', supports_wrapper=True, default_parameters={'progid': 'trustmebro', 'classid': '{F000F000-0000-0000-0000-000000000001}'}, example_parameters={'progid': 'trustmebro', 'classid': '{F000F000-0000-0000-0000-000000000001}'}),
    ComponentDefinition(type='cmd_regsvr32_remote_sct', stage_type='downloader', label='CMD regsvr32 remote SCT', description='Launch regsvr32 against a remote SCT', supports_downloader=True, default_parameters={}, example_parameters={}),
    ComponentDefinition(type='clickfix', stage_type='wrapper', label='ClickFix HTML', description='ClickFix social-engineering HTML page', supports_wrapper=True),
]


BASIC_PAYLOAD_QUERY = """
query GetPayloadTypes {
  payloadtype {
    id
    name
    author
    supported_os
    wrapper
    container_running
    deleted
    note
  }
}
"""


ENRICHED_PAYLOAD_QUERY = """
query GetPayloadTypes {
  payloadtype {
    id
    name
    author
    supported_os
    wrapper
    container_running
    deleted
    note
    buildparameters {
      name
      parameter_type
      description
      default_value
      randomize
      format_string
      required
      verifier_regex
      choices
    }
    commands(order_by: {cmd: asc}) {
      cmd
      description
      needs_admin
      supported_ui_features
    }
    payloadtypec2profiles {
      c2profile {
        name
        description
        is_p2p
        container_running
        c2profileparameters {
          name
          parameter_type
          description
          default_value
          randomize
          format_string
          required
          verifier_regex
          choices
          crypto_type
        }
      }
    }
  }
}
"""


def _parse_mythic_connection() -> tuple[str, int, bool]:
    if not settings.mythic_url:
        raise ValueError('MYTHIC_URL is not configured')

    parsed = urlparse(settings.mythic_url)
    if not parsed.hostname:
        raise ValueError(f'Invalid MYTHIC_URL: {settings.mythic_url}')

    ssl = parsed.scheme == 'https'
    port = parsed.port or (7443 if ssl else 80)
    return parsed.hostname, port, ssl


async def _execute_payload_query(query: str) -> list[dict[str, Any]]:
    host, port, ssl = _parse_mythic_connection()
    mythic_instance = await mythic.login(
        username=settings.mythic_username or '',
        password=settings.mythic_password or '',
        server_ip=host,
        server_port=port,
        ssl=ssl,
    )
    result = await mythic.execute_custom_query(mythic=mythic_instance, query=query)
    return result.get('payloadtype', []) if isinstance(result, dict) else []


async def _fetch_payload_types_from_mythic() -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    try:
        return await _execute_payload_query(ENRICHED_PAYLOAD_QUERY), warnings
    except Exception as exc:
        warnings.append(f'Mythic payload metadata is partially unavailable ({exc}). Falling back to basic payload catalog data.')
        return await _execute_payload_query(BASIC_PAYLOAD_QUERY), warnings


def _coerce_parameter_default(parameter: dict[str, Any]) -> Any:
    default_value = parameter.get('default_value')
    parameter_type = str(parameter.get('parameter_type') or '').lower()
    format_string = str(parameter.get('format_string') or '').lower()

    if default_value not in (None, ''):
        if parameter_type in {'boolean', 'bool'}:
            return str(default_value).lower() in {'true', '1', 'yes', 't'}
        if parameter_type in {'number', 'int', 'integer'}:
            try:
                return int(default_value)
            except (TypeError, ValueError):
                return default_value
        if parameter_type in {'float', 'double'}:
            try:
                return float(default_value)
            except (TypeError, ValueError):
                return default_value
        if parameter_type in {'array', 'list'}:
            if isinstance(default_value, str):
                try:
                    return json.loads(default_value)
                except Exception:
                    return [default_value]
            return default_value
        if parameter_type in {'dictionary', 'dict', 'map'}:
            if isinstance(default_value, str):
                try:
                    return json.loads(default_value)
                except Exception:
                    return default_value
            return default_value
        return default_value

    if parameter_type in {'boolean', 'bool'}:
        return False
    if parameter_type in {'number', 'int', 'integer', 'float', 'double'}:
        return 0
    if parameter_type in {'array', 'list'}:
        return []
    if parameter_type in {'dictionary', 'dict', 'map'}:
        return {}
    if format_string in {'file', 'chooseone', 'choosemultiple'}:
        return ''
    return ''


def _build_c2_profile_metadata(item: dict[str, Any]) -> list[C2ProfileDefinition]:
    output: list[C2ProfileDefinition] = []

    for relation in item.get('payloadtypec2profiles') or []:
        profile = relation.get('c2profile') or {}
        name = profile.get('name')
        if not name:
            continue

        parameters = [
            C2ProfileParameterDefinition(
                name=str(parameter.get('name') or ''),
                parameter_type=str(parameter.get('parameter_type') or ''),
                description=str(parameter.get('description') or ''),
                default_value=str(parameter.get('default_value') or ''),
                default_value_decoded=_coerce_parameter_default(parameter),
                required=bool(parameter.get('required')),
                randomize=bool(parameter.get('randomize')),
                format_string=str(parameter.get('format_string') or ''),
                verifier_regex=str(parameter.get('verifier_regex') or ''),
                choices=list(parameter.get('choices') or []),
                crypto_type=bool(parameter.get('crypto_type')),
            )
            for parameter in (profile.get('c2profileparameters') or [])
            if parameter.get('name')
        ]

        output.append(
            C2ProfileDefinition(
                name=name,
                description=str(profile.get('description') or ''),
                is_p2p=bool(profile.get('is_p2p')),
                container_running=profile.get('container_running'),
                parameters=parameters,
            )
        )

    return output


def _build_c2_profile_defaults(metadata: list[C2ProfileDefinition], name: str | None) -> dict[str, Any]:
    if not name:
        return {}

    for profile in metadata:
        if profile.name == name:
            return {parameter.name: deepcopy(parameter.default_value_decoded) for parameter in profile.parameters}

    return _get_c2_profile_parameter_template(name)


def _build_parameter_examples(item: dict[str, Any]) -> dict[str, Any]:
    examples: dict[str, Any] = {}
    for parameter in item.get('buildparameters') or []:
        name = parameter.get('name')
        if not name:
            continue
        examples[name] = _coerce_parameter_default(parameter)
    return examples


def _build_c2_profile_examples(item: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]], list[C2ProfileDefinition]]:
    metadata = _build_c2_profile_metadata(item)
    available_profiles = [profile.name for profile in metadata]
    examples = [
        {'c2_profile': profile.name, 'c2_profile_parameters': _build_c2_profile_defaults(metadata, profile.name)}
        for profile in metadata
    ]

    if not examples:
        for relation in item.get('payloadtypec2profiles') or []:
            profile = relation.get('c2profile') or {}
            name = profile.get('name')
            if not name:
                continue
            available_profiles.append(name)
            examples.append({'c2_profile': name, 'c2_profile_parameters': _get_c2_profile_parameter_template(name)})

    return available_profiles, examples, metadata


def _detect_url_parameter(buildparameters: list[dict[str, Any]]) -> str | None:
    """Return the parameter named exactly 'downloader_url' (case-insensitive), or None.
    This is the convention used to mark a wrapper as a downloader stage.
    """
    for p in buildparameters:
        name = p.get('name') or ''
        if name.lower() == 'downloader_url':
            return name
    return None


def _build_components_from_payload_types(payload_types: list[dict[str, Any]]) -> list[ComponentDefinition]:
    """Convert raw Mythic payloadtype records into ComponentDefinition objects.

    Classification rule:
    - base payload (wrapper=False) → stage_type='base'
    - wrapper with a build param containing 'url' → stage_type='downloader', supports_downloader=True
    - wrapper without url param → stage_type='wrapper', supports_wrapper=True
    The two wrapper sub-types are mutually exclusive.
    """
    components: list[ComponentDefinition] = []
    for item in payload_types:
        if item.get('deleted'):
            continue
        name = item.get('name')
        if not name:
            continue

        is_wrapper = bool(item.get('wrapper'))
        buildparams = item.get('buildparameters') or []
        url_param = _detect_url_parameter(buildparams) if is_wrapper else None

        # Classify
        if not is_wrapper:
            stage_type = 'base'
            supports_wrapper = False
            supports_downloader = False
        elif url_param:
            stage_type = 'downloader'
            supports_wrapper = False
            supports_downloader = True
        else:
            stage_type = 'wrapper'
            supports_wrapper = True
            supports_downloader = False

        description_bits = []
        if item.get('author'):
            description_bits.append(f"Author: {item['author']}")
        if item.get('supported_os'):
            description_bits.append(f"OS: {', '.join(item['supported_os'])}")
        if item.get('container_running') is False:
            description_bits.append('container stopped')
        description = ' | '.join(description_bits) or item.get('note') or 'Synchronized from Mythic'

        example_parameters = _build_parameter_examples(item)
        available_c2_profiles, example_c2_profiles, c2_profiles_metadata = _build_c2_profile_examples(item)
        build_parameters_metadata = _build_build_parameter_metadata(item)

        # Commands (base payloads only)
        available_commands = []
        default_commands_list = []
        if not is_wrapper:
            from app.schemas.chain import CommandDefinition
            for cmd in (item.get('commands') or []):
                cmd_name = cmd.get('cmd', '')
                if not cmd_name:
                    continue
                available_commands.append(CommandDefinition(
                    cmd=cmd_name,
                    description=cmd.get('description') or '',
                    needs_admin=bool(cmd.get('needs_admin')),
                    supported_ui_features=cmd.get('supported_ui_features') or [],
                ))
                default_commands_list.append(cmd_name)

        components.append(
            ComponentDefinition(
                type=name,
                stage_type=stage_type,
                label=name,
                description=description,
                note=item.get('note') or None,
                supports_wrapper=supports_wrapper,
                supports_downloader=supports_downloader,
                url_parameter=url_param,
                default_parameters=example_parameters,
                example_parameters=example_parameters,
                build_parameters_metadata=build_parameters_metadata,
                available_commands=available_commands,
                default_commands=default_commands_list,
                default_c2_profile=deepcopy(example_c2_profiles[0]) if example_c2_profiles else None,
                example_c2_profiles=example_c2_profiles,
                available_c2_profiles=available_c2_profiles,
                c2_profiles_metadata=c2_profiles_metadata,
            )
        )
    return components


def _build_build_parameter_metadata(item: dict[str, Any]) -> list[BuildParameterDefinition]:
    output: list[BuildParameterDefinition] = []
    for param in item.get('buildparameters') or []:
        name = param.get('name')
        if not name:
            continue
        output.append(BuildParameterDefinition(
            name=name,
            parameter_type=str(param.get('parameter_type') or 'String'),
            description=str(param.get('description') or ''),
            default_value=str(param.get('default_value') or ''),
            default_value_decoded=_coerce_parameter_default(param),
            required=bool(param.get('required')),
            randomize=bool(param.get('randomize')),
            choices=list(param.get('choices') or []),
        ))
    return output


async def fetch_components() -> tuple[str, list[ComponentDefinition], list[str]]:
    warnings: list[str] = []
    if not settings.mythic_url:
        warnings.append('MYTHIC_URL is not configured. Using the local catalog.')
        return 'fallback', FALLBACK_COMPONENTS, warnings

    if not settings.mythic_username or not settings.mythic_password:
        warnings.append('Mythic credentials are incomplete. Using the local catalog.')
        return 'fallback', FALLBACK_COMPONENTS, warnings

    try:
        payload_types, metadata_warnings = await _fetch_payload_types_from_mythic()
        warnings.extend(metadata_warnings)
    except Exception as exc:
        raise MythicCatalogError(f'Unable to query Mythic through the Python SDK: {exc}') from exc

    components = _build_components_from_payload_types(payload_types)

    if not components:
        raise MythicCatalogError('Mythic returned an empty payload catalog. Local fallback stays disabled when MYTHIC_URL is configured.')

    return 'mythic', components, warnings


async def fetch_components_with_creds(
    mythic_url: str,
    mythic_username: str,
    mythic_password: str,
) -> tuple[str, list[ComponentDefinition], list[str]]:
    """Like fetch_components() but uses explicit credentials instead of global settings."""
    from urllib.parse import urlparse

    warnings: list[str] = []

    parsed = urlparse(mythic_url)
    if not parsed.hostname:
        raise MythicCatalogError(f'Invalid MYTHIC_URL: {mythic_url}')

    ssl = parsed.scheme == 'https'
    port = parsed.port or (7443 if ssl else 80)

    async def _query(query: str) -> list[dict[str, Any]]:
        instance = await mythic.login(
            username=mythic_username,
            password=mythic_password,
            server_ip=parsed.hostname,
            server_port=port,
            ssl=ssl,
        )
        result = await mythic.execute_custom_query(mythic=instance, query=query)
        return result.get('payloadtype', []) if isinstance(result, dict) else []

    try:
        try:
            payload_types = await _query(ENRICHED_PAYLOAD_QUERY)
        except Exception as exc:
            warnings.append(f'Enriched query failed ({exc}), falling back to basic query.')
            payload_types = await _query(BASIC_PAYLOAD_QUERY)
    except Exception as exc:
        raise MythicCatalogError(f'Unable to query Mythic: {exc}') from exc

    components = _build_components_from_payload_types(payload_types)

    if not components:
        raise MythicCatalogError('Mythic returned an empty payload catalog.')

    return 'mythic', components, warnings


async def fetch_component_catalog_debug() -> tuple[str, list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    if not settings.mythic_url:
        warnings.append('MYTHIC_URL is not configured. No live Mythic schema inspection is possible.')
        return 'fallback', [], warnings

    if not settings.mythic_username or not settings.mythic_password:
        warnings.append('Mythic credentials are incomplete. No live Mythic schema inspection is possible.')
        return 'fallback', [], warnings

    try:
        payload_types, metadata_warnings = await _fetch_payload_types_from_mythic()
        warnings.extend(metadata_warnings)
        return 'mythic', payload_types, warnings
    except Exception as exc:
        raise MythicCatalogError(f'Unable to inspect the live Mythic payload catalog: {exc}') from exc
