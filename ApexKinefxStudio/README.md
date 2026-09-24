# ApexKinefxStudio

Procedural rigging, retargeting, vehicle and crowd tools for Houdini (targets
**Houdini 22**, designed to run on 20.5+), built on KineFX skeletons and APEX
characters.

| Module | What it builds |
|---|---|
| `retarget` | Mixamo / Cascadeur / UE5 / Rigify / custom animation -> any KineFX rig, with automatic joint mapping, rest-pose matching, root-motion options and foot locking |
| `rigging.bipeds` | Humanoid rig from a mesh: canonical skeleton, skinning, APEX character, optional retargeted animation |
| `rigging.creatures` | Snake/worm, insect, spider, quadruped, bird, jellyfish, each with procedural motion |
| `rigging.vehicles` | Car / truck / bike / tank following a curve over a heightfield or mesh: rolling wheels, suspension, steering, body roll/pitch, drift, vibration, tank treads |
| `dynamics` | Spring chains, jiggle, vibration, velocity drag for any skeleton |
| `crowd` | Agents from characters, stateless stadium crowds, SOP state-machine crowds with trigger volumes and ragdoll hand-off, stock DOP crowd networks |

> **Status: first implementation, not yet run inside Houdini.** The Python and
> the math are unit-tested outside Houdini (see [Tests](#tests)), and every
> builder runs end to end against a recording fake of `hou`. But no network has
> been cooked in a real Houdini session yet, and none of the VEX has been
> compiled. Expect a round of fixes the first time you run it. Start with
> [Verify your Houdini build](#1-verify-your-houdini-build) and report what the
> probe and the demo scene print.

---

## Contents

1. [Install](#install)
2. [Quick start](#quick-start)
3. [Architecture](#architecture)
4. [Retargeting](#retargeting)
5. [Creatures](#creatures)
6. [Vehicles](#vehicles)
7. [Secondary dynamics](#secondary-dynamics)
8. [Crowds](#crowds)
9. [Digital assets](#digital-assets)
10. [Tests](#tests)
11. [Limitations and roadmap](#limitations-and-roadmap)

---

## Install

1. Copy (or clone) the `ApexKinefxStudio/` folder somewhere, e.g.
   `~/houdini_packages/ApexKinefxStudio`.
2. Copy `ApexKinefxStudio.json` into your Houdini packages folder
   (`$HOUDINI_USER_PREF_DIR/packages/`, e.g. `~/houdini22.0/packages/`).
3. Edit `APEX_KINEFX_STUDIO` in that JSON so it points at the folder from step 1.
4. Start Houdini. The package adds itself to `HOUDINI_PATH`, which gives you:
   * the Python package `apex_studio` (from `scripts/python/`)
   * the **ApexKinefxStudio** shelf (`toolbar/`; add it with the shelf's `+` tab menu)
   * any HDAs you build into `otls/`
   * the VEX headers in `vex/include/` (usable as `#include "aks_path.h"` in your own wrangles)

Optional: set `APEX_KINEFX_STUDIO_VALIDATE=1` to run the environment check at
startup (`scripts/123.py`). Houdini only runs the **first** `123.py` on the
path, so delete ours if your studio already has one.

### 1. Verify your Houdini build

Native node type and parameter names change between Houdini releases, so the
package resolves them at runtime (`apex_studio/compat.py`) and never hard-fails
on a renamed parameter: it logs a warning and leaves the default. Check what
resolved in your build:

```bash
hython tools/probe_node_types.py            # writes node_types_report.json
hython examples/build_demo_scene.py         # builds every tool into a .hip
```

Or run the shelf's **Validate** tool / `apex_studio.validate.report(verbose=True)`.

---

## Quick start

In the Python Shell, or from the shelf:

```python
import apex_studio as aks

# Retarget a Mixamo run onto your character (both FBX)
aks.retarget.build_retarget("/path/mixamo_run.fbx", "/path/my_character.fbx")

# Vehicles: select nothing to get a demo wheel layout, or pass your model
aks.vehicles.build_vehicle(path="/obj/road/OUT", ground="/obj/terrain/OUT", vehicle_type="car")
aks.vehicles.build_vehicle(model="/obj/tank_model", vehicle_type="tank", speed=5)

# Creatures
aks.creatures.build_snake(path="/obj/snake_path/OUT", ground="/obj/terrain/OUT")
aks.creatures.build_insect(num_legs=6, gait="tripod")
aks.creatures.build_bird()
aks.creatures.build_jellyfish()

# Crowds
agent = aks.crowd.build_agent("/path/character.fbx", clips={"walk": "/path/walk.fbx", "run": "/path/run.fbx"})
aks.crowd.build_stadium(agent, event_frames="120 360")
aks.crowd.build_crowd(agent, count=300)
```

Every builder creates a normal, readable network under `/obj/<name>` with
sticky notes, output nulls (`OUT_REST_SKELETON`, `OUT_ANIM_SKELETON`,
`OUT_MESH`) and all tunables as spare parameters on the motion node.
Nothing is hidden in compiled code. Inputs you don't pass are red Null
placeholders (`path_in`, `ground_in`, `mesh_in`...) you can wire later.

---

## Architecture

```
ApexKinefxStudio/
├── ApexKinefxStudio.json         package definition (adds the folder to HOUDINI_PATH)
├── scripts/
│   ├── 123.py                    optional startup validation
│   └── python/apex_studio/
│       ├── __init__.py
│       ├── compat.py             node-type resolution, defensive parm setting
│       ├── network.py            wrangle/solver/spare-parm/note helpers, VEX loader
│       ├── retarget.py           retargeting engine
│       ├── dynamics.py           secondary motion
│       ├── crowd.py              crowd layer
│       ├── hda.py                network -> digital asset conversion
│       ├── validate.py           environment report
│       ├── rigging/{bipeds,creatures,vehicles,common}.py
│       └── core/                 pure Python (no hou): profiles, gait, vehicle math,
│                                 guide skeletons, crowd layouts/state machine
├── vex/
│   ├── include/aks_*.h           skeleton, path, ground, IK, gait, vehicle helpers
│   └── snippets/*.vfl            one file per wrangle / solver step
├── otls/                         generated HDAs (tools/build_hdas.py)
├── toolbar/                      shelf
├── tools/                        probe_node_types.py, build_hdas.py
├── examples/                     build_demo_scene.py
└── tests/                        unit tests + fake-hou builder smoke test
```

Design rules:

* **Source-first.** The logic lives in Python and `.vfl` files so it can be
  diffed and reviewed; HDAs are generated from it. `network.load_vex()` inlines
  the `aks_*.h` headers into each wrangle at build time, so built scenes keep
  working without the package installed.
* **Closed-form where possible.** Creature and vehicle motion is a function of
  time/distance, not a simulation. It scrubs, renders per frame on a farm, and
  needs no cache. Only true dynamics (spring chains, vehicle body springs,
  foot lock, crowd state machines) use SOP Solvers.
* **KineFX conventions.** Joints are points with `name`, `P`, `3@transform`
  (world) and `4@localtransform`, linked parent -> child by polylines. All VEX
  uses row-vector matrices (`p_world = p_local * M`).
* **Native nodes where they're solid, our own VEX where we need control.**
  SideFX nodes are used for FBX import, capture, deformation, agents and APEX
  packaging. Retargeting, IK, gait, vehicle and crowd logic are our own VEX, so
  the math is known and tested.

A note on terms: APEX is SideFX's *All-Purpose EXecution* graph framework, not
an Autodesk technology. KineFX has no `mapblends` node, and there is no
`apex::autorig` / `apex::character` node pair. The closest native nodes, which
this package uses, are Rig Match Pose / Map Points / Full Body IK for retargeting
and Pack Folder + APEX Autorig Component for APEX characters.

---

## Retargeting

```python
from apex_studio import retarget
geo = retarget.build_retarget(
    "/anim/mixamo_run.fbx", "/chars/hero.fbx", name="hero_run",
    options=retarget.RetargetOptions(root_motion="in_place", foot_lock=True))
```

Network: `source` / `target` (FBX Character Import) → `assign_map` → `pose_match` → `world_delta_retarget` → `foot_lock` → `deform`.

1. **Joint mapping.** `core.profiles` knows Mixamo (with or without
   `mixamorig:` namespaces), UE5 Mannequin, Cascadeur (UE-style default
   humanoid), Rigify and Houdini-style names. It detects profiles, maps
   source → canonical → target, then fuzzy-matches the rest (same side only).
   The result is baked into `assign_map` as two VEX arrays you can edit by
   hand. `retarget.rebuild_mapping(container)` recomputes it after you swap
   files. Custom profiles: `profiles.load_profile_json("my_rig.json")`.
2. **Rest-pose match** (`retarget_pose_match.vfl`). The source rest is rotated
   bone by bone onto the target's rest directions, so T-pose vs A-pose (or
   splayed fingers) don't leak into the animation.
3. **World-delta retarget** (`retarget_world_delta.vfl`). For each mapped joint,
   `R_tgt = R_tgt_rest · R_src_matched⁻¹ · R_src_anim`, applied parent-first.
   Positions are rebuilt by FK with the **target's** bone lengths, so there is
   no stretching. The hips translate by the source delta scaled by the
   hip-height ratio. Root motion can be *keep*, *in place* (XZ locked) or
   *none*.
4. **Foot lock** (SOP Solver, `foot_lock_step.vfl`). A foot is in contact when
   it is low and slow. While in contact it is pinned, and the leg is re-solved
   with analytic two-bone IK. Locks blend in and out over a short time.
5. A **native branch** (Rig Match Pose → Map Points → Full Body IK) is built
   next to it behind a Switch, so you can compare with the stock workflow.
   `retarget.apex_retarget()` feeds an animated skeleton into
   *APEX Animation from Skeleton* for an existing APEX character.
   `retarget.try_biped_recipe()` tries Houdini 22's biped recipe if the recipe
   API is exposed (discovered at runtime).
6. **Batch:** `retarget.batch_retarget(folder, target_fbx, out_dir)` writes one
   `.bgeo.sc` sequence per clip.

**Bipeds** (`rigging.bipeds.build_biped(mesh, animation_fbx=...)`) place a
canonical skeleton from the mesh bounding box, capture it, package an APEX
character, and optionally retarget a Mixamo/Cascadeur clip onto it (the
mapping is exact because the names are canonical).

---

## Creatures

All creatures follow a curve (`path_in`, optional; defaults to +Z) over a
ground (`ground_in`: heightfield or mesh, optional; defaults to y = 0).

| Builder | Motion model | Key parameters |
|---|---|---|
| `build_snake` | Each joint samples the path at `u = head_distance − arclen`, so the body follows the head's track (no sliding). Lateral undulation is a world-fixed wave `A·sin(2πu/λ + ωt)`; twist and banking are functions of `u`, so they travel head → tail. Joints are ray-cast to the ground and aligned to its normal. Optional jiggle. | speed, amplitude, wavelength, phase speed (0 = serpentine), twist, bank, head lift |
| `build_insect` / `build_spider` | Distance-driven gait (`core/gait.py`): phase `p = frac(d/stride + offset)`; stance feet are planted at the body's home position evaluated at mid-stance, swing feet arc to the next plant. Closed form, so feet never slide. Legs use coxa yaw + two-bone IK (knees up/out); the body follows the terrain slope and bobs slightly. | gait (tripod, wave, tetrapod, metachronal...), stride, step height, duty factor |
| `build_quadruped` | Same solver with fore/aft knee poles; walk, trot, pace, canter, gallop, bound tables; spring-chain tail. | gait, stride, knee directions |
| `build_bird` | Path flight with banking `atan(v²κ/g)`. Wings are FK chains; segment k flaps by `A·w_k·sin(ωt − k·lag)` (automatic follow-through), sweeps back with speed (velocity drag), and folds by a single parameter. Tail fans with banking. Velocity drag on feathers. | flap amount (0 = glide), fold, frequency, amplitude, lag |
| `build_jellyfish` | Closed-form pulse: fast contraction, slow relax. Thrust happens only while contracting. Tentacles use follow-the-leader lag: joint k samples the bell motion at `t − k·lag`, then segment lengths are restored. | pulse frequency, contraction ratio, thrust, tentacle lag, curl |

Pass `mesh=` to skin a model (biharmonic by default, `capture_method="proximity"`
for non-watertight meshes, `"rigid"` for per-piece models).

---

## Vehicles

```python
from apex_studio.rigging import vehicles
vehicles.build_vehicle(model="/obj/car_model", path="/obj/road", ground="/obj/terrain",
                       vehicle_type="car", speed=15)
```

**Model conventions:** +Z forward, +X left, Y up, resting on y = 0, pieces
named by a primitive `name` attribute. Pieces whose name contains
`wheel/tire/tyre/rim` are wheels (radius and axle from the bounding box; front
wheels steer). `body/chassis/hull/frame/shell` pieces are the body. Every other
named piece becomes a rigid part under the body. Packed models are unpacked
automatically. You can also pass `wheels=[{name, center, radius, side, steers}]`.

**Drive** (`vehicle_drive.vfl`, closed form, scrubbable):

* distance `s(t)` from a constant speed, or a keyable **Distance** channel
  (keys give accelerate/brake/reverse); `v` and `a` by finite differences
* heading from the path tangent; signed curvature κ over a smoothing window
* **ground conform:** every wheel is ray-cast (heightfield `height` layer or
  mesh), and a least-squares plane through the contacts gives chassis height,
  pitch and roll
* **suspension:** each wheel closes its own gap to the ground within the travel
* **rolling wheels:** `angle = distance_this_wheel / radius` (radians), i.e.
  `revolutions = Δd / (2π·r)`. A wheel offset `w` from the path centre travels
  `s − w·Δθ` (Δθ = heading change), so inner wheels turn slower than outer ones
  and nothing skates. Reversing just works.
* **steering:** Ackermann `δ = atan(L·κ / (1 ∓ κ·T/2))` for cars;
  `atan(L·κ)` for bikes; none for tanks (skid steer)
* **body:** squat/dive from longitudinal acceleration, roll from `v²κ`
  (leaning out); bikes lean in by `atan(v²κ/g)`
* **drift:** past the grip limit, slip angle `β` grows with lateral
  acceleration. The body yaws into the turn, the front wheels counter-steer,
  and wheel points get `f@skid` for smoke and skid marks

**Dynamics** (`vehicle_dynamics_step.vfl`, SOP Solver): damped springs let the
body chase the kinematic pitch/roll (overshoot on braking and turn-in), a heave
spring kicked by terrain bumps, engine idle buzz that fades with speed, road
vibration scaled by speed and terrain roughness, and extra spin on driven
wheels while drifting. Loose parts (`part_*`) get their own vibration.

**Tanks:** road wheels/sprockets on each side are wrapped by a convex-hull
track loop. Tread links slide along it by that side's travelled distance, and
links on the bottom run conform to the ground. Replace `tread_link` with your
own link model.

---

## Secondary dynamics

```python
from apex_studio import dynamics
anim = dynamics.add_spring_chain(geo, anim, "tail_* antenna_*")        # chain, length preserving
anim = dynamics.add_spring_chain(geo, anim, "belly", mode="jiggle")     # lag + overshoot
anim = dynamics.add_vibration(geo, anim, "part_*", amplitude=0.1)       # follows detail f@speed
anim = dynamics.add_velocity_drag(geo, anim, "ear_* feather_*")        # stateless trailing
anim = dynamics.add_native_secondary(geo, anim, "tail_*")               # SideFX Secondary Motion SOP
```

Joint patterns use Houdini wildcards separated by spaces. A point attribute
`f@secondary_amount` (0–1) scales the spring chain per joint.

---

## Crowds

* `build_agent(fbx, clips={...})` → Agent (FBX) or Agent From Rig → Agent
  Clip → Agent Prep → Agent Configure Joints (ragdoll collision shapes).
* `build_stadium(agent, rows, seats_per_row, event_frames="120 360")`: tiered
  seat layout facing the pitch; every agent loops an idle clip with a random
  offset and blends into a cheer after each event frame, with random reaction
  delay, duration and enthusiasm, plus spontaneous cheers. **Stateless**: no
  simulation.
* `build_crowd(agent, count, state_machine=...)`: a SOP Solver runs a
  declarative state machine (`core.crowd_layout.StateMachine`). States have a
  clip (variations separated by `|`), a speed, looping, and a ragdoll flag.
  Transitions fire on `volume:<name>`, `time:<frame>`, `random:<p/sec>`,
  `near:<radius>` or `clip_end`, with timed clip blending. Agents steer to a
  goal with neighbour avoidance and snap to the ground. Ragdoll states set
  `i@ragdoll` and a `ragdoll` group for the physics hand-off. Trigger volumes
  are named boxes (or SDF volumes) you move around.
* `build_crowd_dop(agents)`: the same machine as stock Crowd Object / Solver /
  State / Transition nodes, for the physics ragdoll hand-off. Built best
  effort; review the state parameters.

```python
from apex_studio.core.crowd_layout import StateMachine, CrowdState, CrowdTransition
sm = StateMachine(
    states=[CrowdState("walk", "walk|walk_b", 1.4), CrowdState("run", "run", 4.0),
            CrowdState("cheer", "cheer", 0.0, loop=False), CrowdState("fall", "run", 0, ragdoll=True)],
    transitions=[CrowdTransition("walk", "run", "near:3"), CrowdTransition("*", "fall", "volume:hazard"),
                 CrowdTransition("run", "cheer", "time:200"), CrowdTransition("cheer", "walk", "clip_end")],
    initial="walk")
```

---

## Digital assets

```bash
hython tools/build_hdas.py      # -> otls/apex_kinefx_studio.hda
```

Each tool is built with defaults. Placeholder inputs become object-path
parameters, and motion/solver parameters are promoted into folders. The
retarget asset has *Source FBX*, *Target FBX* and an **Update Joint Mapping**
button. See `otls/README.md`. Apprentice/Indie users should pass a
`.hdanc`/`.hdalc` path.

---

## Tests

```bash
cd ApexKinefxStudio
python3 -m unittest discover -s tests -t .
```

No Houdini needed:

* **core math:** wheel rotation units, offset-wheel arc length on a circle
  (inner `2π(R−w)`, outer `2π(R+w)`), Ackermann, bike lean, drift, plane fit,
  springs, part classification, track loops, gait (no sliding while planted,
  continuous foot paths), guides, profile detection and mapping
  (Mixamo ↔ UE5 ↔ Cascadeur), stadium layout, state machine
* **VEX static checks:** includes resolve, braces balance, every `aks_*`
  helper exists, every `ch*()` channel has a spare parameter, no ambiguous
  `point()`/`prim()` ternaries, no variables shadowing VEX functions
* **builder smoke test:** every builder runs against `tests/fake_hou.py`, a
  recording fake of `hou`; it checks wiring and that every wrangle's channels
  exist

These checks do not compile VEX or cook networks. Only Houdini can do that.

---

## Limitations and roadmap

* **Not yet run in Houdini** (see the status note above). The first priority is
  a pass in a live H22 session: probe the node types, build the demo scene,
  and fix what the VEX compiler and cooking report.
* Native node **parameter names** (Pack Folder entries, Agent Clip multiparm,
  crowd DOP states, Full Body IK inputs) are set best effort and logged when
  they don't exist. The APEX character and stock crowd DOP networks need a
  review in your build.
* Procedural creature skeletons use identity rest orientations. Skinning and
  deformation are fine, but retargeting *from* them into a production rig
  needs a rest-pose match (the retarget module does this).
* The biped rig has no procedural walk; animate it with APEX controls or
  retarget a clip onto it.
* Tank treads follow the rest loop plus ground conformance on the bottom run;
  per-road-wheel suspension deformation of the track is not modelled yet.
* Next: an APEX control rig per creature (Autorig components mapped to our
  chains), a PySide Rig Wizard panel, and H22 rig-template / Rig Transfer
  integration once node names are verified.
