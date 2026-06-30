from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import CountermeasureConfig


@dataclass(frozen=True)
class CountermeasureSpec:
    name: str
    target_nf: str
    interface: str
    service: str
    gate_field: str
    base_uri_field: str


COUNTERMEASURE_SPECS = (
    CountermeasureSpec(
        name="smf-pdu-session-release",
        target_nf="SMF",
        interface="Nids-Nsmf",
        service="Nsmf_PDUSession_Release",
        gate_field="smf_pdu_session_release_enabled",
        base_uri_field="smf_base_uri",
    ),
    CountermeasureSpec(
        name="amf-ue-context-release",
        target_nf="AMF",
        interface="Nids-Namf",
        service="Namf_Communication_ReleaseUEContext",
        gate_field="amf_ue_context_release_enabled",
        base_uri_field="amf_base_uri",
    ),
    CountermeasureSpec(
        name="udm-service-restriction",
        target_nf="UDM",
        interface="Nids-Nudm",
        service="Nudm_UECM_DeregistrationOrServiceRestriction",
        gate_field="udm_service_restriction_enabled",
        base_uri_field="udm_base_uri",
    ),
    CountermeasureSpec(
        name="pcf-smf-policy-update",
        target_nf="PCF/SMF",
        interface="Nids-Npcf/N7/N4",
        service="Npcf_SMPolicyControl_Update",
        gate_field="pcf_policy_update_enabled",
        base_uri_field="pcf_base_uri",
    ),
)


def build_countermeasure_plan(
    config: CountermeasureConfig,
    predicted_class: str,
    report_context: dict[str, Any],
) -> list[dict[str, Any]]:
    if predicted_class == "benign" or config.mode == "disabled":
        return []

    return [
        _build_action(config=config, spec=spec, report_context=report_context)
        for spec in COUNTERMEASURE_SPECS
    ]


def summarize_report_action(
    predicted_class: str,
    config: CountermeasureConfig,
    planned_countermeasures: list[dict[str, Any]],
) -> str:
    if predicted_class == "benign":
        return "none"
    if config.mode == "disabled":
        return "countermeasure-disabled"
    if config.mode == "observe-only":
        return "observe-only-countermeasure-planned"
    if any(action["status"] == "stub-active-not-called" for action in planned_countermeasures):
        return "countermeasure-stub-not-called"
    return "countermeasure-blocked-by-config"


def _build_action(
    config: CountermeasureConfig,
    spec: CountermeasureSpec,
    report_context: dict[str, Any],
) -> dict[str, Any]:
    gate_enabled = bool(getattr(config, spec.gate_field))
    base_uri = str(getattr(config, spec.base_uri_field))
    status = _status(config=config, gate_enabled=gate_enabled)

    return {
        "name": spec.name,
        "targetNf": spec.target_nf,
        "interface": spec.interface,
        "service": spec.service,
        "baseUri": base_uri,
        "enabled": gate_enabled,
        "mode": config.mode,
        "status": status,
        "called": False,
        "reason": _reason(config=config, gate_enabled=gate_enabled),
        "context": {
            "ueIp": report_context.get("ueIp"),
            "teid": report_context.get("teid"),
            "region": report_context.get("region"),
            "tac": report_context.get("tac"),
            "predictedClass": report_context.get("predictedClass"),
            "score": report_context.get("score"),
        },
    }


def _status(config: CountermeasureConfig, gate_enabled: bool) -> str:
    if config.mode == "observe-only":
        return "observe-only"
    if config.mode == "active" and config.active_enabled and gate_enabled:
        return "stub-active-not-called"
    return "blocked-by-config"


def _reason(config: CountermeasureConfig, gate_enabled: bool) -> str:
    if config.mode == "observe-only":
        return "observe-only mode records the intended NF action without calling it"
    if config.mode != "active":
        return "countermeasure mode is not active"
    if not config.active_enabled:
        return "global active countermeasure gate is disabled"
    if not gate_enabled:
        return "per-countermeasure active gate is disabled"
    return "active countermeasure client is a stub in Phase 1"
