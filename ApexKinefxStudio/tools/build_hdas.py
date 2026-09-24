"""Build the ApexKinefxStudio digital assets.

    hython tools/build_hdas.py [otls/apex_kinefx_studio.hda]

Builds each tool network with its defaults, exposes its inputs as object
path parameters, promotes the motion/solver parameters, and saves every asset
into one HDA library. Re-run after changing the Python or VEX sources.
"""

import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "python"))
os.environ.setdefault("APEX_KINEFX_STUDIO", ROOT)

import hou  # noqa: E402

from apex_studio import crowd, hda, retarget  # noqa: E402
from apex_studio.rigging import creatures, vehicles  # noqa: E402

HELP = "= {label} =\n\nBuilt by ApexKinefxStudio. See README.md in the package for usage.\n"

# (type name, label, builder, kwargs, internal nodes whose parms get promoted)
ASSETS = [
    ("snake_rig", "AKS Snake Rig", creatures.build_snake, {}, ["snake_motion", "body_jiggle"]),
    ("insect_rig", "AKS Insect Rig", creatures.build_insect, {}, ["insect_motion", "spring_chain"]),
    ("spider_rig", "AKS Spider Rig", creatures.build_spider, {}, ["spider_motion"]),
    ("quadruped_rig", "AKS Quadruped Rig", creatures.build_quadruped, {}, ["quadruped_motion", "spring_chain"]),
    ("bird_rig", "AKS Bird Rig", creatures.build_bird, {}, ["bird_motion", "feather_drag"]),
    ("jellyfish_rig", "AKS Jellyfish Rig", creatures.build_jellyfish, {}, ["jellyfish_motion"]),
    ("car_rig", "AKS Car Rig", vehicles.build_vehicle, {"vehicle_type": "car"}, ["drive", "dynamics"]),
    ("bike_rig", "AKS Bike Rig", vehicles.build_vehicle, {"vehicle_type": "bike", "speed": 15.0},
     ["drive", "dynamics"]),
    ("tank_rig", "AKS Tank Rig", vehicles.build_vehicle, {"vehicle_type": "tank", "speed": 5.0},
     ["drive", "dynamics", "treads"]),
]


def build_retarget_asset(hda_path: str) -> None:
    geo = retarget.build_retarget("$HIP/source.fbx", "$HIP/target.fbx", name="aks_retarget_asset")
    network_parms = [
        hda.network.ParmSpec("source_fbx", "Source FBX", "string", "$HIP/source.fbx", folder="Files"),
        hda.network.ParmSpec("target_fbx", "Target FBX", "string", "$HIP/target.fbx", folder="Files"),
    ]
    hda.network.add_spare_parms(geo, network_parms, folder="Files")
    for node_name, parm in (("source", "source_fbx"), ("target", "target_fbx")):
        node = geo.node(node_name)
        for cand in ("fbxfile", "file", "filename"):
            if node is not None and node.parm(cand) is not None:
                node.parm(cand).setExpression(f'chs("../{parm}")')
                break
    ptg = geo.parmTemplateGroup()
    button = hou.ButtonParmTemplate("update_mapping", "Update Joint Mapping")
    button.setScriptCallback("import apex_studio.retarget as r; r.rebuild_mapping(kwargs['node'])")
    button.setScriptCallbackLanguage(hou.scriptLanguage.Python)
    ptg.append(button)
    geo.setParmTemplateGroup(ptg)
    hda.convert(geo, "retarget", "AKS Retarget", hda_path, ["world_delta_retarget", "foot_lock"],
                HELP.format(label="AKS Retarget"))


def main(hda_path: str) -> int:
    failures = 0
    for type_name, label, builder, kwargs, promote in ASSETS:
        try:
            geo = builder(name=f"{type_name}_build", **kwargs)
            hda.convert(geo, type_name, label, hda_path, promote, HELP.format(label=label))
        except Exception:
            failures += 1
            print(f"FAILED {type_name}:\n{traceback.format_exc()}")
    try:
        build_retarget_asset(hda_path)
    except Exception:
        failures += 1
        print(f"FAILED retarget:\n{traceback.format_exc()}")
    print(f"Done: {len(ASSETS) + 1 - failures} assets written to {hda_path}, {failures} failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "otls", "apex_kinefx_studio.hda")
    sys.exit(main(out))
