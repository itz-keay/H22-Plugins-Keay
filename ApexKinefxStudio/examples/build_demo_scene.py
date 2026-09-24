"""Build a demo scene with every module and save it as a .hip file.

    hython examples/build_demo_scene.py [demo.hip]

Creates: a heightfield terrain, a drive curve, a car / bike / tank driving
it, a snake and an insect following their own curves, a bird, a jellyfish,
and (if agent FBX paths are given via env vars) crowds.

    AKS_AGENT_FBX=/path/character.fbx  (optional)  -> stadium + state machine crowd
    AKS_RETARGET_SRC / AKS_RETARGET_TGT (optional) -> retarget demo
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "python"))
os.environ.setdefault("APEX_KINEFX_STUDIO", ROOT)

import hou  # noqa: E402

from apex_studio import compat, crowd, network, retarget  # noqa: E402
from apex_studio.rigging import creatures, vehicles  # noqa: E402


def terrain():
    geo = network.obj_container("terrain", clear=True)
    hf = compat.create(geo, "heightfield", "heightfield")
    compat.set_parm(hf, "size", (200.0, 200.0), warn=False)
    compat.set_parm(hf, "gridspacing", 0.5, warn=False)
    noise = compat.create(geo, "heightfield_noise", "noise")
    noise.setInput(0, hf)
    compat.set_parm(noise, "amp", 1.5, warn=False)
    compat.set_parm(noise, "elementsize", 25.0, warn=False)
    out = network.null(geo, "OUT_TERRAIN", noise)
    network.finalize(geo, out)
    return out


def curve(name, points, closed=False):
    geo = network.obj_container(name, clear=True)
    code = ("node = hou.pwd()\ngeo = node.geometry()\n"
            f"pts = {points!r}\n"
            f"poly = geo.createPolygon({closed})\n"
            "for p in pts:\n"
            "    pt = geo.createPoint()\n"
            "    pt.setPosition(p)\n"
            "    poly.addVertex(pt)\n")
    py = network.python_sop(geo, "points", code)
    resample = compat.create(geo, "resample", "resample")
    resample.setInput(0, py)
    compat.set_parm(resample, "length", 0.25, warn=False)
    out = network.null(geo, "OUT_CURVE", resample)
    network.finalize(geo, out)
    return out


def main(hip_path):
    ground = terrain()
    loop = [(math.cos(a) * 40, 0.0, math.sin(a) * 25) for a in [i * 2 * math.pi / 24 for i in range(24)]]
    track = curve("drive_path", loop, closed=True)
    wiggle = curve("creature_path", [(x * 2.0, 0.0, math.sin(x * 0.4) * 4) for x in range(-20, 21)])

    vehicles.build_vehicle(path=track, ground=ground, vehicle_type="car", name="demo_car")
    vehicles.build_vehicle(path=track, ground=ground, vehicle_type="bike", name="demo_bike",
                           speed=15.0).setPosition(hou.Vector2(3, 0))
    vehicles.build_vehicle(path=track, ground=ground, vehicle_type="tank", name="demo_tank", speed=5.0)
    creatures.build_snake(path=wiggle, ground=ground, name="demo_snake")
    creatures.build_insect(path=wiggle, ground=ground, name="demo_insect")
    creatures.build_spider(path=wiggle, ground=ground, name="demo_spider")
    creatures.build_quadruped(path=wiggle, ground=ground, name="demo_quadruped")
    creatures.build_bird(name="demo_bird")
    creatures.build_jellyfish(name="demo_jellyfish")

    agent_fbx = os.environ.get("AKS_AGENT_FBX")
    if agent_fbx:
        agent = crowd.build_agent(agent_fbx, name="demo_agent")
        crowd.build_stadium(agent, name="demo_stadium")
        crowd.build_crowd(agent, name="demo_crowd", ground=ground)
    src, tgt = os.environ.get("AKS_RETARGET_SRC"), os.environ.get("AKS_RETARGET_TGT")
    if src and tgt:
        retarget.build_retarget(src, tgt, name="demo_retarget")

    hou.node("/obj").layoutChildren()
    hou.playbar.setFrameRange(1, 480)
    hou.hipFile.save(hip_path)
    print(f"Saved {hip_path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "apex_kinefx_studio_demo.hip"))
