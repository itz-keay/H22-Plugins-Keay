"""Universal Retargeting Engine: Mixamo / Cascadeur / UE5 / custom -> any KineFX rig.

Network built by :func:`build_retarget` (inside ``/obj/<name>``)::

    source FBX (Character Import) ─┬─ rest ── pose_match ──────────┐
                                   └─ animated ─────────────────────┤
    target FBX (Character Import) ─┬─ rest skel ── assign_map ── world_delta_retarget
                                   │                                  │
                                   │                      (optional) foot_lock (SOP Solver)
                                   └─ rest geometry ─────────────── Joint Deform ── OUT_MESH

* Joint mapping is automatic (:mod:`core.profiles`): profiles are detected
  from joint names, mapped through canonical names, with fuzzy matching for
  the rest. The mapping is baked into the ``assign_map`` wrangle as two
  arrays, so it is visible and editable by hand.
* ``pose_match`` rotates the source rest pose onto the target's (T-pose vs
  A-pose), then ``world_delta_retarget`` copies world-space rotation deltas
  and rebuilds positions with the target's bone lengths (no stretching).
* Optionally a *native* branch is built next to it with SideFX's Rig Match
  Pose -> Map Points -> Full Body IK, switchable with a Switch SOP, so you can
  compare against the stock KineFX workflow.
* :func:`apex_retarget` hands the result to ``APEX Animation from Skeleton``
  when you already have an APEX character.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import compat, network
from .compat import LOG, require_hou
from .core import profiles
from .network import ParmSpec
from .rigging import common

# Re-exported pure helpers (usable without Houdini)
detect_profile = profiles.detect_profile
auto_map = profiles.auto_map
missing_core = profiles.missing_core


@dataclass
class RetargetOptions:
    source_profile: Optional[str] = None      # None = auto-detect
    target_profile: Optional[str] = None
    mapping_overrides: Dict[str, str] = field(default_factory=dict)  # target -> source
    root_motion: str = "keep"                 # keep | in_place | none
    auto_scale: bool = True
    foot_lock: bool = True
    feet: Optional[Sequence[str]] = None      # target foot joint names (auto if None)
    build_native_branch: bool = True
    apex_character: bool = False              # also package target as an APEX character


ROOT_MOTION = {"keep": 0, "in_place": 1, "none": 2}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def mapping_to_vex(mapping: Dict[str, str]) -> str:
    """Return the ``retarget_assign_map`` snippet with the mapping arrays filled in."""
    def arr(values: Sequence[str]) -> str:
        esc = ['"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"' for v in values]
        return "{" + ", ".join(esc) + "}"

    targets = sorted(mapping)
    sources = [mapping[t] for t in targets]
    code = network.load_vex("retarget_assign_map")
    code = code.replace("string AKS_TARGETS[] = {};", f"string AKS_TARGETS[] = {arr(targets)};")
    code = code.replace("string AKS_SOURCES[] = {};", f"string AKS_SOURCES[] = {arr(sources)};")
    return code


def find_feet(target_names: Sequence[str], profile: Optional[str] = None) -> List[str]:
    """Target joints that play the role of left/right foot."""
    canon = profiles.to_canonical(target_names, profile)
    return [name for name, c in canon.items() if c in ("l_foot", "r_foot")]


def find_hips(target_names: Sequence[str], profile: Optional[str] = None) -> Optional[str]:
    canon = profiles.to_canonical(target_names, profile)
    for name, c in canon.items():
        if c == "hips":
            return name
    return None


# ---------------------------------------------------------------------------
# Houdini side
# ---------------------------------------------------------------------------

def joint_names(sop_node, output_index: int = 0) -> List[str]:
    """Joint names of a skeleton output (cooks the node; [] if it fails to cook)."""
    try:
        geo = sop_node.geometry(output_index) if output_index else sop_node.geometry()
    except Exception as exc:  # hou.OperationFailed / hou.Error: e.g. empty FBX path
        LOG.warning("Could not cook %s: %s", sop_node.path(), exc)
        return []
    if geo is None:
        return []
    attrib = geo.findPointAttrib("name")
    if attrib is None:
        return []
    return list(geo.pointStringAttribValues("name"))


def import_character(parent, name: str, source):
    """FBX path -> FBX Character Import (outputs: 0 rest geo, 1 rest skeleton,
    2 animated skeleton). A SOP node or other file -> used as the animated
    skeleton directly. Returns (node, rest_geo_out, rest_skel_out, anim_out),
    where the *_out values are (node, output_index) tuples.
    """
    h = require_hou()
    if isinstance(source, str) and source.lower().endswith(".fbx"):
        node = compat.create(parent, "fbx_character_import", name)
        compat.set_parm(node, ("fbxfile", "file", "filename"), source)
        return node, (node, 0), (node, 1), (node, 2)
    src = network.input_or_placeholder(parent, name, source)
    # a plain skeleton: frame 1 = rest when no separate rest pose is given
    rest = compat.create(parent, "timeshift", f"{name}_rest_frame")
    rest.setInput(0, src)
    compat.set_parm(rest, "frame", 1)
    compat.set_expression(rest, "frame", "$FSTART")
    return src, (src, 0), (rest, 0), (src, 0)


def _wire(dst, idx: int, out: Tuple[object, int]) -> None:
    node, oi = out
    dst.setInput(idx, node, oi)


def build_retarget(source, target, name: str = "aks_retarget",
                   options: Optional[RetargetOptions] = None, target_mesh=None):
    """Build the full retarget network. Returns the container OBJ node.

    ``source``: animated FBX path (Mixamo, Cascadeur...), or SOP node / geometry file.
    ``target``: rigged FBX path, or a SOP node / file with the target skeleton.
    ``target_mesh``: optional captured mesh when ``target`` is not an FBX.
    """
    require_hou()
    opts = options or RetargetOptions()
    geo = network.obj_container(name, clear=True)

    src_node, _, src_rest, src_anim = import_character(geo, "source", source)
    tgt_node, tgt_geo, tgt_rest, _ = import_character(geo, "target", target)

    # --- mapping --------------------------------------------------------------------
    src_names = joint_names(src_rest[0], src_rest[1])
    tgt_names = joint_names(tgt_rest[0], tgt_rest[1])
    mapping = profiles.auto_map(src_names, tgt_names, opts.source_profile, opts.target_profile)
    mapping.update(opts.mapping_overrides)
    missing = profiles.missing_core(mapping, tgt_names, opts.target_profile)
    sp, sscore = profiles.detect_profile(src_names)
    tp, tscore = profiles.detect_profile(tgt_names)
    LOG.info("Retarget: source profile %s (%.0f%%), target profile %s (%.0f%%), %d joints mapped",
             sp, sscore * 100, tp, tscore * 100, len(mapping))
    if missing:
        LOG.warning("Unmapped core joints on the target: %s", ", ".join(missing))

    assign = network.wrangle(geo, "assign_map", mapping_to_vex(mapping), run_over="points",
                             from_file=False)
    _wire(assign, 0, tgt_rest)

    # --- pose match + retarget --------------------------------------------------------------
    pose_match = network.wrangle(geo, "pose_match", "retarget_pose_match", run_over="detail")
    _wire(pose_match, 0, src_rest)
    pose_match.setInput(1, assign)

    hips = find_hips(tgt_names, opts.target_profile) or "hips"
    retarget = network.wrangle(geo, "world_delta_retarget", "retarget_world_delta", run_over="detail",
                               parms=[
                                   ParmSpec("hips_joint", "Hips Joint", "string", hips),
                                   ParmSpec("root_motion", "Root Motion", "menu", opts.root_motion,
                                            menu=[("keep", "Keep"), ("in_place", "In Place (lock XZ)"),
                                                  ("none", "No Translation")]),
                                   ParmSpec("auto_scale", "Auto Scale by Hip Height", "toggle", opts.auto_scale),
                                   ParmSpec("translation_scale", "Translation Scale", "float", 1.0, 0, 2),
                               ])
    retarget.setInput(0, assign)
    _wire(retarget, 1, src_anim)
    retarget.setInput(2, pose_match)
    anim = retarget

    # --- native KineFX branch (comparison / fallback) -------------------------------------------
    if opts.build_native_branch:
        anim = _native_branch(geo, assign, src_rest, src_anim, retarget) or retarget

    # --- foot lock ----------------------------------------------------------------------------
    if opts.foot_lock:
        feet = list(opts.feet) if opts.feet else find_feet(tgt_names, opts.target_profile)
        anim = add_foot_lock(geo, anim, feet)

    # --- deformation ----------------------------------------------------------------------------
    mesh_out = None
    if isinstance(target, str) and target.lower().endswith(".fbx"):
        deform = compat.create(geo, "joint_deform", "deform")
        _wire(deform, 0, tgt_geo)
        _wire(deform, 1, tgt_rest)
        deform.setInput(2, anim)
        mesh_out = deform
    elif target_mesh is not None:
        mesh_in = network.input_or_placeholder(geo, "target_mesh", target_mesh)
        rest_null = network.null(geo, "target_rest")
        _wire(rest_null, 0, tgt_rest)
        mesh_out = common.skin(geo, mesh_in, rest_null, anim).deformed

    rest_null = network.null(geo, "REST_SKELETON")
    _wire(rest_null, 0, tgt_rest)
    outs = common.outputs(geo, rest_null, anim, mesh_out)
    if opts.apex_character and mesh_out is not None:
        common.apex_character(geo, network.null(geo, "apex_mesh_in", _node_of(tgt_geo)), rest_null)

    network.note(geo, f"Retarget {sp or 'custom'} -> {tp or 'custom'}\n"
                      f"{len(mapping)} joints mapped. Unmapped core joints: {', '.join(missing) or 'none'}.\n"
                      "Edit the arrays in 'assign_map' to fix a mapping by hand.", near=assign)
    network.finalize(geo, outs.get("mesh", outs["anim"]))
    return geo


def rebuild_mapping(container) -> Dict[str, str]:
    """Recompute the joint mapping of a retarget network after changing its files.

    Used by the retarget HDA's "Update Mapping" button and handy after
    swapping the source/target FBX by hand.
    """
    src = container.node("source")
    tgt = container.node("target")
    assign = container.node("assign_map")
    if src is None or tgt is None or assign is None:
        raise compat.StudioError(f"{container.path()} is not an ApexKinefxStudio retarget network")
    src_names = joint_names(src, 1)
    tgt_names = joint_names(tgt, 1)
    mapping = profiles.auto_map(src_names, tgt_names)
    assign.parm("snippet").set(mapping_to_vex(mapping))
    rt = container.node("world_delta_retarget")
    hips = find_hips(tgt_names)
    if rt is not None and hips:
        compat.set_parm(rt, "hips_joint", hips)
    lock = container.node("foot_lock")
    feet = find_feet(tgt_names)
    if lock is not None and feet:
        compat.set_parm(lock, "feet", " ".join(feet))
    LOG.info("Mapping rebuilt: %d joints (missing core: %s)", len(mapping),
             ", ".join(profiles.missing_core(mapping, tgt_names)) or "none")
    return mapping


def _node_of(out: Tuple[object, int]):
    return out[0]


def _native_branch(geo, assign, src_rest, src_anim, custom):
    """SideFX workflow for comparison: Rig Match Pose -> Map Points -> Full Body IK."""
    match = compat.create(geo, "rig_match_pose", "native_rigmatchpose", required=False)
    mapp = compat.create(geo, "map_points", "native_mappoints", required=False)
    fbik = compat.create(geo, "full_body_ik", "native_fullbodyik", required=False)
    if not (match and mapp and fbik):
        LOG.info("Native KineFX retarget nodes not all available; skipping native branch.")
        for n in (match, mapp, fbik):
            if n is not None:
                n.destroy()
        return None
    _wire(match, 0, src_rest)
    match.setInput(1, assign)
    mapp.setInput(0, match)
    mapp.setInput(1, assign)
    fbik.setInput(0, assign)
    _wire(fbik, 1, src_anim)
    fbik.setInput(2, mapp)
    switch = compat.create(geo, "switch", "retarget_method")
    switch.setInput(0, custom)
    switch.setInput(1, fbik)
    network.note(geo, "Switch input 0 = ApexKinefxStudio world-delta retarget (default).\n"
                      "Input 1 = SideFX Rig Match Pose / Map Points / Full Body IK.\n"
                      "The native branch usually needs its mapping and IK targets\n"
                      "configured in the Map Points and Full Body IK parameters.", near=switch)
    return switch


def add_foot_lock(geo, anim, feet: Sequence[str], ground_height: float = 0.0):
    """SOP Solver that pins feet while in contact (two-bone IK on the legs)."""
    if not feet:
        LOG.warning("No feet found for foot lock; skipping.")
        return anim
    return network.make_solver(geo, "foot_lock", "foot_lock_step", inputs=[anim], run_over="detail",
                               parms=[
                                   ParmSpec("feet", "Feet", "string", " ".join(feet)),
                                   ParmSpec("height_threshold", "Contact Height", "float", 0.08, 0, 0.5),
                                   ParmSpec("speed_threshold", "Contact Speed", "float", 0.35, 0, 2),
                                   ParmSpec("ground_height", "Ground Height", "float", ground_height, -5, 5),
                                   ParmSpec("blend_time", "Blend Time (s)", "float", 0.12, 0, 1),
                               ])


def apex_retarget(anim_skeleton, apex_character_node, name: str = "apex_animation_from_skeleton"):
    """Retarget an animated skeleton onto an existing APEX character (H21+)."""
    parent = anim_skeleton.parent()
    node = compat.create(parent, "apex_animation_from_skeleton", name, required=False)
    if node is None:
        LOG.warning("APEX Animation from Skeleton is not available in this Houdini build.")
        return None
    compat.connect_by_label(node, apex_character_node, ["character", "scene", "rig"], fallback_index=0)
    compat.connect_by_label(node, anim_skeleton, ["skeleton", "animation", "anim"], fallback_index=1)
    return node


def try_biped_recipe(parent) -> bool:
    """Best effort: drop Houdini 22's biped retarget recipe if the recipe API exists.

    Recipes are a Houdini 20+ feature; the Python entry points are discovered at
    runtime rather than assumed. Returns True when a recipe was applied.
    """
    h = require_hou()
    data = getattr(h, "data", None)
    if data is None:
        return False
    names: List[str] = []
    for lister in ("tabToolRecipeNames", "recipeNames"):
        fn = getattr(data, lister, None)
        if callable(fn):
            try:
                names = list(fn())
                break
            except Exception:  # API shape differs between builds
                continue
    biped = [n for n in names if "biped" in n.lower() and "retarget" in n.lower()] or \
            [n for n in names if "biped" in n.lower()]
    applier = getattr(data, "applyTabToolRecipe", None)
    if not biped or not callable(applier):
        LOG.info("No biped recipe found through hou.data (found %d recipes).", len(names))
        return False
    try:
        applier(biped[0], parent)
        LOG.info("Applied recipe %s", biped[0])
        return True
    except Exception as exc:
        LOG.warning("Applying recipe %s failed: %s", biped[0], exc)
        return False


def batch_retarget(source_folder: str, target, out_dir: str, name: str = "aks_batch_retarget",
                   options: Optional[RetargetOptions] = None, frame_range: Optional[Tuple[int, int]] = None) -> List[str]:
    """Retarget every FBX in ``source_folder``; writes animated skeleton caches.

    Output per clip: ``<out_dir>/<clip>/<clip>.$F4.bgeo.sc``. Returns clip names.
    """
    h = require_hou()
    files = sorted(glob.glob(os.path.join(source_folder, "*.fbx")))
    if not files:
        LOG.warning("No FBX files in %s", source_folder)
        return []
    geo = build_retarget(files[0], target, name, options)
    src = geo.node("source")
    out = geo.node("OUT_ANIM_SKELETON")
    start, end = frame_range or (int(h.playbar.frameRange()[0]), int(h.playbar.frameRange()[1]))
    clips = []
    for path in files:
        clip = os.path.splitext(os.path.basename(path))[0]
        compat.set_parm(src, ("fbxfile", "file", "filename"), path)
        clip_dir = os.path.join(out_dir, clip)
        os.makedirs(clip_dir, exist_ok=True)
        for f in range(start, end + 1):
            h.setFrame(f)
            out.geometry().saveToFile(os.path.join(clip_dir, f"{clip}.{f:04d}.bgeo.sc"))
        clips.append(clip)
        LOG.info("Retargeted %s (%d frames)", clip, end - start + 1)
    return clips
