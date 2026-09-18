#!/usr/bin/env python3
"""Validate the canonical SubAgent Definition/Profile catalog."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Runtime.ReferenceImplementation.profiles import CATALOG, ProfileValidationError, SubAgentProfileCatalog


def main() -> int:
    try:
        catalog = SubAgentProfileCatalog.from_file(ROOT / "Runtime/ReferenceImplementation/subagent-catalog.yaml")
        definitions = catalog.definitions()
        if not definitions:
            raise ProfileValidationError("catalog contains no SubAgent definitions")
        provider_ids = [definition.profile.provider_id for definition in definitions]
        if len(provider_ids) != len(set(provider_ids)):
            raise ProfileValidationError("provider_id values must be unique")
        for definition in definitions:
            if definition.profile.activation["auto_install"] is not False:
                raise ProfileValidationError("SubAgent profiles must not auto-install")
            if definition.profile.activation["install_mode"] != "optional":
                raise ProfileValidationError("SubAgent profiles must remain optional")
        goal_types = [definition.profile.goal_type for definition in definitions]
        if len(goal_types) != len(set(goal_types)):
            raise ProfileValidationError("goal_type values must be unique")
        if catalog.default_profile_id != CATALOG.default_profile_id:
            raise ProfileValidationError("loaded catalog default differs from the runtime catalog")
    except Exception as exc:
        print(f"SubAgent profile catalog validation failed: {exc}")
        return 1
    print(f"SubAgent profile catalog validation passed ({len(definitions)} definition(s)).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
