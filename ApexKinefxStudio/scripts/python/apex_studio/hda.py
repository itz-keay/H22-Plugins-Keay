"""Turn the Python-built networks into digital assets (HDAs).

The source of truth is the Python/VEX in this package; HDAs are generated
artifacts (``tools/build_hdas.py`` runs this under hython and writes
``otls/apex_kinefx_studio.hda``). Regenerate them after changing the code
instead of editing the HDAs by hand.

Conversion steps for a built OBJ container:

1. :func:`expose_inputs` replaces placeholder input Nulls (``path_in``,
   ``ground_in``, ``mesh_in``, ``model_in``, ``agent_in``...) with Object
   Merges driven by string parameters on the container.
2. :func:`promote_parms` copies the spare parameters of the key internal
   nodes (motion wrangles, solvers) onto the container, one folder per node,
   and channel-references the internal parameters to them.
3. :func:`make_asset` calls ``createDigitalAsset`` (spare parameters move
   into the definition) and saves it.
"""

from __future__ import annotations

import os
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from . import compat, network
from .compat import LOG, require_hou

PLACEHOLDERS = {
    "path_in": ("path_object", "Path Curve"),
    "ground_in": ("ground_object", "Ground (Heightfield / Mesh)"),
    "mesh_in": ("mesh_object", "Mesh"),
    "model_in": ("model_object", "Vehicle Model"),
    "agent_in": ("agent_object", "Agent"),
    "character_in": ("character_object", "Character"),
    "target_mesh": ("target_mesh_object", "Target Mesh"),
}

_SKIP_TEMPLATE_TYPES = ("Folder", "FolderSet", "Separator", "Label")


def expose_inputs(container) -> List[str]:
    """Replace placeholder Nulls with parameter-driven Object Merges."""
    h = require_hou()
    added = []
    specs = []
    for node_name, (parm_name, label) in PLACEHOLDERS.items():
        node = container.node(node_name)
        if node is None or node.type().name() != "null" or node.inputs():
            continue
        specs.append(network.ParmSpec(parm_name, label, "path", "", folder="Inputs"))
        added.append((node, parm_name))
    if not specs:
        return []
    network.add_spare_parms(container, specs, folder="Inputs")
    names = []
    for node, parm_name in added:
        outputs = [(c, c.inputs().index(node)) for c in node.outputs()]
        pos = node.position()
        name = node.name()
        node.destroy()
        merge = compat.create(container, "object_merge", name)
        merge.setPosition(pos)
        merge.parm("objpath1").setExpression(f'chsop("../{parm_name}")', h.exprLanguage.Hscript)
        compat.set_parm(merge, "xformtype", 1)
        for consumer, idx in outputs:
            consumer.setInput(idx, merge)
        names.append(parm_name)
    return names


def promote_parms(container, node_names: Sequence[str]) -> int:
    """Promote spare parms of internal nodes to the container (linked by ch())."""
    h = require_hou()
    ptg = container.parmTemplateGroup()
    count = 0
    links: List[Tuple[object, str, str]] = []
    for node_name in node_names:
        node = container.node(node_name)
        if node is None:
            continue
        spare = [t for t in _flatten(node.spareParms())]
        if not spare:
            continue
        templates = []
        for parm_name in spare:
            tmpl = node.parmTuple(parm_name).parmTemplate().clone()
            new_name = f"{node_name}_{parm_name}"
            tmpl.setName(new_name)
            templates.append(tmpl)
            links.append((node, parm_name, new_name))
            count += 1
        ptg.append(h.FolderParmTemplate(f"{node_name}_folder", node_name.replace("_", " ").title(),
                                        parm_templates=templates))
    container.setParmTemplateGroup(ptg)
    for node, parm_name, new_name in links:
        tup = node.parmTuple(parm_name)
        src_tup = container.parmTuple(new_name)
        if tup is None or src_tup is None:
            continue
        # copy current values up, then reference them down
        try:
            src_tup.set(tup.eval())
        except Exception:
            pass
        rel = node.relativePathTo(container)
        is_string = tup.parmTemplate().type() == h.parmTemplateType.String
        for comp, src in zip(tup, src_tup):
            fn = "chs" if is_string else "ch"
            comp.setExpression(f'{fn}("{rel}/{src.name()}")', h.exprLanguage.Hscript)
    return count


def _flatten(parms) -> List[str]:
    """Unique parm tuple names of a node's spare parms (skipping folders)."""
    out: List[str] = []
    for p in parms:
        tup = p.tuple()
        tmpl = tup.parmTemplate()
        if tmpl.type().name() in _SKIP_TEMPLATE_TYPES:
            continue
        if tup.name() not in out:
            out.append(tup.name())
    return out


def make_asset(container, type_name: str, label: str, hda_path: str, version: str = "1.0",
               help_text: str = ""):
    """Convert an OBJ container to an HDA and save it into ``hda_path``."""
    h = require_hou()
    os.makedirs(os.path.dirname(hda_path) or ".", exist_ok=True)
    full_name = f"aks::{type_name}::{version}"
    asset = container.createDigitalAsset(name=full_name, hda_file_name=hda_path, description=label,
                                         min_num_inputs=0, max_num_inputs=0)
    definition = asset.type().definition()
    if help_text:
        definition.addSection("HelpText", help_text)
    definition.setExtraInfo("apex_kinefx_studio=1")
    definition.updateFromNode(asset)
    definition.save(hda_path, asset)
    LOG.info("Saved %s -> %s", full_name, hda_path)
    return asset


def convert(container, type_name: str, label: str, hda_path: str, promote: Sequence[str],
            help_text: str = "", version: str = "1.0"):
    """expose_inputs + promote_parms + make_asset."""
    expose_inputs(container)
    promote_parms(container, promote)
    return make_asset(container, type_name, label, hda_path, version, help_text)
