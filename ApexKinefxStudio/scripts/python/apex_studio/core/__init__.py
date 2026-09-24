"""Pure-Python core: no ``hou`` imports allowed in this subpackage.

Everything here is deterministic math or data (skeleton profiles, joint
mapping, vehicle kinematics, gait phases, skeleton guide generation), so it can
be unit-tested with the standard library outside Houdini. The VEX snippets in
``vex/`` implement the same formulas per frame; the tests keep them honest.
"""
