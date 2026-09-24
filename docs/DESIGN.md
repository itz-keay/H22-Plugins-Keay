# Keay Rig Kit — Design Brainstorm (Houdini 22, KineFX + APEX)

Status: **brainstorm / proposal** — nothing here is implemented yet.

## 1. Goal

One toolkit that makes KineFX + APEX easy for beginners but still scales up for TDs:

- **Retarget** animation from Mixamo, Cascadeur, UE Mannequin, mocap BVH and other rigs onto any Houdini character.
- **Rig** any creature with templates: human, quadruped, ant/insect, snake, bird, jellyfish/octopus, or a custom creature.
- **Rig and drive vehicles** (car, bike, tank, custom). They follow a spline path over a heightfield, with correctly rolling wheels, suspension, drift, and vibration.
- **Add secondary motion** (jiggle, overlap, tails, antennae, tentacles, loose vehicle parts) to any of the above.

Design rule: **wrap native Houdini 22 features, and don't rebuild them.** When SideFX already solves a problem, like the H22 biped recipe for Mixamo retargeting, the kit just calls it with sensible defaults. Our own code goes into the parts Houdini doesn't cover: non-biped templates, vehicles, procedural locomotion, and the beginner UX.

## 2. What Houdini already gives us (don't reinvent)

| Area | Native feature | Since |
|---|---|---|
| Skeleton / joints | KineFX SOPs: Skeleton, Rig Pose, Rig Doctor, Joint Capture Biharmonic, Joint Deform, Map Points, Rig Match Pose, Full Body IK, Motion Clip family | H18.5+ |
| Retarget (generic) | Map Points → Rig Match Pose → Full Body IK / Rig Retarget | H18.5+ |
| APEX rigging | APEX graphs, Autorig Component (3.0 in H21), Rigscript Component, Autorig Builder (drag-drop schematic, H21), fuse-graph custom components | H20 → H21 |
| APEX anim | Animate state, APEX Animation from Skeleton (retarget onto APEX character), Motion Mixer | H20.5 → H21 |
| **H22** | Reusable/adaptive **rig templates**, **Rig Transfer**, automatic **biped recipe** (Mixamo → custom: name map, rest pose, orientation), **skeleton mapping**, **rig inversion**, **Set Driven Keys** component, **APEX Rig Pose**, **character picker**, nested clips in Motion Mixer, ragdoll forces/impact thresholds | H22 |
| Secondary | KineFX Secondary Motion SOP, Vellum, Ragdoll Solver | H19+ |

> Exact H22 node type names and parameters must be verified in a live H22 session (see §9). The builder scripts should look them up at runtime and warn when one is missing, never hard-fail.

**Takeaway:** biped Mixamo→custom retargeting is basically solved in H22. What we add for bipeds is *presets + validation + cleanup* (foot lock, root motion, batch clips). The big gaps are **non-biped creatures, vehicles, procedural locomotion, and a single guided front end**.

## 3. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ L3  Rig Wizard (Python Panel / shelf)  +  optional MCP bridge│  beginner front end
├──────────────────────────────────────────────────────────────┤
│ L2  keay:: HDAs  (Retarget, Creature, Vehicle, Secondary)    │  artist-facing nodes
├──────────────────────────────────────────────────────────────┤
│ L1  Libraries: VEX (.h), Python (keayrig pkg), JSON profiles │  shared logic / data
├──────────────────────────────────────────────────────────────┤
│ L0  Native KineFX SOPs + APEX graphs/components (H22)        │  SideFX
└──────────────────────────────────────────────────────────────┘
```

### Source-first HDAs (important for git + Claude collaboration)

HDAs are opaque blobs, so git can't diff them and nobody can review them. So:

- All VEX lives in `vex/include/*.h` and snippet files.
- All APEX logic goes in Python (APEX graph API / rigscript) or `.bgeo`/`.json` graph files.
- `python/keayrig/build/*.py` **generates the HDAs** by running `hython build_hdas.py`. It creates nodes, wires them, promotes parameters, and saves `otls/*.hda`.
- Built `.hda` files are release artifacts (or checked in, but always regenerated).

This lets development happen outside Houdini, with Houdini used for build + test. Because I can't run Houdini in this environment, **you run the build and send back errors/screenshots**. A later option is an MCP bridge (e.g. houdini-mcp) so Claude can drive a live Houdini session directly.

### Houdini package layout

```
H22-Plugins-Keay/
  keay_rigkit.json            # Houdini package file (drop in $HOUDINI_USER_PREF_DIR/packages)
  otls/                       # built HDAs
  python/keayrig/             # hou-side Python: profiles, builders, wizard, utils
    profiles/                 # skeleton name maps (json)
    templates/                # creature/vehicle template definitions (json)
    build/                    # HDA builder scripts
    ui/                       # Python panel (PySide6)
  vex/include/keay_*.h        # vehicle math, gait, springs
  python_panels/ toolbar/     # panel + shelf definitions
  examples/                   # .hip scenes per module
  tests/                      # hython smoke tests (headless)
  docs/
```

## 4. Module A — Retarget ("Retarget Anything")

**HDA `keay::retarget`** — inputs: target character (skin + skeleton, or APEX character), source animation (FBX/BVH/USD skel).

Pipeline:
1. **Detect source profile.** Match joint names against `profiles/*.json` (Mixamo `mixamorig:*`, Cascadeur, UE5 Manny/Quinn, Rokoko, CMU BVH, Rigify, …). Each profile maps names → a canonical `keay` joint set (hips, spine_01…, l_upperarm…), declares the rest pose (T/A), and gives the up/forward axis and unit scale.
2. **Detect target profile** the same way, or use a guided mapping UI with fuzzy name matching and left/right symmetry inference.
3. **Route:**
   - *Biped ↔ biped* → H22 biped recipe / Rig Transfer (native).
   - *Everything else* (quadruped, partial chains, props) → Map Points → Rig Match Pose → Full Body IK retarget with per-chain weights.
4. **Cleanup stack (our value-add):**
   - Foot/hand **contact detection + locking**: velocity + height threshold, then IK pin.
   - **Root motion** options: in-place / extract to root / keep.
   - Scale compensation (stride length vs leg length ratio).
   - Finger curl preservation, spine distribution.
   - Optional APEX layer for animator tweaks on top of the retarget.
5. **Batch mode:** a folder of FBX clips → Motion Clips → Motion Mixer library.

Output: animated skeleton + deformed mesh, or an APEX character with the animation baked on controls.

## 5. Module B — Creature Rigs (templates)

**HDA `keay::creature_rig`** — choose a template → a guide skeleton is placed/fit to the mesh → APEX components are stacked → captured and deformed.

Each template = JSON describing: guide joints (relative to bounds / landmarks), APEX components to apply per chain, default controls/shapes, and secondary motion defaults.

| Template | Skeleton guides | APEX components | Special logic |
|---|---|---|---|
| Biped | H22 biped template | native autorig (limb, hand, foot, spine, neck) | reuse H22 wholesale |
| Quadruped | spine, 4 legs (digitigrade option), tail, neck | limb (3-bone + foot roll), spine, tail FK/IK | gait generator (walk/trot/gallop phase offsets) |
| Insect / ant | thorax/abdomen, 6 legs, antennae, mandibles | leg IK ×N (generic N-leg component) | **tripod gait** + terrain foot planting |
| Spider / crab | 8 / 10 legs | same N-leg component | wave / tetrapod gait |
| Snake / worm | N-joint spline chain | spline IK component | **path follow** along a curve + sinusoidal lateral undulation, sidewinder / rectilinear modes |
| Bird | biped legs + wings (humerus/ulna/hand), tail fan | limb + wing fold SDK (H22 Set Driven Keys) | flap cycle generator, feather spread driven by fold |
| Fish | spine chain, fins | spline/FK chain | swim wave (amplitude grows toward tail) |
| Jellyfish / octopus | radial bell ring + N tentacle chains | bell pulse via SDK/blendshape; tentacles FK + dynamics | pulse → thrust cycle; tentacles Vellum or spring chain |
| Custom | user-drawn guides (Skeleton SOP) | pick components per chain in Autorig Builder | "chain type" tags drive the component choice |

**Auto-fit:** start with bounds + PCA and symmetry-plane detection for the guide skeleton, then refine by hand in the Skeleton SOP. Later: landmark picking in the viewport.

**Procedural locomotion (shared VEX lib `keay_gait.h`):**
- Legs have a phase offset table per gait; each foot has a swing/stance cycle driven by distance traveled, not time, so there's no foot sliding.
- Foot targets are raycast onto the ground (heightfield or mesh). Body height and tilt come from averaging the planted feet.
- The output drives the leg IK controls in APEX, so animators can still override it.

## 6. Module C — Vehicle Rig & Driving

**HDAs:** `keay::vehicle_rig` (build) and `keay::vehicle_drive` (animate).

### 6.1 Rig build
- **Part detection.** Wheels come from name patterns (`wheel_fl`, `tire*`), connectivity + cylinder fit, or user groups. For each wheel we get center, axle axis (the fitted cylinder axis), and radius (from the fit or the bounding box).
- **Skeleton:** `root → body(chassis) → suspension_i → steer_i → wheel_i`, plus optional extra joints (doors, antenna, exhaust, turret, barrel).
- **Vehicle types:** car (4 wheels, front steer), bike (2 wheels, fork steer + lean), truck (N axles), tank (tracks + road wheels + sprockets + turret).
- **APEX controls:** path offset, speed multiplier, steer override, per-wheel suspension, and body manual offset layered on top of the procedural result.

### 6.2 Driving solver (per frame, SOP Solver + VEX, results baked into the skeleton)

Inputs: path curve, ground (heightfield or mesh), speed curve (or a keyframed `u` along the path).

1. **Position on path.** Resample the curve by arc length; `s(t)` = distance traveled (integrated speed). Chassis XZ position and heading come from the path tangent.
2. **Ground contact.** Raycast each wheel down onto the heightfield → contact height `h_i` and normal.
3. **Suspension.** Each wheel is a spring-damper: `x'' = -k(x - x_rest) - c x' + (h_i - wheel_y)`. It's integrated in the solver, so bumps give real overshoot.
4. **Chassis pitch/roll.** Fit a plane to the 4 (or N) suspension tops; body pitch/roll/height come from that plane, plus inertial terms:
   - roll from lateral acceleration `a_lat = v² · κ` (κ = path curvature),
   - pitch from longitudinal acceleration (squat on accelerate, dive on brake).
5. **Wheel spin, correctly.** Rotation `θ_i += Δd_i / r_i`, where `Δd_i` is **the distance that wheel's contact point actually traveled** (inner and outer wheels differ in turns, and reversing is handled by the signed dot with heading). No skating.
6. **Steering (Ackermann).** With wheelbase `L`, track `T`, and turn radius `R = 1/κ`: `δ_inner = atan(L / (R - T/2))`, `δ_outer = atan(L / (R + T/2))`. Look ahead along the path for smoother steering.
7. **Bike lean.** `φ = atan(v² κ / g)`, damped. The steer angle is reduced by the lean.
8. **Drift.** A slip angle `β` (user curve, or auto when `a_lat` > grip threshold) yaws the body away from the path tangent. The front wheels counter-steer by `−β·k`, the rear wheels spin faster (`θ` multiplier), and a tire-smoke/skid-mark emission attribute is exported.
9. **Vibration.** Engine idle buzz (high-frequency, low amplitude, fades out with speed) plus road noise (amplitude ∝ speed × terrain roughness sampled from heightfield gradient variance), applied to body and loose parts.
10. **Tank tracks.** Treads are instanced along a track curve built around the road wheels/sprockets. Tread offset = distance traveled per side; differential speed per side gives pivot turns. Road wheels conform to the terrain individually.

Everything is bake-able to keyframes on the APEX controls, so animators can refine the result.

### 6.3 Vehicle secondary
Antenna/exhaust/mirror spring chains, loose-panel jiggle driven by the chassis acceleration, and an optional driver character. The driver's hands are pinned to the wheel and the body sways with `a_lat`. This reuses Module D.

## 7. Module D — Secondary Motion

**HDA `keay::secondary`** — applies to any skeleton (character or vehicle):
- **Spring chain** (VEX, verlet): per-joint stiffness/damping/gravity, collisions with a proxy sphere/capsule. For tails, ears, antennae, hair clumps, straps.
- **Jiggle points** for belly, cheeks, and loose parts. This wraps the KineFX Secondary Motion SOP.
- **Dynamics hand-off:** Vellum for tentacles/cloth, and a Ragdoll blend (H22 forces/impact threshold) for hits and falls.
- **Paint weights** per region (`secondary_amount` attribute) so beginners get one intuitive slider.

## 8. Beginner UX — the "Rig Wizard"

A Python panel walking through: **1. Import → 2. What is it? (human / animal / vehicle / custom) → 3. Fit guides → 4. Build rig → 5. Animate or retarget → 6. Secondary → 7. Export (FBX / USD / bgeo).**

- Every step creates *normal, visible nodes*. The wizard is a teacher, not a black box, and each node gets a sticky note explaining what it does.
- **Validator** (Rig Doctor+): checks for missing rest pose, non-uniform scale, flipped joint orientations, unmapped joints, and unit mismatches (cm vs m from FBX), with one-click fixes.
- Presets and example `.hip` per template; H22 character picker auto-configured.
- Optional **AI helper** via an MCP bridge for commands like "retarget this Mixamo run onto my character and lock the feet".

## 9. Roadmap (proposed)

| Phase | Deliverable | Why first |
|---|---|---|
| 0 | Repo skeleton, Houdini package file, hython build + smoke-test harness; **you** run a probe script that dumps H22's actual KineFX/APEX node type names | everything depends on a verified node list |
| 1 | Retarget: profiles (Mixamo, Cascadeur, UE5), detection, routing to H22 biped recipe, foot lock + root motion | quickest real-world win |
| 2 | Vehicle rig + drive (car first: path, heightfield, wheels, Ackermann, suspension) | most custom math, least native coverage |
| 3 | Vehicle extras: drift, vibration, bike lean, tank tracks | builds on phase 2 |
| 4 | Secondary motion HDA | used by 2, 3 and 5 |
| 5 | Creature templates: snake → quadruped → insect (gait lib) → bird → jellyfish | ordered by difficulty |
| 6 | Rig Wizard panel + validator + examples | wraps it all |

## 10. Open questions

1. **License tier:** Apprentice, Indie, or FX/Core? Indie saves `.hdalc` and Apprentice `.hdanc`, and that affects the build scripts.
2. **Priority:** retargeting first, or vehicles first?
3. **Output target:** in-Houdini rendering only, or export to Unreal/Unity/Blender (FBX/USD)? This changes the bake requirements.
4. Can you run `hython` headless on your machine for build/tests, and would you want an MCP bridge so Claude can drive Houdini directly?
5. Do you have sample assets (a Mixamo FBX, a Cascadeur export, a car model) to put in `examples/` or keep private?
