from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class GraphNodeData(BaseModel):
    label: str
    payload: str | None = None
    stage_type: Literal['base', 'wrapper', 'downloader']
    os: str = 'Windows'
    parameters: dict[str, Any] = Field(default_factory=dict)
    commands: list[str] = Field(default_factory=list)
    c2_profiles: list[dict[str, Any]] = Field(default_factory=list)
    wrapped_payload: str | None = None
    downloaded_payload: str | None = None
    c2_profile: str | None = None
    profile_url: str | None = None
    base_url: str | None = None  # Base URL for downloader (e.g. https://{{DOMAIN1}})
    url_parameter: str | None = None

    @field_validator('label')
    @classmethod
    def validate_label(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError('Stage labels cannot be empty.')
        return cleaned

    @field_validator('payload')
    @classmethod
    def validate_payload(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = value.strip()
        return cleaned or None

    @field_validator('os')
    @classmethod
    def validate_os(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError('Stage operating system cannot be empty.')
        return cleaned


class GraphNode(BaseModel):
    id: str
    type: str = 'default'
    position: dict[str, float]
    data: GraphNodeData


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str | None = None


class GraphDocument(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class ChainBase(BaseModel):
    name: str
    description: str | None = None
    mythic_tag: str | None = None
    graph: GraphDocument
    variables: dict[str, str] = Field(default_factory=dict)


class ChainCreate(ChainBase):
    pass


class ChainUpdate(ChainBase):
    pass


class ChainRead(ChainBase):
    id: int
    yaml_content: str
    created_at: datetime
    updated_at: datetime


class ImportRequest(BaseModel):
    yaml_content: str
    name: str | None = None
    description: str | None = None


class ValidationResult(BaseModel):
    valid: bool
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    yaml_content: str
    graph: GraphDocument


class ApplyRequest(BaseModel):
    name: str
    description: str | None = None
    graph: GraphDocument
    variables: dict[str, str] = Field(default_factory=dict)


class ApplyStageResult(BaseModel):
    node_id: str
    label: str
    stage_type: str
    mythic_uuid: str | None = None
    mythic_filename: str | None = None
    status: str
    detail: str | None = None


class ApplyResult(BaseModel):
    ok: bool
    chain_name: str
    stages: list[ApplyStageResult] = Field(default_factory=list)


class PreflightStageSupport(BaseModel):
    node_id: str
    label: str
    stage_type: str
    order: int
    upstream_labels: list[str] = Field(default_factory=list)
    supported_for_apply: bool
    action_summary: str | None = None
    reason: str | None = None


class PreflightStageSummary(BaseModel):
    total: int = 0
    base: int = 0
    wrapper: int = 0
    downloader: int = 0
    apply_supported: int = 0
    apply_unsupported: int = 0


class PreflightResult(BaseModel):
    can_apply: bool
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stage_summary: PreflightStageSummary = Field(default_factory=PreflightStageSummary)
    stages: list[PreflightStageSupport] = Field(default_factory=list)
    yaml_content: str = ''


class C2ProfileParameterDefinition(BaseModel):
    name: str
    parameter_type: str
    description: str = ''
    default_value: str = ''
    default_value_decoded: Any = None
    required: bool = False
    randomize: bool = False
    format_string: str = ''
    verifier_regex: str = ''
    choices: list[Any] = Field(default_factory=list)
    crypto_type: bool = False


class C2ProfileDefinition(BaseModel):
    name: str
    description: str = ''
    is_p2p: bool = False
    container_running: bool | None = None
    parameters: list[C2ProfileParameterDefinition] = Field(default_factory=list)


class BuildParameterDefinition(BaseModel):
    name: str
    parameter_type: str  # String, Number, Boolean, ChooseOne, ChooseMultiple, File, Date, Array
    description: str = ''
    default_value: str = ''
    default_value_decoded: Any = None
    required: bool = False
    randomize: bool = False
    choices: list[Any] = Field(default_factory=list)


class CommandDefinition(BaseModel):
    cmd: str
    description: str = ''
    needs_admin: bool = False
    supported_ui_features: list[str] = Field(default_factory=list)


class ComponentDefinition(BaseModel):
    type: str
    stage_type: str  # 'base', 'wrapper', 'downloader'
    label: str
    description: str
    note: str | None = None  # Free-text note from Mythic payload type
    supports_wrapper: bool = False
    supports_downloader: bool = False
    url_parameter: str | None = None  # Name of the URL build param (downloaders only)
    default_parameters: dict[str, Any] = Field(default_factory=dict)
    example_parameters: dict[str, Any] = Field(default_factory=dict)
    build_parameters_metadata: list[BuildParameterDefinition] = Field(default_factory=list)
    default_commands: list[str] = Field(default_factory=list)
    available_commands: list[CommandDefinition] = Field(default_factory=list)
    default_c2_profile: dict[str, Any] | None = None
    example_c2_profiles: list[dict[str, Any]] = Field(default_factory=list)
    available_c2_profiles: list[str] = Field(default_factory=list)
    c2_profiles_metadata: list[C2ProfileDefinition] = Field(default_factory=list)


class ComponentsResponse(BaseModel):
    source: str
    components: list[ComponentDefinition]
    warnings: list[str] = Field(default_factory=list)


class ComponentCatalogDebugResponse(BaseModel):
    source: str
    warnings: list[str] = Field(default_factory=list)
    raw_payload_types: list[dict[str, Any]] = Field(default_factory=list)


class SettingsRead(BaseModel):
    mythic_url: str | None = None
    mythic_username: str | None = None
    mythic_password_set: bool = False
    payload_server_url: str | None = None
    payload_server_token_set: bool = False


class SettingsWrite(BaseModel):
    mythic_url: str | None = None
    mythic_username: str | None = None
    mythic_password: str | None = None
    payload_server_url: str | None = None
    payload_server_token: str | None = None


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str


class PayloadTypeStat(BaseModel):
    name: str
    stage_type: str
    container_running: bool | None
    supported_os: list[str]
    description: str


class StatsResponse(BaseModel):
    source: str
    total: int
    base: int
    wrapper: int
    running: int
    stopped: int
    os_distribution: dict[str, int]
    payload_types: list[PayloadTypeStat]
    warnings: list[str] = Field(default_factory=list)


class MythicCallbackInfo(BaseModel):
    id: int
    agent_callback_id: str
    last_checkin: str | None
    active: bool
    host: str | None
    user: str | None


class MythicPayloadInfo(BaseModel):
    uuid: str
    agent_file_id: str | None
    filename: str
    payload_type: str
    build_phase: str
    os: str | None
    description: str | None
    creation_time: str | None
    md5: str | None
    sha1: str | None
    callbacks: list[MythicCallbackInfo] = Field(default_factory=list)


class ChainMythicPayloadsResponse(BaseModel):
    chain_name: str
    mythic_tag: str | None
    payloads: list[MythicPayloadInfo]
    warnings: list[str] = Field(default_factory=list)


class ChainStatusResponse(BaseModel):
    chain_id: int
    deployed: bool
    payload_count: int
    active_callbacks: int


class DeployRequest(BaseModel):
    chain_id: int
