"""Startup / on-demand validation of the Houdini environment.

``python -c "import apex_studio.validate as v; v.report()"`` in hython, or the
"Validate" shelf tool, prints which native KineFX / APEX / crowd nodes this
package resolved, and warns about anything missing.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from . import compat, network
from .compat import LOG

CRITICAL = ["sop:attribwrangle", "sop:python", "sop:solver", "sop:null", "sop:object_merge"]
IMPORTANT = ["sop:fbx_character_import", "sop:joint_deform", "sop:joint_capture_biharmonic",
             "sop:rig_match_pose", "sop:copytopoints", "sop:agent"]


def check_vex_files() -> List[str]:
    """Snippets that fail to load (missing include etc.)."""
    bad = []
    snippets_dir = os.path.join(network.VEX_ROOT, "snippets")
    if not os.path.isdir(snippets_dir):
        return [f"missing folder {snippets_dir}"]
    for fn in sorted(os.listdir(snippets_dir)):
        if fn.endswith(".vfl"):
            try:
                network.load_vex(fn)
            except OSError as exc:
                bad.append(f"{fn}: {exc}")
    return bad


def report(verbose: bool = False) -> Dict[str, Optional[str]]:
    """Log the resolution table; returns it."""
    if not compat.HOU_AVAILABLE:
        LOG.info("Not running inside Houdini; only VEX files were checked.")
        for msg in check_vex_files():
            LOG.error(msg)
        return {}
    version = ".".join(str(v) for v in compat.houdini_version())
    LOG.info("Houdini %s, package root %s", version, network.PACKAGE_ROOT)
    if compat.houdini_version()[:2] < compat.MIN_HOUDINI_VERSION:
        LOG.warning("ApexKinefxStudio targets Houdini %s+ (tested design target %s).",
                    ".".join(map(str, compat.MIN_HOUDINI_VERSION)),
                    ".".join(map(str, compat.TARGET_HOUDINI_VERSION)))
    table = compat.resolution_report()
    for key in CRITICAL:
        if not table.get(key):
            LOG.error("Missing critical node type %s", key)
    for key in IMPORTANT:
        if not table.get(key):
            LOG.warning("Missing node type %s (related features degrade gracefully)", key)
    missing = [k for k, v in table.items() if v is None]
    LOG.info("Resolved %d/%d node types.%s", len(table) - len(missing), len(table),
             f" Missing: {', '.join(missing)}" if missing else "")
    if verbose:
        for k, v in sorted(table.items()):
            LOG.info("  %-40s %s", k, v)
    for msg in check_vex_files():
        LOG.error(msg)
    return table
