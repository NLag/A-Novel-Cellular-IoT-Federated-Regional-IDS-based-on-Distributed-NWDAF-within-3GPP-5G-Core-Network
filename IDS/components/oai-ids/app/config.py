from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import uuid

import yaml

from .dataset_capture import DatasetCaptureConfig


@dataclass
class GtpuConfig:
    host: str = "0.0.0.0"
    port: int = 2152


@dataclass
class HttpConfig:
    host: str = "0.0.0.0"
    port: int = 8080


@dataclass
class ClassifierConfig:
    packet_mtu: int = 1500
    seed: int = 1337
    hidden_layers: list[int] = field(default_factory=lambda: [256, 64])
    mode: str = "heuristic"
    malicious_packet_size_threshold: int = 512
    high_byte_ratio_threshold: float = 0.60


@dataclass
class ModelRegistryConfig:
    enabled: bool = True
    mode: str = "placeholder"
    artifact_path: str = ""
    registry_uri: str = ""
    request_timeout_seconds: int = 3
    model_version: str = "placeholder-v1"
    architecture: str = "deterministic-placeholder"
    artifact_type: str = "placeholder"
    source_nf: str = "LOCAL"
    source_nf_instance_id: str = "oai-ids-placeholder"
    source_uri: str = ""
    checksum: str = ""
    sequence_size: int = 1
    label_map: dict = field(default_factory=lambda: {0: "benign", 1: "malicious"})


@dataclass
class ServingAreaConfig:
    region: str = "default"
    mcc: str = "001"
    mnc: str = "01"
    tac: str = "000001"


@dataclass
class ReportsConfig:
    storage: str = "memory"
    file_path: str = "/tmp/oai-ids/reports.jsonl"


@dataclass
class CountermeasureConfig:
    mode: str = "observe-only"
    active_enabled: bool = False
    smf_pdu_session_release_enabled: bool = False
    amf_ue_context_release_enabled: bool = False
    udm_service_restriction_enabled: bool = False
    pcf_policy_update_enabled: bool = False
    smf_base_uri: str = "http://oai-smf:80"
    amf_base_uri: str = "http://oai-amf:80"
    udm_base_uri: str = "http://oai-udm:80"
    pcf_base_uri: str = "http://oai-pcf:80"


@dataclass
class TrafficInfluenceConfig:
    enabled: bool = False
    mode: str = "disabled"
    pcf_base_uri: str = "http://oai-pcf:80/npcf-smpolicycontrol/v1"
    supi: str = "imsi-001010000000001"
    pdu_session_id: int = 1
    pdu_session_type: str = "IPV4"
    dnn: str = "oai"
    snssai_sst: int = 1
    snssai_sd: str = ""
    notification_uri: str = "http://oai-ids:8080/nids-event-exposure/v1/notifications"
    request_timeout_seconds: int = 3
    max_attempts: int = 3
    retry_interval_seconds: float = 5.0
    duplication_policy_id: str = "ids-duplication"
    duplication_teid: int = 1


@dataclass
class NwdafIntegrationConfig:
    enabled: bool = False
    mode: str = "disabled"
    base_uri: str = "http://oai-nwdaf-mtlf-service:8082/nnwdaf-mlmodelprovision/v1"
    notification_uri: str = "http://oai-ids:8080/nids-model-management/v1/model-notifications"
    fetch_model_metadata: bool = False
    report_forwarding_enabled: bool = False
    report_forwarding_uri: str = "http://oai-nwdaf-dccf:8081/ndccf-datamanagement/v1/ids-reports"
    notif_correlation_id: str = "oai-ids-model-updates"
    ml_event: str = "ABNORMAL_BEHAVIOUR"
    supported_features: str = "0"
    expiry: str = ""
    request_timeout_seconds: int = 3
    max_attempts: int = 3
    retry_interval_seconds: float = 5.0


@dataclass
class NrfConfig:
    base_uri: str = "http://oai-nrf:80/nnrf-nfm/v1"
    nf_instance_id: str = field(
        default_factory=lambda: os.getenv("IDS_NF_INSTANCE_ID", str(uuid.uuid4()))
    )
    nf_type: str = "AF"
    nf_status: str = "REGISTERED"
    heart_beat_timer: int = 30
    service_name: str = "oai-ids-monitoring"
    service_version: str = "v1"


@dataclass
class AlertingConfig:
    """Sliding-window gate: only notify after sustained malicious activity.

    Suppresses isolated false positives and cuts CP signaling — a notification
    (NWDAF report + countermeasure) is raised once ``threshold`` of the last
    ``window`` inspected packets are malicious, and re-armed after the count
    falls back to ``clear_below``.
    """

    enabled: bool = True
    window: int = 50
    threshold: int = 10
    clear_below: int = 3


@dataclass
class IdsConfig:
    host: str = "oai-ids"
    instance_id: str = field(
        default_factory=lambda: os.getenv("IDS_INSTANCE_ID", str(uuid.uuid4()))
    )
    serving_area: ServingAreaConfig = field(default_factory=ServingAreaConfig)
    gtpu: GtpuConfig = field(default_factory=GtpuConfig)
    http: HttpConfig = field(default_factory=HttpConfig)
    classifier: ClassifierConfig = field(default_factory=ClassifierConfig)
    model_registry: ModelRegistryConfig = field(default_factory=ModelRegistryConfig)
    reports: ReportsConfig = field(default_factory=ReportsConfig)
    countermeasures: CountermeasureConfig = field(default_factory=CountermeasureConfig)
    traffic_influence: TrafficInfluenceConfig = field(
        default_factory=TrafficInfluenceConfig
    )
    nwdaf_integration: NwdafIntegrationConfig = field(
        default_factory=NwdafIntegrationConfig
    )
    dataset_capture: DatasetCaptureConfig = field(default_factory=DatasetCaptureConfig)
    alerting: AlertingConfig = field(default_factory=AlertingConfig)
    nrf: NrfConfig = field(default_factory=NrfConfig)


def _merge_dataclass(dataclass_type, data: dict):
    field_names = dataclass_type.__dataclass_fields__.keys()
    filtered = {key: value for key, value in data.items() if key in field_names}
    return dataclass_type(**filtered)


def load_config(path: str | Path) -> IdsConfig:
    config_path = Path(path)
    if not config_path.exists():
        return IdsConfig()

    with config_path.open("r", encoding="utf-8") as stream:
        raw = yaml.safe_load(stream) or {}

    ids_config = raw.get("ids", raw)
    config = IdsConfig()

    if "host" in ids_config:
        config.host = ids_config["host"]
    if "instanceId" in ids_config:
        config.instance_id = ids_config["instanceId"]
    if "servingArea" in ids_config:
        config.serving_area = _merge_dataclass(
            ServingAreaConfig, ids_config["servingArea"] or {}
        )
    if "gtpu" in ids_config:
        config.gtpu = _merge_dataclass(GtpuConfig, ids_config["gtpu"] or {})
    if "http" in ids_config:
        config.http = _merge_dataclass(HttpConfig, ids_config["http"] or {})
    if "classifier" in ids_config:
        config.classifier = _merge_dataclass(
            ClassifierConfig, ids_config["classifier"] or {}
        )
    if "modelRegistry" in ids_config:
        config.model_registry = _merge_dataclass(
            ModelRegistryConfig, ids_config["modelRegistry"] or {}
        )
    if "reports" in ids_config:
        config.reports = _merge_dataclass(ReportsConfig, ids_config["reports"] or {})
    if "countermeasures" in ids_config:
        config.countermeasures = _merge_dataclass(
            CountermeasureConfig, ids_config["countermeasures"] or {}
        )
    if "trafficInfluence" in ids_config:
        config.traffic_influence = _merge_dataclass(
            TrafficInfluenceConfig, ids_config["trafficInfluence"] or {}
        )
    if "nwdafIntegration" in ids_config:
        config.nwdaf_integration = _merge_dataclass(
            NwdafIntegrationConfig, ids_config["nwdafIntegration"] or {}
        )
    if "datasetCapture" in ids_config:
        config.dataset_capture = _merge_dataclass(
            DatasetCaptureConfig, ids_config["datasetCapture"] or {}
        )
    if "alerting" in ids_config:
        config.alerting = _merge_dataclass(AlertingConfig, ids_config["alerting"] or {})
    if "nrf" in ids_config:
        config.nrf = _merge_dataclass(NrfConfig, ids_config["nrf"] or {})

    return config
