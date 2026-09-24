"""List the KineFX / APEX / crowd node types of *your* Houdini build.

    hython tools/probe_node_types.py [out.json]

Writes a JSON report with every matching SOP/DOP type and how each logical
key in apex_studio.compat resolved. Share it when something fails to build:
node type names are the main thing that changes between Houdini releases.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "python"))

import hou  # noqa: E402  (hython)

from apex_studio import compat  # noqa: E402


def main(out_path: str) -> None:
    report = {
        "houdini": hou.applicationVersionString(),
        "sop": compat.probe("sop", ("kinefx", "apex", "agent", "crowd", "ragdoll", "motion", "rig")),
        "dop": compat.probe("dop", ("crowd", "agent", "ragdoll", "pop")),
        "resolved": compat.resolution_report(),
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    missing = [k for k, v in report["resolved"].items() if v is None]
    print(f"Houdini {report['houdini']}: wrote {out_path}")
    print(f"Unresolved keys ({len(missing)}): {', '.join(missing) or 'none'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "node_types_report.json")
