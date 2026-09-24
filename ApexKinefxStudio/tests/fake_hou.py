"""A permissive stand-in for Houdini's ``hou`` module, for smoke tests only.

It records the node graph the builders create (types, names, wiring, parm
values and expressions) so tests can run every builder end to end outside
Houdini and catch Python errors: wrong helper signatures, typos, missing
imports, bad wiring logic. It does NOT validate native node types' real
parameter names or cook anything; that still needs a real Houdini session
(see tools/probe_node_types.py and examples/build_demo_scene.py).
"""

from __future__ import annotations

import enum
import types
from typing import Dict, List, Optional


class Error(Exception):
    pass


class OperationFailed(Error):
    pass


# --- enums ---------------------------------------------------------------------

class _Enum:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name

    def __repr__(self):
        return f"<{self._name}>"


class parmTemplateType:
    Int = _Enum("Int")
    Float = _Enum("Float")
    String = _Enum("String")
    Toggle = _Enum("Toggle")
    Menu = _Enum("Menu")
    Button = _Enum("Button")
    Folder = _Enum("Folder")
    FolderSet = _Enum("FolderSet")
    Separator = _Enum("Separator")
    Label = _Enum("Label")
    Ramp = _Enum("Ramp")


class exprLanguage:
    Hscript = "hscript"
    Python = "python"


class scriptLanguage:
    Python = "python"
    Hscript = "hscript"


class stringParmType:
    Regular = "regular"
    NodeReference = "noderef"
    FileReference = "file"


class rampParmType:
    Float = "float"
    Color = "color"


class attribType:
    Point = "point"
    Prim = "prim"
    Global = "global"
    Vertex = "vertex"


class attribData:
    Int = "int"
    Float = "float"
    String = "string"


# --- small value types --------------------------------------------------------------

class Color:
    def __init__(self, rgb):
        self.rgb = tuple(rgb)


class Vector2(tuple):
    def __new__(cls, x=0.0, y=0.0):
        return super().__new__(cls, (x, y))


# --- parm templates -----------------------------------------------------------------

class ParmTemplate:
    _type = parmTemplateType.Float

    def __init__(self, name, label="", num_components=1, default_value=(), **kwargs):
        self._name = name
        self._label = label
        self._n = num_components
        self._default = default_value
        self._kwargs = kwargs
        self._help = ""
        self._callback = ""

    def name(self):
        return self._name

    def setName(self, name):
        self._name = name

    def label(self):
        return self._label

    def numComponents(self):
        return self._n

    def type(self):
        return self._type

    def setHelp(self, text):
        self._help = text

    def clone(self):
        c = type(self).__new__(type(self))
        c.__dict__.update(self.__dict__)
        return c

    def menuItems(self):
        return tuple(self._kwargs.get("menu_items", ()))

    def setScriptCallback(self, s):
        self._callback = s

    def setScriptCallbackLanguage(self, lang):
        pass


class FloatParmTemplate(ParmTemplate):
    _type = parmTemplateType.Float


class IntParmTemplate(ParmTemplate):
    _type = parmTemplateType.Int


class StringParmTemplate(ParmTemplate):
    _type = parmTemplateType.String


class ToggleParmTemplate(ParmTemplate):
    _type = parmTemplateType.Toggle

    def __init__(self, name, label, default_value=False, **kw):
        super().__init__(name, label, 1, (default_value,), **kw)


class MenuParmTemplate(ParmTemplate):
    _type = parmTemplateType.Menu

    def __init__(self, name, label, menu_items, menu_labels=(), default_value=0, **kw):
        super().__init__(name, label, 1, (default_value,), menu_items=menu_items, **kw)


class RampParmTemplate(ParmTemplate):
    _type = parmTemplateType.Ramp

    def __init__(self, name, label, ramp_type, default_value=2, **kw):
        super().__init__(name, label, 1, (default_value,), **kw)


class SeparatorParmTemplate(ParmTemplate):
    _type = parmTemplateType.Separator

    def __init__(self, name, **kw):
        super().__init__(name, "", 1, ())


class ButtonParmTemplate(ParmTemplate):
    _type = parmTemplateType.Button

    def __init__(self, name, label, **kw):
        super().__init__(name, label, 1, ())


class FolderParmTemplate(ParmTemplate):
    _type = parmTemplateType.Folder

    def __init__(self, name, label, parm_templates=(), **kw):
        super().__init__(name, label, 1, ())
        self.children = list(parm_templates)


class ParmTemplateGroup:
    def __init__(self, templates=()):
        self.templates = list(templates)

    def append(self, t):
        self.templates.append(t)

    def flat(self):
        out = []
        for t in self.templates:
            if isinstance(t, FolderParmTemplate):
                out.extend(ParmTemplateGroup(t.children).flat())
            else:
                out.append(t)
        return out


# --- parms ----------------------------------------------------------------------

class Parm:
    def __init__(self, node, name, template=None, tup=None):
        self.node = node
        self._name = name
        self._template = template or FloatParmTemplate(name, name)
        self.value = None
        self.expression = None
        self._tuple = tup

    def name(self):
        return self._name

    def set(self, value):
        self.value = value

    def eval(self):
        return self.value

    def setExpression(self, expr, language=None):
        self.expression = expr

    def parmTemplate(self):
        return self._template

    def menuItems(self):
        return self._template.menuItems()

    def menuLabels(self):
        return self._template.menuItems()

    def tuple(self):
        return self._tuple or ParmTuple(self.node, self._name, [self], self._template)


class ParmTuple(list):
    def __init__(self, node, name, parms, template):
        super().__init__(parms)
        self._name = name
        self._template = template

    def name(self):
        return self._name

    def set(self, values):
        for p, v in zip(self, values):
            p.set(v)

    def eval(self):
        return [p.eval() for p in self]

    def parmTemplate(self):
        return self._template


# --- nodes -----------------------------------------------------------------------

class NodeType:
    def __init__(self, name, category):
        self._name = name
        self._category = category
        self._definition = HDADefinition()

    def name(self):
        return self._name

    def category(self):
        return self._category

    def definition(self):
        return self._definition


class HDADefinition:
    def addSection(self, *a):
        pass

    def setExtraInfo(self, *a):
        pass

    def updateFromNode(self, *a):
        pass

    def save(self, *a):
        pass


class Category:
    def __init__(self, name, types_):
        self._name = name
        self._types = {t: NodeType(t, self) for t in types_}

    def name(self):
        return self._name

    def nodeTypes(self):
        return self._types


class StickyNote:
    def setText(self, t):
        self.text = t

    def setSize(self, s):
        pass

    def setColor(self, c):
        pass

    def setPosition(self, p):
        pass


class _Attrib:
    pass


class Geometry:
    def __init__(self, names=()):
        self._names = list(names)

    def points(self):
        return []

    def prims(self):
        return []

    def findPointAttrib(self, name):
        return _Attrib() if (name == "name" and self._names) else None

    def findPrimAttrib(self, name):
        return None

    def pointStringAttribValues(self, name):
        return list(self._names)

    def pointFloatAttribValues(self, name):
        return []


class Node:
    def __init__(self, parent, type_name, name, category):
        self._parent = parent
        self._type = NodeType(type_name, category)
        self._name = name
        self._children: Dict[str, "Node"] = {}
        self._inputs: Dict[int, "Node"] = {}
        self._parms: Dict[str, Parm] = {}
        self._ptg = ParmTemplateGroup()
        self._pos = Vector2(0, 0)
        self.display = False
        self.notes: List[StickyNote] = []
        if type_name == "solver":
            d = self._add_child("dopnet", "d", DOP)
            s = d._add_child("sopnet", "s", SOP)
            for n in ("Prev_Frame", "Input_1", "Input_2", "Input_3", "Input_4"):
                s._add_child("object_merge", n, SOP)
        if type_name in ("attribwrangle",):
            self.parm("snippet")

    # hierarchy -------------------------------------------------------------
    def _add_child(self, type_name, name, category):
        base = name
        i = 1
        while name in self._children:
            i += 1
            name = f"{base}{i}"
        node = Node(self, type_name, name, category)
        self._children[name] = node
        return node

    def createNode(self, type_name, name=None):
        cat = SOP if self._type.name() in ("geo", "sopnet", "subnet") else (
            DOP if self._type.name() == "dopnet" else SOP)
        if self._type.name() == "obj_root":
            cat = OBJ
        if type_name not in cat.nodeTypes():
            raise OperationFailed(f"Invalid node type name {type_name} in {cat.name()}")
        default = type_name.split("::")[1] if type_name.count("::") >= 1 and not type_name.split("::")[1][:1].isdigit() else type_name.split("::")[0]
        return self._add_child(type_name, name or default, cat)

    def children(self):
        return list(self._children.values())

    def allSubChildren(self):
        out = []
        for c in self._children.values():
            out.append(c)
            out.extend(c.allSubChildren())
        return out

    def node(self, path):
        cur = self
        for part in path.split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                cur = cur._parent
                continue
            cur = cur._children.get(part)
            if cur is None:
                return None
        return cur

    def parent(self):
        return self._parent

    def destroy(self):
        if self._parent is not None:
            self._parent._children.pop(self._name, None)
            for sib in self._parent._children.values():
                for k, v in list(sib._inputs.items()):
                    if v is self:
                        del sib._inputs[k]

    def path(self):
        if self._parent is None:
            return ""
        return f"{self._parent.path()}/{self._name}"

    def name(self):
        return self._name

    def type(self):
        return self._type

    def relativePathTo(self, other):
        return "../" * (self.path().count("/")) + other.path().lstrip("/")

    # wiring -------------------------------------------------------------------
    def setInput(self, index, node, output_index=0):
        if node is not None and not isinstance(node, Node):
            raise TypeError(f"setInput expects a node, got {node!r}")
        self._inputs[index] = node

    def inputs(self):
        if not self._inputs:
            return ()
        return tuple(self._inputs.get(i) for i in range(max(self._inputs) + 1))

    def outputs(self):
        return [n for n in self._parent._children.values() if self in n._inputs.values()]

    def inputLabels(self):
        return tuple(f"Input {i + 1}" for i in range(4))

    # parms -----------------------------------------------------------------------
    def parm(self, name):
        if name not in self._parms:
            tmpl = next((t for t in self._ptg.flat() if t.name() == name), None)
            self._parms[name] = Parm(self, name, tmpl)
        return self._parms[name]

    def parmTuple(self, name):
        tmpl = next((t for t in self._ptg.flat() if t.name() == name), None)
        if tmpl is not None and tmpl.numComponents() > 1:
            comps = [self.parm(f"{name}{s}") for s in "xyzw"[: tmpl.numComponents()]]
            return ParmTuple(self, name, comps, tmpl)
        return ParmTuple(self, name, [self.parm(name)], tmpl or FloatParmTemplate(name, name))

    def parmTemplateGroup(self):
        return ParmTemplateGroup(self._ptg.templates)

    def setParmTemplateGroup(self, ptg):
        self._ptg = ParmTemplateGroup(ptg.templates)

    def spareParms(self):
        return [self.parm(t.name()) for t in self._ptg.flat()]

    # misc --------------------------------------------------------------------
    def createStickyNote(self):
        n = StickyNote()
        self.notes.append(n)
        return n

    def layoutChildren(self, *a, **k):
        pass

    def moveToGoodPosition(self):
        pass

    def setDisplayFlag(self, on):
        self.display = on

    def setRenderFlag(self, on):
        pass

    def setColor(self, c):
        pass

    def position(self):
        return self._pos

    def setPosition(self, p):
        self._pos = p

    #: node name -> joint names returned by geometry(); set by tests
    FAKE_JOINTS: Dict[str, List[str]] = {}

    def geometry(self, output_index=0):
        return Geometry(Node.FAKE_JOINTS.get(self._name, ()))

    def displayNode(self):
        return self

    def cook(self, force=False):
        pass

    def errors(self):
        return ()

    def warnings(self):
        return ()

    def isDisplayFlagSet(self):
        return self.display

    def parms(self):
        return list(self._parms.values())

    def createDigitalAsset(self, name, hda_file_name, description, min_num_inputs=0, max_num_inputs=0):
        self._type = NodeType(name, OBJ)
        return self


# --- categories / module functions --------------------------------------------------

from apex_studio import compat as _compat  # noqa: E402  (only used for the type table)

_SOP_TYPES = set(n for c in _compat.SOP_NODE_CANDIDATES.values() for n in c) | {
    "geo", "sopnet", "attribwrangle", "python", "null", "object_merge", "file", "timeshift"}
_DOP_TYPES = set(n for c in _compat.DOP_NODE_CANDIDATES.values() for n in c) | {"dopnet"}
SOP = Category("Sop", _SOP_TYPES)
DOP = Category("Dop", _DOP_TYPES)
OBJ = Category("Object", {"geo", "subnet"})

_ROOT = Node(None, "root", "", OBJ)
_OBJ = Node(_ROOT, "obj_root", "obj", OBJ)
_ROOT._children["obj"] = _OBJ


def reset():
    _OBJ._children.clear()


def node(path):
    return _ROOT.node(path)


def sopNodeTypeCategory():
    return SOP


def dopNodeTypeCategory():
    return DOP


def objNodeTypeCategory():
    return OBJ


def applicationVersion():
    return (22, 0, 0)


def applicationVersionString():
    return "22.0.0"


class BoundingBox:
    pass


class playbar:
    @staticmethod
    def frameRange():
        return (1, 48)


def setFrame(f):
    pass


data = types.SimpleNamespace()  # no recipe API in the fake


class hipFile:
    _path = "untitled.hip"

    @staticmethod
    def path():
        return hipFile._path

    @staticmethod
    def save(path=None):
        if path:
            hipFile._path = path


def isUIAvailable():
    return False
