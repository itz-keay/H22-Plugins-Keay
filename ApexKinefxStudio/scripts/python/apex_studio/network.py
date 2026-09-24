"""Network-building helpers shared by every module.

These wrap the boilerplate of building SOP networks from Python: containers,
wrangles loaded from ``vex/snippets``, spare parameters, sticky notes, layout.

VEX lives in plain ``.vfl`` / ``.h`` files so it can be diffed and reviewed.
:func:`load_vex` inlines ``#include "aks_*.h"`` headers at build time, so the
networks it builds keep working after the package is uninstalled.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from . import compat
from .compat import LOG, require_hou

PACKAGE_ROOT = os.environ.get("APEX_KINEFX_STUDIO") or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
VEX_ROOT = os.path.join(PACKAGE_ROOT, "vex")
_INCLUDE_RE = re.compile(r'^\s*#include\s+[<"](aks_[\w]+\.h)[>"]\s*$', re.M)

#: Wrangle "Run Over" tokens.
RUN_OVER = {"detail": 0, "primitives": 1, "points": 2, "vertices": 3, "numbers": 4}


# ---------------------------------------------------------------------------
# VEX loading
# ---------------------------------------------------------------------------

def load_vex(name: str, inline_includes: bool = True, _seen: Optional[set] = None) -> str:
    """Return the text of ``vex/snippets/<name>.vfl`` (or a header in ``vex/include``).

    ``aks_*.h`` headers are inlined recursively and only once each.
    """
    _seen = set() if _seen is None else _seen
    if name.endswith(".h"):
        path = os.path.join(VEX_ROOT, "include", name)
    else:
        path = os.path.join(VEX_ROOT, "snippets", name if name.endswith(".vfl") else name + ".vfl")
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    if not inline_includes:
        return text

    def _sub(match: "re.Match") -> str:
        header = match.group(1)
        if header in _seen:
            return f"// {header} already inlined"
        _seen.add(header)
        return f"// ---- begin {header} ----\n{load_vex(header, True, _seen)}\n// ---- end {header} ----"

    return _INCLUDE_RE.sub(_sub, text)


# ---------------------------------------------------------------------------
# Spare parameters
# ---------------------------------------------------------------------------

@dataclass
class ParmSpec:
    """Declarative spare parameter.

    kind: float | int | toggle | string | vector | menu | ramp | button
    """

    name: str
    label: str
    kind: str = "float"
    default: object = 0.0
    min: float = 0.0
    max: float = 1.0
    menu: Sequence[Tuple[str, str]] = ()
    help: str = ""
    folder: Optional[str] = None
    expression: Optional[str] = None


def _template(spec: ParmSpec):
    h = require_hou()
    if spec.kind == "float":
        t = h.FloatParmTemplate(spec.name, spec.label, 1, default_value=(float(spec.default),),
                                min=spec.min, max=spec.max)
    elif spec.kind == "int":
        t = h.IntParmTemplate(spec.name, spec.label, 1, default_value=(int(spec.default),),
                              min=int(spec.min), max=int(spec.max))
    elif spec.kind == "toggle":
        t = h.ToggleParmTemplate(spec.name, spec.label, default_value=bool(spec.default))
    elif spec.kind == "string":
        t = h.StringParmTemplate(spec.name, spec.label, 1, default_value=(str(spec.default),))
    elif spec.kind == "path":
        t = h.StringParmTemplate(spec.name, spec.label, 1, default_value=(str(spec.default),),
                                 string_type=h.stringParmType.NodeReference)
    elif spec.kind == "vector":
        d = tuple(float(v) for v in spec.default)  # type: ignore[arg-type]
        t = h.FloatParmTemplate(spec.name, spec.label, 3, default_value=d,
                                min=spec.min, max=spec.max)
    elif spec.kind == "menu":
        tokens = [m[0] for m in spec.menu]
        labels = [m[1] for m in spec.menu]
        default_idx = tokens.index(spec.default) if spec.default in tokens else 0
        t = h.MenuParmTemplate(spec.name, spec.label, tokens, labels, default_value=default_idx)
    elif spec.kind == "ramp":
        t = h.RampParmTemplate(spec.name, spec.label, h.rampParmType.Float,
                               default_value=2)
    elif spec.kind == "separator":
        t = h.SeparatorParmTemplate(spec.name)
    else:
        raise ValueError(f"Unknown ParmSpec kind {spec.kind}")
    if spec.help and hasattr(t, "setHelp"):
        t.setHelp(spec.help)
    return t


def add_spare_parms(node, specs: Sequence[ParmSpec], folder: Optional[str] = "Controls") -> None:
    """Append spare parameters (optionally in a folder) to ``node``."""
    h = require_hou()
    ptg = node.parmTemplateGroup()
    folders: Dict[str, List] = {}
    loose: List = []
    for spec in specs:
        target_folder = spec.folder or folder
        tmpl = _template(spec)
        if target_folder:
            folders.setdefault(target_folder, []).append(tmpl)
        else:
            loose.append(tmpl)
    for tmpl in loose:
        ptg.append(tmpl)
    for fname, tmpls in folders.items():
        ptg.append(h.FolderParmTemplate(fname.lower().replace(" ", "_") + "_fld", fname,
                                        parm_templates=tmpls))
    node.setParmTemplateGroup(ptg)
    for spec in specs:
        if spec.expression and node.parm(spec.name) is not None:
            node.parm(spec.name).setExpression(spec.expression)


def link_parms(src_node, dst_node, names: Iterable[str]) -> None:
    """Channel-reference ``dst.name`` to ``src.name`` for each name (tuples too)."""
    for name in names:
        tup = dst_node.parmTuple(name)
        if tup is None:
            continue
        for comp in tup:
            src = src_node.parm(comp.name())
            if src is None:
                continue
            rel = dst_node.relativePathTo(src_node)
            fn = "chs" if comp.parmTemplate().type().name() == "String" else "ch"
            comp.setExpression(f'{fn}("{rel}/{comp.name()}")')


# ---------------------------------------------------------------------------
# Node creation helpers
# ---------------------------------------------------------------------------

def obj_container(name: str, parent_path: str = "/obj", clear: bool = False):
    """Get or create a Geometry OBJ, optionally clearing its contents."""
    h = require_hou()
    parent = h.node(parent_path)
    existing = parent.node(name)
    if existing is not None:
        if clear:
            for child in existing.children():
                child.destroy()
        return existing
    geo = parent.createNode("geo", name)
    for child in geo.children():  # older builds create a default file SOP
        child.destroy()
    return geo


def wrangle(parent, name: str, vex: str, run_over: str = "points",
            inputs: Sequence = (), parms: Sequence[ParmSpec] = (),
            from_file: bool = True, folder: Optional[str] = "Controls"):
    """Create an Attribute Wrangle.

    ``vex`` is a snippet name in ``vex/snippets`` when ``from_file`` else raw code.
    """
    node = compat.create(parent, "attribwrangle", name)
    code = load_vex(vex) if from_file else vex
    node.parm("snippet").set(code)
    compat.set_parm(node, "class", RUN_OVER[run_over])
    for idx, src in enumerate(inputs):
        if src is not None:
            node.setInput(idx, src)
    if parms:
        add_spare_parms(node, parms, folder=folder)
    return node


def python_sop(parent, name: str, code: str, inputs: Sequence = ()):
    node = compat.create(parent, "python", name)
    node.parm("python").set(code)
    for idx, src in enumerate(inputs):
        if src is not None:
            node.setInput(idx, src)
    return node


def null(parent, name: str, input_node=None, color: Optional[Tuple[float, float, float]] = None):
    h = require_hou()
    node = compat.create(parent, "null", name)
    if input_node is not None:
        node.setInput(0, input_node)
    if color:
        node.setColor(h.Color(color))
    return node


def object_merge(parent, name: str, path: str, xform_to_this: bool = True):
    node = compat.create(parent, "object_merge", name)
    compat.set_parm(node, "objpath1", path)
    compat.set_parm(node, "xformtype", 1 if xform_to_this else 0)
    return node


def file_sop(parent, name: str, path: str):
    node = compat.create(parent, "file", name)
    compat.set_parm(node, "file", path)
    return node


def input_or_placeholder(parent, name: str, source) -> object:
    """Accept a node, node path, file path, or None and return a SOP to wire from.

    * hou.Node -> object merge of it (if outside ``parent``) or the node itself
    * ``/obj/...`` string -> object merge
    * file path string -> File SOP
    * None -> an empty Null the user can wire into later
    """
    h = require_hou()
    if source is None:
        return null(parent, name, color=(0.9, 0.3, 0.3))
    if isinstance(source, h.Node):
        if source.parent() == parent:
            return source
        return object_merge(parent, name, source.path())
    if isinstance(source, str) and source.startswith("/"):
        if h.node(source) is not None:
            return object_merge(parent, name, source)
    return file_sop(parent, name, str(source))


def note(parent, text: str, near=None, size: Tuple[float, float] = (5.0, 2.0),
         color: Tuple[float, float, float] = (1.0, 0.95, 0.6)):
    """Drop a sticky note, optionally next to ``near``."""
    h = require_hou()
    sticky = parent.createStickyNote()
    sticky.setText(text)
    sticky.setSize(h.Vector2(*size))
    sticky.setColor(h.Color(color))
    if near is not None:
        pos = near.position()
        sticky.setPosition(h.Vector2(pos[0] + 2.5, pos[1] - 0.5))
    return sticky


def chain(nodes: Sequence) -> None:
    """Wire nodes in sequence (input 0 <- previous)."""
    prev = None
    for node in nodes:
        if node is None:
            continue
        if prev is not None:
            node.setInput(0, prev)
        prev = node


def finalize(parent, display_node, layout: bool = True) -> None:
    """Set display/render flags and lay the network out."""
    display_node.setDisplayFlag(True)
    display_node.setRenderFlag(True)
    if layout:
        parent.layoutChildren()


def solver_inner(solver_node):
    """Return the SOP network inside a SOP Solver and its Prev_Frame node.

    The internal path has been ``d/s`` for many releases; we search instead of
    hard-coding it.
    """
    for child in solver_node.allSubChildren():
        if child.name() == "Prev_Frame":
            return child.parent(), child
    raise compat.StudioError(f"Could not find Prev_Frame inside {solver_node.path()}")


def solver_input(inner, index: int):
    """Return the Input_N node inside a SOP solver network (1-based like Houdini)."""
    node = inner.node(f"Input_{index}")
    if node is None:
        raise compat.StudioError(f"No Input_{index} inside {inner.path()}")
    return node


def make_solver(parent, name: str, snippet: str, inputs: Sequence = (),
                parms: Sequence[ParmSpec] = (), run_over: str = "points",
                start_frame_expr: str = "$FSTART"):
    """Build a SOP Solver whose step is a single wrangle.

    Inside the wrangle, input 0 = previous frame state (initialised from the
    solver's first input at the start frame) and wrangle inputs 1..3 are the
    solver's inputs 0..2 at the *current* time (Input_1..Input_3). Spare parms
    live on the solver node and are channel-linked into the wrangle, so users
    tweak them outside.
    """
    solver = compat.create(parent, "solver", name)
    for idx, src in enumerate(inputs):
        if src is not None:
            solver.setInput(idx, src)
    compat.set_parm(solver, "startframe", 1, warn=False)
    compat.set_expression(solver, "startframe", start_frame_expr)
    inner, prev = solver_inner(solver)
    step = wrangle(inner, "step", snippet, run_over=run_over, parms=parms)
    step.setInput(0, prev)
    for i in range(1, min(len(inputs), 3) + 1):
        try:
            step.setInput(i, solver_input(inner, i))
        except compat.StudioError:
            LOG.warning("Solver %s: no Input_%d node; wire it manually", solver.path(), i)
    out = null(inner, "OUT_STEP", step)
    out.setDisplayFlag(True)
    out.setRenderFlag(True)
    inner.layoutChildren()
    if parms:
        add_spare_parms(solver, parms, folder="Solver Controls")
        for spec in parms:
            if spec.kind in ("separator", "ramp"):
                continue
            tup = step.parmTuple(spec.name)
            if tup is None:
                continue
            for comp in tup:
                rel = step.relativePathTo(solver)
                fn = "chs" if spec.kind in ("string", "path") else "ch"
                comp.setExpression(f'{fn}("{rel}/{comp.name()}")')
    return solver
