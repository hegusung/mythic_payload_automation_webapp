import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.services.component_catalog import _build_c2_profile_examples, _get_c2_profile_parameter_template
from app.services.mythic_apply import MythicApplyStageError

client = TestClient(app)


def build_base_node(node_id='n1', label='apollo.exe'):
    return {
        'id': node_id,
        'type': 'default',
        'position': {'x': 0, 'y': 0},
        'data': {
            'label': label,
            'payload': 'apollo',
            'stage_type': 'base',
            'os': 'Windows',
            'parameters': {'output_type': 'WinExe'},
            'commands': ['exit'],
            'c2_profiles': [{'c2_profile': 'http', 'c2_profile_parameters': {'callback_host': 'http://127.0.0.1'}}],
            'wrapped_payload': None,
            'downloaded_payload': None,
            'c2_profile': None,
            'profile_url': None,
            'url_parameter': None,
        },
    }


def build_wrapper_node(node_id='n2', label='wrap.ps1', payload='psh_wraps_shellcode'):
    return {
        'id': node_id,
        'type': 'default',
        'position': {'x': 1, 'y': 0},
        'data': {
            'label': label,
            'payload': payload,
            'stage_type': 'wrapper',
            'os': 'Windows',
            'parameters': {},
            'commands': [],
            'c2_profiles': [],
            'wrapped_payload': None,
            'downloaded_payload': None,
            'c2_profile': None,
            'profile_url': None,
            'url_parameter': None,
        },
    }


def build_downloader_node(node_id='n2', label='dl.hta'):
    return {
        'id': node_id,
        'type': 'default',
        'position': {'x': 1, 'y': 0},
        'data': {
            'label': label,
            'payload': 'hta',
            'stage_type': 'downloader',
            'os': 'Windows',
            'parameters': {},
            'commands': [],
            'c2_profiles': [],
            'wrapped_payload': None,
            'downloaded_payload': None,
            'c2_profile': 'http',
            'profile_url': '/artifact.txt',
            'url_parameter': 'url',
        },
    }


def test_health():
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_components_include_json_examples_from_fallback_catalog():
    response = client.get('/api/components')
    assert response.status_code == 200
    body = response.json()
    assert body['source'] == 'fallback'
    apollo = next(component for component in body['components'] if component['type'] == 'apollo')
    assert apollo['example_parameters']['output_type'] == 'WinExe'
    assert apollo['available_c2_profiles'] == ['http']
    assert apollo['default_c2_profile']['c2_profile'] == 'http'
    assert apollo['example_c2_profiles'][0]['c2_profile'] == 'http'
    assert apollo['example_c2_profiles'][0]['c2_profile_parameters']['callback_host'] == 'http://127.0.0.1'
    assert apollo['c2_profiles_metadata'][0]['name'] == 'http'
    assert apollo['c2_profiles_metadata'][0]['parameters'][0]['name'] == 'callback_host'


def test_known_http_c2_template_contains_meaningful_defaults():
    template = _get_c2_profile_parameter_template('http')
    assert template['callback_host'] == 'http://127.0.0.1'
    assert template['callback_port'] == 80
    assert template['headers']['User-Agent'] == 'Mozilla/5.0'


def test_build_c2_profile_examples_uses_live_metadata_when_available_and_templates_otherwise():
    available, examples, metadata = _build_c2_profile_examples(
        {
            'payloadtypec2profiles': [
                {
                    'c2profile': {
                        'name': 'http',
                        'description': 'HTTP profile',
                        'c2profileparameters': [
                            {
                                'name': 'callback_interval',
                                'parameter_type': 'Number',
                                'description': 'Seconds',
                                'default_value': '10',
                                'required': False,
                                'randomize': False,
                                'format_string': '',
                                'verifier_regex': '',
                                'choices': [],
                                'crypto_type': False,
                            }
                        ],
                    }
                },
                {'c2profile': {'name': 'tcp'}},
            ]
        }
    )

    assert available == ['http', 'tcp']
    assert examples[0]['c2_profile_parameters']['callback_interval'] == 10
    assert examples[1]['c2_profile_parameters'] == {}
    assert metadata[0].parameters[0].default_value_decoded == 10


def test_components_debug_returns_fallback_shape_without_live_mythic():
    response = client.get('/api/components/debug')
    assert response.status_code == 200
    body = response.json()
    assert body['source'] == 'fallback'
    assert isinstance(body['raw_payload_types'], list)
    assert body['warnings']


def test_import_and_validate():
    yaml_content = """payloads:\n  - name: apollo.exe\n    payload: apollo\n    os: Windows\n    commands: [exit]\n    c2_profiles:\n      - c2_profile: http\n        c2_profile_parameters:\n          callback_host: http://127.0.0.1\n    parameters:\n      output_type: WinExe\n  - name: wrapper.ps1\n    payload: psh_wraps_shellcode\n    os: Windows\n    wrapper: true\n    wrapped_payload: apollo.exe\n    parameters: {}\n"""
    imported = client.post('/api/import', json={'yaml_content': yaml_content})
    assert imported.status_code == 200
    data = imported.json()
    assert data['valid'] is True
    assert len(data['graph']['nodes']) == 2

    validate = client.post('/api/validate', json={'name': 'demo', 'description': 'x', 'graph': data['graph']})
    assert validate.status_code == 200
    assert validate.json()['valid'] is True


def test_create_chain_roundtrip():
    graph = {
        'nodes': [build_base_node(), build_wrapper_node()],
        'edges': [{'id': 'e1', 'source': 'n1', 'target': 'n2', 'label': 'wrapper'}],
    }
    created = client.post('/api/chains', json={'name': f"chain-{uuid.uuid4().hex}", 'description': 'demo', 'graph': graph})
    assert created.status_code == 200
    body = created.json()
    assert 'payloads:' in body['yaml_content']
    listed = client.get('/api/chains')
    assert listed.status_code == 200
    assert len(listed.json()) >= 1


def test_validate_reports_downloader_live_apply_limitation():
    graph = {
        'nodes': [build_base_node(), build_downloader_node()],
        'edges': [{'id': 'e1', 'source': 'n1', 'target': 'n2', 'label': 'downloads'}],
    }

    response = client.post('/api/validate', json={'name': 'demo', 'description': 'demo', 'graph': graph})
    assert response.status_code == 200
    body = response.json()
    assert body['valid'] is True
    assert any('live Mythic apply is not supported yet' in warning for warning in body['warnings'])


def test_preflight_reports_structured_apply_readiness_and_execution_plan():
    graph = {
        'nodes': [build_base_node(), build_downloader_node()],
        'edges': [{'id': 'e1', 'source': 'n1', 'target': 'n2', 'label': 'downloads'}],
    }

    response = client.post('/api/preflight', json={'name': 'demo-apply', 'description': 'demo', 'graph': graph})
    assert response.status_code == 200
    body = response.json()
    assert body['can_apply'] is False
    assert body['stage_summary']['downloader'] == 1
    assert body['stage_summary']['apply_supported'] == 1
    assert body['stages'][0]['order'] == 1
    assert body['stages'][1]['order'] == 2
    assert body['stages'][1]['upstream_labels'] == ['apollo.exe']
    assert body['stages'][1]['supported_for_apply'] is False
    assert 'YAML-only' in body['stages'][1]['action_summary']
    assert any('downloader stages are excluded from live Mythic apply' in blocker for blocker in body['blockers'])


def test_apply_to_mythic_rejects_downloader_graph():
    graph = {
        'nodes': [build_base_node(), build_downloader_node()],
        'edges': [{'id': 'e1', 'source': 'n1', 'target': 'n2', 'label': 'downloads'}],
    }

    response = client.post('/api/apply', json={'name': 'demo-apply', 'description': 'demo', 'graph': graph})
    assert response.status_code == 400
    assert 'downloader stages are excluded from live Mythic apply' in response.json()['detail']


def test_validate_rejects_missing_payload_type_and_invalid_wrapper_source():
    graph = {
        'nodes': [build_base_node(), build_downloader_node(), build_wrapper_node(node_id='n3', payload='')],
        'edges': [
            {'id': 'e1', 'source': 'n1', 'target': 'n2', 'label': 'downloads'},
            {'id': 'e2', 'source': 'n2', 'target': 'n3', 'label': 'wraps'},
        ],
    }

    response = client.post('/api/validate', json={'name': 'demo', 'description': 'demo', 'graph': graph})
    assert response.status_code == 200
    body = response.json()
    assert body['valid'] is False
    assert any('select a payload type' in error for error in body['errors'])
    assert any('can only wrap payload or wrapper stages, not downloader' in error for error in body['errors'])


def test_apply_to_mythic_endpoint(monkeypatch):
    graph = {
        'nodes': [build_base_node(), build_wrapper_node()],
        'edges': [{'id': 'e1', 'source': 'n1', 'target': 'n2', 'label': 'wraps'}],
    }

    async def fake_apply(payload):
        assert payload.name == 'demo-apply'
        return {
            'ok': True,
            'chain_name': payload.name,
            'stages': [
                {'node_id': 'n1', 'label': 'apollo.exe', 'stage_type': 'base', 'mythic_uuid': 'uuid-1', 'mythic_filename': 'apollo.exe', 'status': 'success', 'detail': 'success'},
                {'node_id': 'n2', 'label': 'wrap.ps1', 'stage_type': 'wrapper', 'mythic_uuid': 'uuid-2', 'mythic_filename': 'wrap.ps1', 'status': 'success', 'detail': 'success'},
            ],
        }

    monkeypatch.setattr('app.api.routes.apply_graph_to_mythic', fake_apply)

    response = client.post('/api/apply', json={'name': 'demo-apply', 'description': 'demo', 'graph': graph})
    assert response.status_code == 200
    body = response.json()
    assert body['ok'] is True
    assert [stage['mythic_uuid'] for stage in body['stages']] == ['uuid-1', 'uuid-2']


def test_apply_to_mythic_returns_stage_specific_error_details(monkeypatch):
    graph = {
        'nodes': [build_base_node(), build_wrapper_node()],
        'edges': [{'id': 'e1', 'source': 'n1', 'target': 'n2', 'label': 'wraps'}],
    }

    async def fake_apply(payload):
        raise MythicApplyStageError(
            'Wrapper stage wrap.ps1 could not authenticate to Mythic. Verify the configured username and password.',
            stage_label='wrap.ps1',
            suggestion='Check the Mythic account credentials and retry the apply.',
        )

    monkeypatch.setattr('app.api.routes.apply_graph_to_mythic', fake_apply)

    response = client.post('/api/apply', json={'name': 'demo-apply', 'description': 'demo', 'graph': graph})
    assert response.status_code == 400
    detail = response.json()['detail']
    assert 'wrap.ps1' in detail
    assert 'Next step:' in detail
    assert 'credentials' in detail
