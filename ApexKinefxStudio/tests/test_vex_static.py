"""Static checks on the VEX sources (no Houdini/vcc needed).

These catch the mistakes that are easy to make when editing VEX outside
Houdini: unresolved includes, unbalanced braces, calls to helpers that do not
exist, channel names with no matching spare parameter, and ambiguous
return-type-overloaded calls (point(), prim(), detail(), ident()) used in
ternaries. They are not a substitute for compiling in Houdini.
"""
import os
import re
import unittest

from tests import _path  # noqa: F401
from apex_studio import network

ROOT = _path.ROOT
SNIPPETS = os.path.join(ROOT, "vex", "snippets")
INCLUDES = os.path.join(ROOT, "vex", "include")
PYROOT = os.path.join(ROOT, "scripts", "python", "apex_studio")


def _strip(code: str) -> str:
    code = re.sub(r"//[^\n]*", "", code)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    return re.sub(r'"(?:\\.|[^"\\])*"', '""', code)


def _snippets():
    return sorted(f for f in os.listdir(SNIPPETS) if f.endswith(".vfl"))


def _defined_functions():
    names = set()
    for fn in os.listdir(INCLUDES):
        code = _strip(open(os.path.join(INCLUDES, fn)).read())
        names.update(re.findall(r"^\s*(?:function\s+)?[\w\[\]]+\s+(aks_\w+)\s*\(", code, re.M))
    return names


def _python_parm_names():
    names = set()
    for dirpath, _, files in os.walk(PYROOT):
        for fn in files:
            if fn.endswith(".py"):
                src = open(os.path.join(dirpath, fn)).read()
                names.update(re.findall(r'\b(?:P|ParmSpec|network\.ParmSpec|hda\.network\.ParmSpec)\(\s*"(\w+)"', src))
    return names


class TestVexStatic(unittest.TestCase):
    def test_includes_resolve(self):
        for fn in _snippets():
            code = network.load_vex(fn)
            self.assertNotRegex(code, r'#include\s+"aks_', fn)

    def test_balanced(self):
        files = [os.path.join(SNIPPETS, f) for f in _snippets()] + \
                [os.path.join(INCLUDES, f) for f in os.listdir(INCLUDES)]
        for path in files:
            code = _strip(open(path).read())
            for a, b in ("{}", "()", "[]"):
                self.assertEqual(code.count(a), code.count(b), f"{os.path.basename(path)} {a}{b}")

    def test_helpers_exist(self):
        defined = _defined_functions()
        for fn in _snippets():
            code = _strip(network.load_vex(fn))
            local = set(re.findall(r"^\s*function\s+[\w\[\]]+\s+(\w+)\s*\(", code, re.M))
            for call in set(re.findall(r"\b(aks_\w+)\s*\(", code)):
                self.assertTrue(call in defined or call in local, f"{fn}: undefined {call}()")

    def test_channels_have_parms(self):
        parms = _python_parm_names()
        for fn in _snippets():
            code = re.sub(r"//[^\n]*", "", open(os.path.join(SNIPPETS, fn)).read())
            for chan in re.findall(r'\bch[fisv]\(\s*"(\w+)"', code):
                self.assertIn(chan, parms, f"{fn}: channel '{chan}' has no ParmSpec")

    def test_no_ambiguous_ternaries(self):
        for fn in _snippets() + os.listdir(INCLUDES):
            base = SNIPPETS if fn.endswith(".vfl") else INCLUDES
            code = _strip(open(os.path.join(base, fn)).read())
            self.assertNotRegex(code, r"[?:]\s*(point|prim|detail|ident|primintrinsic)\s*\(", fn)

    def test_builtin_names_not_shadowed(self):
        builtins = ("tan", "prim", "point", "detail", "length", "noise", "match", "set", "up")
        for fn in _snippets():
            code = _strip(network.load_vex(fn))
            for b in builtins:
                if b == "up":
                    continue
                hit = re.search(rf"\b(?:float|int|vector|string|matrix3?)\s+{b}\s*[=;]", code)
                self.assertIsNone(hit, f"{fn}: variable named '{b}' shadows a VEX function")


if __name__ == "__main__":
    unittest.main()
