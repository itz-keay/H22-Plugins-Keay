"""Humanoid autorig: guide skeleton -> KineFX rig -> APEX character.

:func:`build_biped` creates, inside ``/obj/<name>``:

1. a canonical biped guide skeleton scaled/centred to the mesh bounding box
   (canonical joint names, so Mixamo/Cascadeur/UE retargets map 1:1);
2. a Rig Doctor pass (when available) for validation;
3. skinning (biharmonic by default, proximity fallback);
4. an APEX character (Pack Folder + Autorig FK component), best effort;
5. optionally animation: a Mixamo/Cascadeur FBX retargeted onto the new rig
   with :mod:`apex_studio.retarget`.

In Houdini 22 you can also use SideFX's biped template/recipe (automatic
skeleton mapping and rig transfer). :func:`build_biped` stays useful when you
need a code-driven, repeatable setup, a skeleton with canonical names, or a
starting point on Houdini 20.5/21.
"""

from __future__ import annotations

from typing import Optional, Sequence

from .. import compat, network, retarget
from ..compat import LOG, require_hou
from ..core import guides
from . import common


def guides_for_mesh(mesh_node, fingers: bool = False, height: Optional[float] = None):
    """Biped guides fitted to the mesh bounding box (height + centre)."""
    h = height
    cx = cz = 0.0
    y0 = 0.0
    if mesh_node is not None:
        geo = mesh_node.geometry()
        if geo is not None and len(geo.points()) > 0:
            bb = geo.boundingBox()
            h = h or bb.sizevec()[1]
            c = bb.center()
            cx, cz, y0 = c[0], c[2], bb.minvec()[1]
    joints = guides.biped(height=h or 1.8, fingers=fingers)
    for j in joints:
        j.pos = (j.pos[0] + cx, j.pos[1] + y0, j.pos[2] + cz)
    return joints


def build_biped(mesh=None, name: str = "aks_biped", fingers: bool = False,
                capture_method: str = "biharmonic", apex: bool = True,
                animation_fbx: Optional[str] = None, height: Optional[float] = None):
    """Build a biped rig. ``mesh``: SOP node, node path, file path or None."""
    require_hou()
    geo = network.obj_container(name, clear=True)
    mesh_in = network.input_or_placeholder(geo, "mesh_in", mesh) if mesh is not None else None
    joints = guides_for_mesh(mesh_in, fingers=fingers, height=height)
    skel = common.skeleton_sop(geo, "guides", joints, template="biped")

    doctor = compat.create(geo, "rig_doctor", "rig_doctor", required=False)
    rest = skel
    if doctor is not None:
        doctor.setInput(0, skel)
        rest = doctor
    rest = network.null(geo, "REST_SKELETON", rest)

    anim = rest
    if animation_fbx:
        # animate by retargeting onto our canonical skeleton: map is exact
        mapping_src = retarget.import_character(geo, "anim_source", animation_fbx)
        anim = _retarget_into(geo, rest, mapping_src)

    mesh_out = None
    if mesh_in is not None:
        mesh_out = common.skin(geo, mesh_in, rest, anim, method=capture_method).deformed
        if apex:
            common.apex_character(geo, mesh_in, rest)

    outs = common.outputs(geo, rest, anim, mesh_out)
    network.note(geo, "Biped guides are placed from the mesh bounding box.\n"
                      "Adjust joints with a Skeleton SOP or Rig Pose after 'guides' if needed,\n"
                      "then re-run capture. Joint names are canonical (hips, l_thigh...).",
                 near=skel)
    network.finalize(geo, outs.get("mesh", outs["anim"]))
    return geo


def _retarget_into(geo, rest_null, source):
    """Wire the world-delta retarget from an imported source into ``rest_null``."""
    src_node, _, src_rest, src_anim = source
    tgt_names = [j.name for j in guides.biped(fingers=True)]
    src_names = retarget.joint_names(src_rest[0], src_rest[1])
    mapping = retarget.auto_map(src_names, tgt_names, target_profile="houdini")
    assign = network.wrangle(geo, "assign_map", retarget.mapping_to_vex(mapping), "points",
                             inputs=[rest_null], from_file=False)
    pose = network.wrangle(geo, "pose_match", "retarget_pose_match", "detail")
    pose.setInput(0, src_rest[0], src_rest[1])
    pose.setInput(1, assign)
    rt = network.wrangle(geo, "world_delta_retarget", "retarget_world_delta", "detail", parms=[
        network.ParmSpec("hips_joint", "Hips Joint", "string", "hips"),
        network.ParmSpec("root_motion", "Root Motion", "menu", "keep",
                         menu=[("keep", "Keep"), ("in_place", "In Place"), ("none", "None")]),
        network.ParmSpec("auto_scale", "Auto Scale", "toggle", True),
        network.ParmSpec("translation_scale", "Translation Scale", "float", 1.0, 0, 2),
    ])
    rt.setInput(0, assign)
    rt.setInput(1, src_anim[0], src_anim[1])
    rt.setInput(2, pose)
    return retarget.add_foot_lock(geo, rt, ["l_foot", "r_foot"])
