from __future__ import annotations

import json
from collections import defaultdict, deque

import yaml

from app.schemas.chain import GraphDocument, GraphEdge, GraphNode, GraphNodeData


def _toposort(graph: GraphDocument) -> list[GraphNode]:
    indegree = defaultdict(int)
    children: dict[str, list[str]] = defaultdict(list)
    node_map = {node.id: node for node in graph.nodes}
    for edge in graph.edges:
        indegree[edge.target] += 1
        children[edge.source].append(edge.target)
        indegree.setdefault(edge.source, 0)
    queue = deque(sorted([nid for nid in node_map if indegree[nid] == 0]))
    ordered: list[GraphNode] = []
    while queue:
        current = queue.popleft()
        ordered.append(node_map[current])
        for child in children[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(ordered) != len(graph.nodes):
        raise ValueError('The graph contains a cycle or an invalid reference.')
    return ordered


def graph_to_payloads(graph: GraphDocument) -> list[dict]:
    node_map = {node.id: node for node in graph.nodes}
    incoming: dict[str, list[str]] = defaultdict(list)
    for edge in graph.edges:
        incoming[edge.target].append(edge.source)

    payloads = []
    for node in _toposort(graph):
        data = node.data
        item = {
            'name': data.label,
            'payload': data.payload or data.label,
            'os': data.os,
            'parameters': data.parameters or {},
        }
        if data.stage_type == 'base':
            item['commands'] = data.commands or []
            item['c2_profiles'] = data.c2_profiles or []
        elif data.stage_type == 'wrapper':
            item['wrapper'] = True
            item['wrapped_payload'] = node_map[incoming[node.id][0]].data.label if incoming[node.id] else data.wrapped_payload or ''
        elif data.stage_type == 'downloader':
            item['downloader'] = True
            item['downloaded_payload'] = node_map[incoming[node.id][0]].data.label if incoming[node.id] else data.downloaded_payload or ''
            item['c2_profile'] = data.c2_profile or 'http'
            item['profile_url'] = data.profile_url or '/artifact.txt'
            item['url_parameter'] = data.url_parameter or 'url'
        payloads.append(item)
    return payloads


def graph_to_yaml(graph: GraphDocument) -> str:
    doc = {'payloads': graph_to_payloads(graph)}
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)


def yaml_to_graph(yaml_content: str) -> GraphDocument:
    parsed = yaml.safe_load(yaml_content) or {}
    payloads = parsed.get('payloads', [])
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    name_to_id: dict[str, str] = {}

    for idx, payload in enumerate(payloads, start=1):
        name = payload['name']
        node_id = f'n{idx}'
        name_to_id[name] = node_id
        stage_type = 'base'
        wrapped_payload = payload.get('wrapped_payload')
        downloaded_payload = payload.get('downloaded_payload')
        if payload.get('wrapper'):
            stage_type = 'wrapper'
        if payload.get('downloader'):
            stage_type = 'downloader'
        nodes.append(GraphNode(
            id=node_id,
            position={'x': 80 + (idx - 1) * 240, 'y': 140},
            data=GraphNodeData(
                label=name,
                payload=payload.get('payload'),
                stage_type=stage_type,
                os=payload.get('os', 'Windows'),
                parameters=payload.get('parameters') or {},
                commands=payload.get('commands') or [],
                c2_profiles=payload.get('c2_profiles') or [],
                wrapped_payload=wrapped_payload,
                downloaded_payload=downloaded_payload,
                c2_profile=payload.get('c2_profile'),
                profile_url=payload.get('profile_url'),
                url_parameter=payload.get('url_parameter'),
            )
        ))

    for node in nodes:
        data = node.data
        parent_name = data.wrapped_payload or data.downloaded_payload
        if parent_name and parent_name in name_to_id:
            edges.append(GraphEdge(id=f'e-{name_to_id[parent_name]}-{node.id}', source=name_to_id[parent_name], target=node.id, label=data.stage_type))

    return GraphDocument(nodes=nodes, edges=edges)


def graph_to_json(graph: GraphDocument) -> str:
    return json.dumps(graph.model_dump())
