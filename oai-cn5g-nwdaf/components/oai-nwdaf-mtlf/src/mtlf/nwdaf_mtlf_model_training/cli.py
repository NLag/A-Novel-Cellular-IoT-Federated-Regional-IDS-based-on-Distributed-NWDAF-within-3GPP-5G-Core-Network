"""Small command line helper for the normalized research workspace."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .scenarios import ScenarioDefinition, get_scenario, scenario_definitions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect normalized IDS/NWDAF research scenarios."
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Workspace root used when rendering legacy script paths.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-scenarios", help="List known training scenarios.")

    show_parser = subparsers.add_parser(
        "show-scenario",
        help="Show details for one training scenario.",
    )
    show_parser.add_argument("scenario", help="Scenario key.")

    command_parser = subparsers.add_parser(
        "legacy-command",
        help="Print the legacy command for one scenario without executing it.",
    )
    command_parser.add_argument("scenario", help="Scenario key.")

    args = parser.parse_args(argv)
    root = Path(args.root)

    if args.command == "list-scenarios":
        for scenario in scenario_definitions(root):
            print(f"{scenario.key}\t{scenario.title}")
        return 0

    scenario = get_scenario(args.scenario, root=root)
    if args.command == "show-scenario":
        print(json.dumps(_scenario_payload(scenario), indent=2, sort_keys=True))
        return 0

    if args.command == "legacy-command":
        print(" ".join(scenario.legacy_command()))
        return 0

    parser.error(f"unsupported command {args.command}")
    return 2


def _scenario_payload(scenario: ScenarioDefinition) -> dict[str, object]:
    return {
        "key": scenario.key,
        "title": scenario.title,
        "trainingStrategy": scenario.training_strategy,
        "legacyScript": str(scenario.legacy_script),
        "legacyCommand": list(scenario.legacy_command()),
        "datasetSplitName": scenario.dataset_split_name,
        "modelScope": scenario.model_scope,
        "usesPublicDataset": scenario.uses_public_dataset,
        "packageTargets": list(scenario.package_targets),
        "description": scenario.description,
    }


if __name__ == "__main__":
    raise SystemExit(main())

