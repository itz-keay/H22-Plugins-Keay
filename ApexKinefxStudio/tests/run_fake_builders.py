"""Run every builder against tests/fake_hou.py (invoked by test_builders_fake.py).

Exits non-zero on the first exception, printing the traceback.
"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "python"))
sys.path.insert(0, HERE)
os.environ.setdefault("APEX_KINEFX_STUDIO", ROOT)

import fake_hou  # noqa: E402

sys.modules["hou"] = fake_hou
for mod in [m for m in sys.modules if m.startswith("apex_studio")]:
    del sys.modules[mod]

import apex_studio  # noqa: E402
from apex_studio import compat, crowd, dynamics, hda, network, retarget, validate  # noqa: E402
from apex_studio.rigging import bipeds, creatures, vehicles  # noqa: E402

assert compat.HOU_AVAILABLE, "fake hou was not picked up"


def count(container):
    return len(container.allSubChildren())


def check_wrangles(container):
    """Every wrangle got VEX and every ch() in it has a matching parm template."""
    import re
    for n in container.allSubChildren():
        if n.type().name() != "attribwrangle":
            continue
        code = n.parm("snippet").value or ""
        assert code.strip(), f"{n.path()} has an empty snippet"
        names = {t.name() for t in n.parmTemplateGroup().flat()}
        for chan in re.findall(r'\bch[fisv]\(\s*"(\w+)"', code):
            assert chan in names, f"{n.path()}: ch('{chan}') has no spare parm (have {sorted(names)})"


from apex_studio.core import profiles  # noqa: E402

fake_hou.Node.FAKE_JOINTS = {
    "source": ["mixamorig:" + n for n in profiles.PROFILES["mixamo"].values()],
    "anim_source": ["mixamorig:" + n for n in profiles.PROFILES["mixamo"].values()],
    "target": list(profiles.PROFILES["ue5"].values()),
}


def check_retarget(geo):
    code = geo.node("assign_map").parm("snippet").value
    assert '"thigh_l"' in code and '"mixamorig:LeftUpLeg"' in code, "mapping not baked into VEX"
    def default(node, parm):
        return node.parm(parm).parmTemplate()._default[0]
    assert default(geo.node("world_delta_retarget"), "hips_joint") == "pelvis"
    assert "foot_l" in default(geo.node("foot_lock"), "feet")
    return geo


CASES = [
    ("snake", lambda: creatures.build_snake()),
    ("insect", lambda: creatures.build_insect()),
    ("spider", lambda: creatures.build_spider()),
    ("quadruped", lambda: creatures.build_quadruped()),
    ("bird", lambda: creatures.build_bird()),
    ("jellyfish", lambda: creatures.build_jellyfish()),
    ("biped", lambda: bipeds.build_biped()),
    ("car", lambda: vehicles.build_vehicle(vehicle_type="car")),
    ("bike", lambda: vehicles.build_vehicle(vehicle_type="bike", name="bike")),
    ("tank", lambda: vehicles.build_vehicle(vehicle_type="tank", name="tank")),
    ("retarget", lambda: check_retarget(retarget.build_retarget("/tmp/src.fbx", "/tmp/tgt.fbx"))),
    ("biped+anim", lambda: bipeds.build_biped(animation_fbx="/tmp/mixamo_run.fbx", name="biped_anim")),
    ("agent", lambda: crowd.build_agent("/tmp/agent.fbx", clips={"walk": "/tmp/walk.fbx"})),
    ("stadium", lambda: crowd.build_stadium(None, rows=2, seats_per_row=5)),
    ("crowd", lambda: crowd.build_crowd(None, count=10)),
]

failed = 0
for label, fn in CASES:
    try:
        geo = fn()
        check_wrangles(geo)
        print(f"ok   {label:10s} {count(geo):3d} nodes")
    except Exception:
        failed += 1
        print(f"FAIL {label}")
        traceback.print_exc()

# extra paths
try:
    geo = creatures.build_snake(name="snake_hda")
    hda.convert(geo, "snake_rig", "AKS Snake Rig", "/tmp/aks_test.hda", ["snake_motion", "body_jiggle"])
    assert geo.parm("path_object") is not None
    crowd.build_crowd_dop(fake_hou.node("/obj/aks_crowd/OUT_CROWD"))
    retarget.rebuild_mapping(fake_hou.node("/obj/aks_retarget"))
    validate.report()
    print("ok   hda/dop/rebuild/validate")
except Exception:
    failed += 1
    print("FAIL extra paths")
    traceback.print_exc()

sys.exit(1 if failed else 0)
