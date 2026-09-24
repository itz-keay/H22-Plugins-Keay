"""SOP Crowd Automation Layer.

* :func:`build_agent` - rigged/animated character -> crowd agent with clips
  (Agent SOP from FBX, or Agent From Rig for KineFX skeletons), then Agent
  Clip, Agent Prep and Agent Configure Joints (ragdoll shapes), best effort.
* :func:`build_stadium` - tiered seat layout + stateless idle/cheer layering
  (no simulation: scrubs and renders per frame).
* :func:`build_crowd` - SOP-level state machine in a SOP Solver: walk/run
  variations, trigger volumes, random/time/proximity triggers, clip blending,
  neighbour avoidance, ground snapping, and ragdoll flagging (i@ragdoll and
  a ``ragdoll`` group for the physics hand-off).
* :func:`build_crowd_dop` - the equivalent stock DOP crowd network (Crowd
  Object/Solver/State/Transition/Trigger) for teams that prefer it, and for
  the ragdoll physics hand-off. Built best effort with label-based wiring.

The state machine is data (:class:`core.crowd_layout.StateMachine`), written
to detail attributes so the VEX step can read it.
"""

from __future__ import annotations

import json
import math
from typing import Dict, List, Optional, Sequence, Tuple

from . import compat, network
from .compat import LOG, require_hou
from .core import crowd_layout
from .core.crowd_layout import CrowdState, CrowdTransition, StateMachine
from .network import ParmSpec as P


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

def _set_multiparm(node, count_names: Sequence[str], entries: Sequence[Dict[str, object]]) -> bool:
    """Fill a multiparm. ``entries`` use '#' in parm names for the 1-based index."""
    for cname in count_names:
        if node.parm(cname) is not None:
            node.parm(cname).set(len(entries))
            for i, entry in enumerate(entries, start=1):
                for key, value in entry.items():
                    names = [k.replace("#", str(i)) for k in key.split("|")]
                    compat.set_parm(node, names, value)
            return True
    LOG.warning("No multiparm %s on %s", count_names, node.path())
    return False


def build_agent(character, clips: Optional[Dict[str, str]] = None, name: str = "aks_agent",
                agent_name: str = "hero", ragdoll_shapes: bool = True):
    """Create an agent from a character FBX (plus extra clip FBX files).

    ``character``: FBX path, or a SOP node outputting a KineFX character
    (rest geometry in output 0). ``clips``: {clip name: FBX file}.
    Returns the last SOP node (agent with clips).
    """
    require_hou()
    geo = network.obj_container(name, clear=True)
    if isinstance(character, str) and character.lower().endswith(".fbx"):
        agent = compat.create(geo, "agent", "agent")
        compat.set_parm(agent, "agentname", agent_name)
        compat.set_parm(agent, ("input", "source"), "fbx", warn=False)
        compat.set_parm(agent, ("fbxfile", "file"), character)
    else:
        src = network.input_or_placeholder(geo, "character_in", character)
        agent = compat.create(geo, "agent_from_rig", "agent_from_rig", required=False) or \
            compat.create(geo, "agent", "agent")
        agent.setInput(0, src)
        compat.set_parm(agent, "agentname", agent_name, warn=False)
    last = agent

    if clips:
        clip_node = compat.create(geo, "agent_clip", "agent_clips", required=False)
        if clip_node is not None:
            clip_node.setInput(0, last)
            _set_multiparm(clip_node, ("clips", "numclips"), [
                {"name#|clipname#": clip, "file#|fbxfile#|source#": path} for clip, path in clips.items()
            ])
            last = clip_node

    prep = compat.create(geo, "agent_prep", "agent_prep", required=False)
    if prep is not None:
        prep.setInput(0, last)
        last = prep
    if ragdoll_shapes:
        joints = compat.create(geo, "agent_configure_joints", "ragdoll_shapes", required=False)
        if joints is not None:
            joints.setInput(0, last)
            last = joints
    out = network.null(geo, "OUT_AGENT", last, (0.9, 0.5, 0.9))
    network.note(geo, "Agent build (best effort). Check the Agent Clip multiparm entries,\n"
                      "Agent Prep (foot/locomotion joints) and Agent Configure Joints\n"
                      "(collision shapes for ragdolls) in your Houdini build.", near=agent)
    network.finalize(geo, out)
    return out


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def _points_sop(parent, name: str, points: Sequence[Tuple[Tuple[float, float, float], float]]):
    data = [[list(p), yaw] for p, yaw in points]
    code = ("import json, math\nnode = hou.pwd()\ngeo = node.geometry()\n"
            "geo.addAttrib(hou.attribType.Point, 'orient', (0.0, 0.0, 0.0, 1.0))\n"
            "geo.addAttrib(hou.attribType.Point, 'id', 0)\n"
            f"data = json.loads({json.dumps(data)!r})\n"
            "for i, (p, yaw) in enumerate(data):\n"
            "    pt = geo.createPoint()\n"
            "    pt.setPosition(p)\n"
            "    pt.setAttribValue('orient', (0.0, math.sin(yaw * 0.5), 0.0, math.cos(yaw * 0.5)))\n"
            "    pt.setAttribValue('id', i)\n")
    return network.python_sop(parent, name, code)


def _copy_agents(parent, agent_in, points, name: str = "copy_agents"):
    copy = compat.create(parent, "copytopoints", name)
    copy.setInput(0, agent_in)
    copy.setInput(1, points)
    return copy


def _state_machine_sop(parent, sm: StateMachine, input_node, name: str = "state_machine_data"):
    data = sm.to_detail()
    code = ("import json\nnode = hou.pwd()\ngeo = node.geometry()\n"
            f"data = json.loads({json.dumps(data)!r})\n"
            "kinds = {str: hou.attribData.String, float: hou.attribData.Float, int: hou.attribData.Int}\n"
            "for key, values in data.items():\n"
            "    t = type(values[0]) if values else str\n"
            "    if geo.findGlobalAttrib(key) is None:\n"
            "        geo.addArrayAttrib(hou.attribType.Global, key, kinds[t])\n"
            "    geo.setGlobalAttribValue(key, values)\n")
    return network.python_sop(parent, name, code, inputs=[input_node])


def trigger_volumes(parent, names_and_boxes: Dict[str, Tuple[Tuple[float, float, float], Tuple[float, float, float]]],
                    name: str = "triggers"):
    """Named boxes {name: (center, size)} used as trigger volumes."""
    merge = compat.create(parent, "merge", name)
    for i, (tname, (center, size)) in enumerate(names_and_boxes.items()):
        box = compat.create(parent, "box", f"trigger_{tname}")
        compat.set_parm(box, "size", tuple(size))
        compat.set_parm(box, "t", tuple(center))
        tag = network.wrangle(parent, f"name_{tname}", f's@name = "{tname}";', "primitives",
                              inputs=[box], from_file=False)
        merge.setInput(i, tag)
    return merge


# ---------------------------------------------------------------------------
# Stadium
# ---------------------------------------------------------------------------

def build_stadium(agent, name: str = "aks_stadium", rows: int = 12, seats_per_row: int = 60,
                  inner_radius: float = 30.0, arc_degrees: float = 120.0, event_frames: str = "120 360",
                  idle_clip: str = "idle", cheer_clip: str = "cheer"):
    require_hou()
    geo = network.obj_container(name, clear=True)
    agent_in = network.input_or_placeholder(geo, "agent_in", agent)
    seats = crowd_layout.stadium_seats(rows, seats_per_row, inner_radius, arc_degrees=arc_degrees)
    pts = _points_sop(geo, "seats", seats)
    agents = _copy_agents(geo, agent_in, pts)
    layer = network.wrangle(geo, "cheer_layering", "crowd_stadium", "primitives", inputs=[agents], parms=[
        P("idle_clip", "Idle Clip", "string", idle_clip),
        P("cheer_clip", "Cheer Clip", "string", cheer_clip),
        P("event_frames", "Event Frames", "string", event_frames,
          help="Space separated frames (goals, songs...) the crowd reacts to."),
        P("reaction_delay_max", "Max Reaction Delay (s)", "float", 0.8, 0, 5),
        P("cheer_hold", "Cheer Duration (s)", "float", 3.0, 0, 20),
        P("blend_time", "Blend Time (s)", "float", 0.4, 0, 3),
        P("enthusiasm_min", "Min Enthusiasm", "float", 0.4, 0, 1),
        P("spontaneous_period", "Spontaneous Period (s)", "float", 4.0, 0, 60),
        P("spontaneous_probability", "Spontaneous Probability", "float", 0.05, 0, 1),
        P("loop_cheer", "Loop Cheer Clip", "toggle", True),
        P("seed", "Seed", "float", 1.0, 0, 100),
    ])
    out = network.null(geo, "OUT_CROWD", layer, (0.9, 0.5, 0.9))
    network.note(geo, f"{len(seats)} seats. Stateless: every frame is computed independently\n"
                      "(random offsets per agent, reactions to Event Frames).", near=layer)
    network.finalize(geo, out)
    return geo


# ---------------------------------------------------------------------------
# SOP state machine crowd
# ---------------------------------------------------------------------------

def build_crowd(agent, count: int = 200, name: str = "aks_crowd", state_machine: Optional[StateMachine] = None,
                triggers: Optional[Dict[str, Tuple[Tuple[float, float, float], Tuple[float, float, float]]]] = None,
                ground=None, spacing: float = 1.5, goal: Tuple[float, float, float] = (0.0, 0.0, 60.0)):
    """Walk/run/ragdoll crowd driven by the SOP-level state machine."""
    require_hou()
    sm = state_machine or crowd_layout.default_walk_run_ragdoll()
    geo = network.obj_container(name, clear=True)
    agent_in = network.input_or_placeholder(geo, "agent_in", agent)
    pts = _points_sop(geo, "start_points",
                      [(p, 0.0) for p in crowd_layout.grid_layout(count, spacing)])
    agents = _copy_agents(geo, agent_in, pts)
    with_sm = _state_machine_sop(geo, sm, agents)
    trig = trigger_volumes(geo, triggers or {
        "panic": ((0.0, 1.0, 20.0), (40.0, 4.0, 6.0)),
        "hazard": ((0.0, 1.0, 40.0), (8.0, 4.0, 4.0)),
    })
    ground_in = network.input_or_placeholder(geo, "ground_in", ground)
    solver = network.make_solver(geo, "crowd_state_machine", "crowd_state_machine_step",
                                 inputs=[with_sm, trig, ground_in], run_over="points", parms=[
        P("start_frame", "Start Frame", "float", 1.0, 1, 1000),
        P("use_goal", "Steer to Goal", "toggle", True),
        P("goal", "Goal", "vector", goal, -1000, 1000),
        P("avoid_radius", "Avoid Radius", "float", 1.2, 0, 10),
        P("avoid_neighbours", "Avoid Neighbours", "int", 8, 0, 64),
        P("avoid_strength", "Avoid Strength", "float", 0.6, 0, 5),
        P("turn_rate", "Turn Rate (deg/s)", "float", 120.0, 0, 720),
        P("snap_to_ground", "Snap to Ground", "toggle", True),
    ])
    out = network.null(geo, "OUT_CROWD", solver, (0.9, 0.5, 0.9))
    network.note(geo, "States: " + ", ".join(s.name for s in sm.states) + "\n"
                      "Transitions: " + "; ".join(f"{t.src}->{t.dst} on {t.trigger}" for t in sm.transitions) +
                 "\nMove the trigger boxes to stage the action. Agents flagged i@ragdoll=1\n"
                 "(group 'ragdoll') are ready for the ragdoll hand-off (build_crowd_dop).",
                 near=solver)
    network.finalize(geo, out)
    return geo


# ---------------------------------------------------------------------------
# DOP crowd (stock nodes) - best effort
# ---------------------------------------------------------------------------

def build_crowd_dop(agents_sop, sm: Optional[StateMachine] = None, name: str = "crowd_dop"):
    """Stock crowd DOP network inside a DOP Network SOP next to ``agents_sop``.

    Creates Crowd Object -> Crowd Solver with one Crowd State per state and a
    Crowd Transition per transition. Ragdoll states get the state's ragdoll
    option enabled when present. Wiring uses input labels because the crowd
    solver's input order is not guaranteed across builds; review the network.
    """
    sm = sm or crowd_layout.default_walk_run_ragdoll()
    parent = agents_sop.parent()
    dopnet = compat.create(parent, "dopnet", name)
    obj = compat.create(dopnet, "crowd_object", "crowdobject", kind="dop")
    compat.set_parm(obj, ("soppath", "sop_path"), dopnet.relativePathTo(agents_sop))
    solver = compat.create(dopnet, "crowd_solver", "crowdsolver", kind="dop")
    solver.setInput(0, obj)
    states = {}
    merge = compat.create(dopnet, "merge", "states", kind="dop")
    for i, st in enumerate(sm.states):
        node = compat.create(dopnet, "crowd_state", f"state_{st.name}", kind="dop")
        compat.set_parm(node, ("statename", "name"), st.name)
        compat.set_parm(node, ("clipname", "clip"), st.clip.split("|")[0], warn=False)
        if st.ragdoll:
            compat.set_parm(node, ("ragdoll", "enableragdoll", "ragdollmode"), 1, warn=True)
        merge.setInput(i, node)
        states[st.name] = node
    for i, tr in enumerate(sm.transitions):
        node = compat.create(dopnet, "crowd_transition", f"tr_{tr.src}_{tr.dst}".replace("*", "any"), kind="dop")
        compat.set_parm(node, ("inputstate", "fromstate"), tr.src if tr.src != "*" else "*", warn=False)
        compat.set_parm(node, ("outputstate", "tostate"), tr.dst, warn=False)
        merge.setInput(len(sm.states) + i, node)
    compat.connect_by_label(solver, merge, ["state", "transition", "crowd"], fallback_index=2)
    out = compat.create(dopnet, "output", "output", kind="dop", required=False)
    if out is not None:
        out.setInput(0, solver)
        out.setDisplayFlag(True)
    dopnet.layoutChildren()
    LOG.info("Built stock crowd DOP network %s (review state/transition parameters).", dopnet.path())
    return dopnet
