from __future__ import annotations

from collections import defaultdict, deque

from app.schemas.chain import GraphDocument, PreflightResult, PreflightStageSummary, PreflightStageSupport


class GraphValidationResult:
    def __init__(self, *, warnings: list[str] | None = None, errors: list[str] | None = None):
        self.warnings = warnings or []
        self.errors = errors or []

    @property
    def valid(self) -> bool:
        return not self.errors


def _toposort(graph: GraphDocument) -> list[str]:
    indegree = defaultdict(int)
    children: dict[str, list[str]] = defaultdict(list)
    node_ids = {node.id for node in graph.nodes}

    for edge in graph.edges:
        if edge.source not in node_ids or edge.target not in node_ids:
            raise ValueError('The graph contains an invalid edge reference.')
        indegree[edge.target] += 1
        indegree.setdefault(edge.source, 0)
        children[edge.source].append(edge.target)

    queue = deque(sorted([node_id for node_id in node_ids if indegree[node_id] == 0]))
    ordered: list[str] = []
    while queue:
        current = queue.popleft()
        ordered.append(current)
        for child in sorted(children[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    if len(ordered) != len(node_ids):
        raise ValueError('The graph contains a cycle or an invalid reference.')

    return ordered


def _graph_relations(graph: GraphDocument):
    node_map = {node.id: node for node in graph.nodes}
    incoming: dict[str, list[str]] = defaultdict(list)
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in graph.edges:
        if edge.source in node_map and edge.target in node_map:
            incoming[edge.target].append(edge.source)
            outgoing[edge.source].append(edge.target)
    return node_map, incoming, outgoing


def validate_graph(graph: GraphDocument, *, for_apply: bool = False) -> GraphValidationResult:
    warnings: list[str] = []
    errors: list[str] = []

    if not graph.nodes:
        errors.append('The graph is empty.')
        return GraphValidationResult(warnings=warnings, errors=errors)

    labels = [node.data.label for node in graph.nodes]
    if len(labels) != len(set(labels)):
        errors.append('Stage labels must be unique.')

    try:
        _toposort(graph)
    except ValueError as exc:
        errors.append(str(exc))

    node_map, incoming, outgoing = _graph_relations(graph)

    for node in graph.nodes:
        data = node.data
        upstream = incoming.get(node.id, [])
        upstream_nodes = [node_map[source_id] for source_id in upstream if source_id in node_map]
        upstream_types = [source_node.data.stage_type for source_node in upstream_nodes]

        if not data.payload:
            errors.append(f'{data.label}: select a payload type before exporting or applying this stage.')

        if data.stage_type == 'base':
            if upstream:
                errors.append(f'{data.label}: payload stages cannot have upstream graph links.')
            if not data.c2_profiles:
                warnings.append(f'{data.label}: no C2 profile configured.')
        elif data.stage_type == 'wrapper':
            if len(upstream) == 0:
                errors.append(f'{data.label}: wrapper stages require exactly one upstream payload or wrapper.')
            elif len(upstream) > 1:
                errors.append(f'{data.label}: wrapper stages support only one upstream payload.')
            elif upstream_types[0] not in {'base', 'wrapper'}:
                errors.append(f'{data.label}: wrapper stages can only wrap payload or wrapper stages, not {upstream_types[0]}.')
        elif data.stage_type == 'downloader':
            if len(upstream) == 0:
                errors.append(f'{data.label}: downloader stages require exactly one upstream payload or wrapper.')
            elif len(upstream) > 1:
                errors.append(f'{data.label}: downloader stages support only one upstream payload.')
            elif upstream_types[0] not in {'base', 'wrapper'}:
                errors.append(f'{data.label}: downloader stages can only package payload or wrapper stages, not {upstream_types[0]}.')
            if for_apply:
                errors.append(
                    f'{data.label}: downloader stages are not supported by live Mythic apply yet. '
                    'Export the YAML for this chain instead.'
                )
            else:
                warnings.append(
                    f'{data.label}: downloader stages export to YAML, but live Mythic apply is not supported yet.'
                )

        if outgoing.get(node.id, []) and data.stage_type == 'downloader':
            warnings.append(f'{data.label}: downloader stages usually terminate the delivery chain.')

    return GraphValidationResult(warnings=warnings, errors=errors)


def _build_stage_action(node, upstream_labels: list[str]) -> str:
    data = node.data
    if data.stage_type == 'base':
        profile_count = len(data.c2_profiles or [])
        command_count = len(data.commands or [])
        return (
            f'Build payload via Mythic as {data.payload} on {data.os} '
            f'with {profile_count} C2 profile{'' if profile_count == 1 else 's'} '
            f'and {command_count} command{'' if command_count == 1 else 's'}.'
        )
    if data.stage_type == 'wrapper':
        source = upstream_labels[0] if upstream_labels else 'the upstream stage'
        return f'Wrap {source} with Mythic payload type {data.payload} for {data.os}.'
    if data.stage_type == 'downloader':
        source = upstream_labels[0] if upstream_labels else 'the upstream stage'
        return f'Would package {source} as downloader {data.payload}, but this remains YAML-only.'
    return f'Unhandled stage type {data.stage_type}.'


def build_apply_preflight(graph: GraphDocument, *, yaml_content: str = '') -> PreflightResult:
    validation = validate_graph(graph, for_apply=False)
    node_map, incoming, _ = _graph_relations(graph)

    blockers = list(validation.errors)
    warnings = list(validation.warnings)
    stage_counts = {'base': 0, 'wrapper': 0, 'downloader': 0}
    stages: list[PreflightStageSupport] = []

    ordered_ids: list[str] = []
    if graph.nodes:
        try:
            ordered_ids = _toposort(graph)
        except ValueError:
            ordered_ids = [node.id for node in graph.nodes]

    for order_index, node_id in enumerate(ordered_ids, start=1):
        node = node_map[node_id]
        stage_type = node.data.stage_type
        if stage_type in stage_counts:
            stage_counts[stage_type] += 1

        upstream_labels = [node_map[source_id].data.label for source_id in incoming.get(node.id, []) if source_id in node_map]
        supported_for_apply = stage_type in {'base', 'wrapper'}
        reason = None if supported_for_apply else 'Downloader stages cannot be created through live Mythic apply yet.'
        stages.append(
            PreflightStageSupport(
                node_id=node.id,
                label=node.data.label,
                stage_type=stage_type,
                order=order_index,
                upstream_labels=upstream_labels,
                supported_for_apply=supported_for_apply,
                action_summary=_build_stage_action(node, upstream_labels),
                reason=reason,
            )
        )

        if stage_type == 'downloader':
            blockers.append(
                f'{node.data.label}: downloader stages are excluded from live Mythic apply. Export YAML for this chain instead.'
            )

    deduped_blockers = list(dict.fromkeys(blockers))
    deduped_warnings = list(dict.fromkeys(warnings))
    apply_supported = sum(1 for stage in stages if stage.supported_for_apply)

    if graph.nodes and not deduped_blockers:
        deduped_warnings.append('This graph is structurally compatible with live Mythic apply.')
    elif not graph.nodes:
        deduped_blockers.append('Add at least one stage before applying to Mythic.')

    if stage_counts['downloader']:
        deduped_warnings.append('Downloader chains can still be exported as YAML even when live apply is blocked.')

    summary = PreflightStageSummary(
        total=len(node_map),
        base=stage_counts['base'],
        wrapper=stage_counts['wrapper'],
        downloader=stage_counts['downloader'],
        apply_supported=apply_supported,
        apply_unsupported=len(stages) - apply_supported,
    )

    return PreflightResult(
        can_apply=bool(graph.nodes) and not deduped_blockers,
        blockers=deduped_blockers,
        warnings=deduped_warnings,
        stage_summary=summary,
        stages=stages,
        yaml_content=yaml_content,
    )
