"""Houdini compatibility layer.

Everything that touches ``hou`` directly and could break between Houdini
releases lives here:

* importing ``hou`` lazily so the pure-Python parts of the package (``core``)
  can be imported and unit-tested outside Houdini,
* resolving node type names (SideFX renames / re-versions nodes between
  releases, e.g. ``kinefx::fbxcharacterimport::2.0``),
* setting parameters defensively, because native node parameter names are not
  a stable public API.

Rule for the rest of the package: never call ``parent.createNode("x::y")`` or
``node.parm("foo").set()`` on a *native* node directly. Go through
:func:`create` and :func:`set_parms` so a missing node or renamed parameter
produces a clear log message instead of a half-built network.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

LOG = logging.getLogger("apex_studio")
if not LOG.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[ApexKinefxStudio] %(levelname)s: %(message)s"))
    LOG.addHandler(_handler)
LOG.setLevel(os.environ.get("APEX_KINEFX_STUDIO_LOGLEVEL", "INFO").upper())

try:  # pragma: no cover - only true inside Houdini / hython
    import hou  # type: ignore

    HOU_AVAILABLE = True
except ImportError:  # running tests or docs tooling outside Houdini
    hou = None  # type: ignore
    HOU_AVAILABLE = False


MIN_HOUDINI_VERSION = (20, 5)
TARGET_HOUDINI_VERSION = (22, 0)


class StudioError(RuntimeError):
    """Base error for ApexKinefxStudio."""


class MissingNodeTypeError(StudioError):
    """Raised when none of the candidate node types exist in this Houdini build."""


def require_hou():
    """Return the ``hou`` module or raise a helpful error outside Houdini."""
    if not HOU_AVAILABLE:
        raise StudioError(
            "This function needs Houdini's 'hou' module. Run it inside Houdini "
            "or with hython."
        )
    return hou


def houdini_version() -> tuple:
    """(major, minor, build) of the running Houdini, or (0, 0, 0) outside it."""
    if not HOU_AVAILABLE:
        return (0, 0, 0)
    return tuple(hou.applicationVersion())


# ---------------------------------------------------------------------------
# Node type resolution
# ---------------------------------------------------------------------------

#: Logical key -> ordered candidate SOP node type names. The first one that
#: exists wins; versioned variants (``name::2.0``) are discovered
#: automatically, highest version first. Run ``tools/probe_node_types.py`` in
#: your Houdini build to verify / extend this table.
SOP_NODE_CANDIDATES: Dict[str, List[str]] = {
    # --- generic SOPs --------------------------------------------------
    "attribwrangle": ["attribwrangle"],
    "python": ["python"],
    "null": ["null"],
    "merge": ["merge"],
    "switch": ["switch"],
    "object_merge": ["object_merge"],
    "file": ["file"],
    "timeshift": ["timeshift"],
    "resample": ["resample"],
    "solver": ["solver"],
    "dopnet": ["dopnet"],
    "box": ["box"],
    "sphere": ["sphere"],
    "heightfield": ["heightfield"],
    "heightfield_noise": ["heightfield_noise"],
    "curve": ["curve::2.0", "curve"],
    "pack": ["pack"],
    "pack_folder": ["packfolder"],
    "unpack": ["unpack"],
    "normal": ["normal"],
    "copytopoints": ["copytopoints::2.0", "copytopoints"],
    "transform": ["xform"],
    # --- KineFX ----------------------------------------------------------
    "fbx_character_import": ["kinefx::fbxcharacterimport"],
    "fbx_anim_import": ["kinefx::fbxanimimport"],
    "fbx_skin_import": ["kinefx::fbxskinimport"],
    "skeleton": ["kinefx::skeleton"],
    "rig_doctor": ["kinefx::rigdoctor"],
    "rig_pose": ["kinefx::rigpose"],
    "rig_match_pose": ["kinefx::rigmatchpose"],
    "map_points": ["kinefx::mappoints"],
    "full_body_ik": ["kinefx::fullbodyik"],
    "rig_stash_pose": ["kinefx::rigstashpose"],
    "joint_capture_biharmonic": ["kinefx::jointcapturebiharmonic"],
    "joint_capture_proximity": ["kinefx::jointcaptureproximity"],
    "capture_correct": ["kinefx::capturecorrect", "capturecorrect"],
    "joint_deform": ["kinefx::jointdeform", "bonedeform"],
    "secondary_motion": ["kinefx::secondarymotion"],
    "motion_clip": ["kinefx::motionclip"],
    "motion_clip_evaluate": ["kinefx::motionclipevaluate"],
    "ragdoll_solver": ["kinefx::ragdollsolver"],
    # --- APEX -----------------------------------------------------------
    "apex_autorig_component": ["apex::autorigcomponent"],
    "apex_rigscript_component": ["apex::rigscriptcomponent"],
    "apex_animation_from_skeleton": ["apex::animationfromskeleton"],
    "apex_configure_controls": ["apex::configurecontrols"],
    "apex_scene_add_character": ["apex::sceneaddcharacter"],
    "apex_scene_animate": ["apex::sceneanimate"],
    "apex_scene_invoke": ["apex::sceneinvoke"],
    "apex_script": ["apex::script"],
    "pack_character": ["packcharacter", "apex::packcharacter"],
    "unpack_character": ["unpackcharacter", "apex::unpackcharacter"],
    # --- Crowds (SOP level) ------------------------------------------------
    "agent": ["agent"],
    "agent_from_rig": ["agentfromrig", "kinefx::agentfromrig"],
    "agent_prep": ["agentprep"],
    "agent_clip": ["agentclip"],
    "agent_layer": ["agentlayer"],
    "agent_configure_joints": ["agentconfigurejoints"],
    "agent_terrain_adaptation": ["agentterrainadaptation"],
    "crowd_source": ["crowdsource"],
}

#: Logical key -> candidate DOP node types (used inside a DOP Network SOP).
DOP_NODE_CANDIDATES: Dict[str, List[str]] = {
    "crowd_object": ["crowdobject"],
    "crowd_solver": ["crowdsolver"],
    "crowd_state": ["crowdstate"],
    "crowd_transition": ["crowdtransition"],
    "crowd_trigger": ["crowdtrigger"],
    "crowd_trigger_logic": ["crowdtriggerlogic"],
    "pop_wrangle": ["popwrangle"],
    "pop_steer_avoid": ["popsteeravoid"],
    "pop_steer_path": ["popsteerpath"],
    "pop_steer_wander": ["popsteerwander"],
    "ground_plane": ["groundplane"],
    "merge": ["merge"],
    "output": ["output"],
}

_VERSION_RE = re.compile(r"^(?P<base>.+?)::(?P<ver>\d+(?:\.\d+)*)$")


def _version_key(ver: str) -> tuple:
    return tuple(int(p) for p in ver.split("."))


def _category(kind: str):
    h = require_hou()
    return {"sop": h.sopNodeTypeCategory(), "dop": h.dopNodeTypeCategory(),
            "obj": h.objNodeTypeCategory()}[kind]


def resolve_type(key_or_name: str, kind: str = "sop") -> Optional[str]:
    """Return the best existing node type name for a logical key, or None.

    ``key_or_name`` can be a key of the candidate tables or a raw type name.
    Versioned types are preferred, highest version first: asking for
    ``kinefx::fbxcharacterimport`` returns ``kinefx::fbxcharacterimport::2.0``
    when that exists.
    """
    table = SOP_NODE_CANDIDATES if kind == "sop" else DOP_NODE_CANDIDATES
    candidates = table.get(key_or_name, [key_or_name])
    available = _category(kind).nodeTypes()
    for cand in candidates:
        versions = []
        for name in available:
            m = _VERSION_RE.match(name)
            if m and m.group("base") == cand:
                versions.append((_version_key(m.group("ver")), name))
        if versions:
            versions.sort(reverse=True)
            return versions[0][1]
        if cand in available:
            return cand
    return None


def has_type(key_or_name: str, kind: str = "sop") -> bool:
    return resolve_type(key_or_name, kind) is not None


def create(parent, key_or_name: str, name: Optional[str] = None, kind: str = "sop",
           required: bool = True):
    """Create a node from a logical key, resolving the real type name.

    Returns the new node. If no candidate exists, raises
    :class:`MissingNodeTypeError` when ``required`` else logs and returns None.
    """
    type_name = resolve_type(key_or_name, kind)
    if type_name is None:
        msg = (f"No node type available for '{key_or_name}' ({kind}). "
               f"Run tools/probe_node_types.py and update compat.SOP_NODE_CANDIDATES.")
        if required:
            raise MissingNodeTypeError(msg)
        LOG.warning(msg)
        return None
    node = parent.createNode(type_name, name) if name else parent.createNode(type_name)
    return node


# ---------------------------------------------------------------------------
# Parameter helpers
# ---------------------------------------------------------------------------

def _set_one(parm, value) -> None:
    """Set a parm, translating menu tokens to indices when needed."""
    h = require_hou()
    tmpl = parm.parmTemplate()
    if isinstance(value, str) and tmpl.type() == h.parmTemplateType.Menu:
        items = list(parm.menuItems())
        if value in items:
            parm.set(items.index(value))
            return
        labels = list(parm.menuLabels())
        if value in labels:
            parm.set(labels.index(value))
            return
    if (isinstance(value, str) and tmpl.type() == h.parmTemplateType.Int
            and tmpl.menuItems()):
        items = list(tmpl.menuItems())
        if value in items:
            parm.set(items.index(value))
            return
    parm.set(value)


def set_parm(node, names: Iterable[str] | str, value: Any, warn: bool = True) -> bool:
    """Set the first existing parm (or parm tuple) from ``names``.

    Returns True on success. Never raises for a missing parm: native parm names
    drift between releases, and a warning is more useful than a crash halfway
    through building a network.
    """
    if isinstance(names, str):
        names = [names]
    names = list(names)
    for n in names:
        tup = node.parmTuple(n)
        if tup is not None and isinstance(value, (list, tuple)) and len(tup) == len(value):
            tup.set(value)
            return True
        p = node.parm(n)
        if p is not None:
            try:
                _set_one(p, value)
                return True
            except Exception as exc:  # hou.Error subclasses vary per parm type
                LOG.warning("Could not set %s/%s = %r (%s)", node.path(), n, value, exc)
                return False
    if warn:
        LOG.warning("None of the parms %s exist on %s (%s); left at default.",
                    names, node.path(), node.type().name())
    return False


def set_parms(node, values: Dict[Any, Any], warn: bool = True) -> None:
    """Set several parms. Keys may be a name or a tuple of candidate names."""
    for key, value in values.items():
        names = list(key) if isinstance(key, tuple) else [key]
        set_parm(node, names, value, warn=warn)


def set_expression(node, name: str, expr: str, language: str = "hscript") -> bool:
    h = require_hou()
    p = node.parm(name)
    if p is None:
        LOG.warning("No parm %s on %s for expression", name, node.path())
        return False
    lang = h.exprLanguage.Python if language == "python" else h.exprLanguage.Hscript
    p.setExpression(expr, lang)
    return True


def connect_by_label(dst, src, keywords: Sequence[str], fallback_index: Optional[int] = None,
                     output_index: int = 0) -> bool:
    """Wire ``src`` into the first input of ``dst`` whose label matches a keyword.

    Input order of many native nodes (crowd solver, full body IK, ...) is not
    documented as stable; labels are more reliable.
    """
    labels = [l.lower() for l in dst.inputLabels()]
    for kw in keywords:
        for i, label in enumerate(labels):
            if kw.lower() in label:
                dst.setInput(i, src, output_index)
                return True
    if fallback_index is not None:
        dst.setInput(fallback_index, src, output_index)
        LOG.info("Wired %s -> %s input %d (fallback, labels=%s)",
                 src.path(), dst.path(), fallback_index, labels)
        return True
    LOG.warning("No input on %s matches %s (labels=%s)", dst.path(), keywords, labels)
    return False


def probe(kind: str = "sop", patterns: Sequence[str] = ("kinefx", "apex", "agent", "crowd")) -> Dict[str, List[str]]:
    """List installed node types that match ``patterns`` (used by tools/probe_node_types.py)."""
    result: Dict[str, List[str]] = {}
    for name in sorted(_category(kind).nodeTypes()):
        for pat in patterns:
            if pat in name:
                result.setdefault(pat, []).append(name)
    return result


def resolution_report() -> Dict[str, Optional[str]]:
    """Resolve every logical key; handy for startup validation."""
    report: Dict[str, Optional[str]] = {}
    for key in SOP_NODE_CANDIDATES:
        report[f"sop:{key}"] = resolve_type(key, "sop")
    for key in DOP_NODE_CANDIDATES:
        report[f"dop:{key}"] = resolve_type(key, "dop")
    return report
