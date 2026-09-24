"""Skeleton naming profiles and automatic joint mapping.

Every supported source/target rig is described by a *profile*: a mapping from
the studio's canonical joint names to that rig's joint names. Retargeting maps
source -> canonical -> target, so N profiles give N*N combinations for free.

Canonical names use ``<side>_<part>`` with ``l``/``r`` sides and no prefix.

Profiles for Mixamo and UE5 Mannequin follow the published naming. Cascadeur
exports the rig you built in it: its default humanoid template uses UE-style
names (``pelvis``, ``spine_01``, ``upperarm_l``...), which is what the
``cascadeur`` profile assumes. For anything else, :func:`auto_map` does fuzzy
matching, and users can save their own JSON profiles (:func:`load_profile_json`).
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Canonical skeleton (parent relationships are used for guide generation and
# for chain-aware mapping)
# ---------------------------------------------------------------------------

CANONICAL_PARENTS: Dict[str, Optional[str]] = {
    "root": None,
    "hips": "root",
    "spine_01": "hips",
    "spine_02": "spine_01",
    "spine_03": "spine_02",
    "neck": "spine_03",
    "head": "neck",
    "head_end": "head",
}
for _s in ("l", "r"):
    CANONICAL_PARENTS.update({
        f"{_s}_clavicle": "spine_03",
        f"{_s}_upperarm": f"{_s}_clavicle",
        f"{_s}_forearm": f"{_s}_upperarm",
        f"{_s}_hand": f"{_s}_forearm",
        f"{_s}_thigh": "hips",
        f"{_s}_shin": f"{_s}_thigh",
        f"{_s}_foot": f"{_s}_shin",
        f"{_s}_toe": f"{_s}_foot",
        f"{_s}_toe_end": f"{_s}_toe",
    })
    for _f in ("thumb", "index", "middle", "ring", "pinky"):
        CANONICAL_PARENTS[f"{_s}_{_f}_01"] = f"{_s}_hand"
        CANONICAL_PARENTS[f"{_s}_{_f}_02"] = f"{_s}_{_f}_01"
        CANONICAL_PARENTS[f"{_s}_{_f}_03"] = f"{_s}_{_f}_02"

CANONICAL_JOINTS: List[str] = list(CANONICAL_PARENTS)

#: Joints that must be mapped for a usable humanoid retarget.
CORE_JOINTS = [
    "hips", "spine_01", "neck", "head",
    "l_upperarm", "l_forearm", "l_hand", "r_upperarm", "r_forearm", "r_hand",
    "l_thigh", "l_shin", "l_foot", "r_thigh", "r_shin", "r_foot",
]


def _side_map(template: Dict[str, str]) -> Dict[str, str]:
    """Expand ``{side}``/``{Side}``/``{S}`` placeholders into left and right entries."""
    out: Dict[str, str] = {}
    for canon, name in template.items():
        if "{" not in canon:
            out[canon] = name
            continue
        for s, side, cap, letter in (("l", "left", "Left", "L"), ("r", "right", "Right", "R")):
            out[canon.format(s=s)] = name.format(side=side, Side=cap, S=letter, s=s)
    return out


_FINGERS = ("thumb", "index", "middle", "ring", "pinky")

_MIXAMO = {
    "hips": "Hips", "spine_01": "Spine", "spine_02": "Spine1", "spine_03": "Spine2",
    "neck": "Neck", "head": "Head", "head_end": "HeadTop_End",
    "{s}_clavicle": "{Side}Shoulder", "{s}_upperarm": "{Side}Arm",
    "{s}_forearm": "{Side}ForeArm", "{s}_hand": "{Side}Hand",
    "{s}_thigh": "{Side}UpLeg", "{s}_shin": "{Side}Leg", "{s}_foot": "{Side}Foot",
    "{s}_toe": "{Side}ToeBase", "{s}_toe_end": "{Side}Toe_End",
}
for _f in _FINGERS:
    for _i in (1, 2, 3):
        _MIXAMO[f"{{s}}_{_f}_0{_i}"] = f"{{Side}}Hand{_f.capitalize()}{_i}"

_UE5 = {
    "root": "root", "hips": "pelvis", "spine_01": "spine_01", "spine_02": "spine_03",
    "spine_03": "spine_05", "neck": "neck_01", "head": "head",
    "{s}_clavicle": "clavicle_{s}", "{s}_upperarm": "upperarm_{s}",
    "{s}_forearm": "lowerarm_{s}", "{s}_hand": "hand_{s}",
    "{s}_thigh": "thigh_{s}", "{s}_shin": "calf_{s}", "{s}_foot": "foot_{s}",
    "{s}_toe": "ball_{s}",
}
for _f in _FINGERS:
    for _i in (1, 2, 3):
        _UE5[f"{{s}}_{_f}_0{_i}"] = f"{_f}_0{_i}_{{s}}"

# Cascadeur default humanoid (UE4-style: 3 spine joints).
_CASCADEUR = dict(_UE5)
_CASCADEUR.update({"spine_02": "spine_02", "spine_03": "spine_03"})

# Houdini's KineFX/APEX test characters (Electra/Otto) use lowercase with
# side suffixes; H22's biped recipe normalises to a similar layout.
_HOUDINI = {
    "root": "root", "hips": "hips", "spine_01": "spine_01", "spine_02": "spine_02",
    "spine_03": "spine_03", "neck": "neck", "head": "head",
    "{s}_clavicle": "{s}_clavicle", "{s}_upperarm": "{s}_upperarm",
    "{s}_forearm": "{s}_forearm", "{s}_hand": "{s}_hand",
    "{s}_thigh": "{s}_thigh", "{s}_shin": "{s}_shin", "{s}_foot": "{s}_foot",
    "{s}_toe": "{s}_toe",
}

# Rigify (Blender) deform bones.
_RIGIFY = {
    "hips": "DEF-spine", "spine_01": "DEF-spine.001", "spine_02": "DEF-spine.002",
    "spine_03": "DEF-spine.003", "neck": "DEF-spine.004", "head": "DEF-spine.006",
    "{s}_clavicle": "DEF-shoulder.{S}", "{s}_upperarm": "DEF-upper_arm.{S}",
    "{s}_forearm": "DEF-forearm.{S}", "{s}_hand": "DEF-hand.{S}",
    "{s}_thigh": "DEF-thigh.{S}", "{s}_shin": "DEF-shin.{S}", "{s}_foot": "DEF-foot.{S}",
    "{s}_toe": "DEF-toe.{S}",
}

PROFILES: Dict[str, Dict[str, str]] = {
    "mixamo": _side_map(_MIXAMO),
    "ue5": _side_map(_UE5),
    "cascadeur": _side_map(_CASCADEUR),
    "houdini": _side_map(_HOUDINI),
    "rigify": _side_map(_RIGIFY),
}

#: Prefixes stripped before matching (namespaces from FBX exporters).
_PREFIX_RE = re.compile(r"^(?:[\w]+[:|])+")


# ---------------------------------------------------------------------------
# Normalisation and matching
# ---------------------------------------------------------------------------

def strip_namespace(name: str) -> str:
    """``mixamorig:LeftArm`` -> ``LeftArm``; ``Armature|Hips`` -> ``Hips``."""
    return _PREFIX_RE.sub("", name)


def normalise(name: str) -> str:
    """Lowercase, strip namespace and separators: ``mixamorig:Left_Arm`` -> ``leftarm``."""
    return re.sub(r"[^a-z0-9]", "", strip_namespace(name).lower())


_SIDE_PATTERNS = [
    (re.compile(r"(^|[^a-z])(left|l)([^a-z]|$)"), "l"),
    (re.compile(r"(^|[^a-z])(right|r)([^a-z]|$)"), "r"),
    (re.compile(r"^left"), "l"),
    (re.compile(r"^right"), "r"),
    (re.compile(r"left"), "l"),
    (re.compile(r"right"), "r"),
]


def detect_side(name: str) -> Optional[str]:
    """Return 'l', 'r' or None for a joint name in any common convention."""
    n = strip_namespace(name)
    # CamelCase / suffix conventions: LeftArm, arm_L, arm.L, L_arm
    low = re.sub(r"([a-z])([A-Z])", r"\1_\2", n).lower()
    low = low.replace(".", "_").replace("-", "_").replace(" ", "_")
    for pattern, side in _SIDE_PATTERNS:
        if pattern.search(low):
            return side
    return None


def detect_profile(joint_names: Iterable[str]) -> Tuple[Optional[str], float]:
    """Return (profile_name, score in 0..1) for the best matching known profile.

    Score = fraction of the profile's core joints present in ``joint_names``.
    """
    present = {normalise(n) for n in joint_names}
    best, best_score = None, 0.0
    for pname, mapping in PROFILES.items():
        core = [mapping[c] for c in CORE_JOINTS if c in mapping]
        hits = sum(1 for n in core if normalise(n) in present)
        score = hits / float(len(core)) if core else 0.0
        if score > best_score:
            best, best_score = pname, score
    return best, best_score


# Keywords for fuzzy canonical classification (order matters: more specific first).
_KEYWORDS: List[Tuple[str, Sequence[str]]] = [
    ("head_end", ("headtop", "headend", "head_end", "headnub")),
    ("head", ("head",)),
    ("neck", ("neck",)),
    ("toe_end", ("toeend", "toe_end", "toenub", "toetip")),
    ("toe", ("toebase", "toe", "ball")),
    ("foot", ("foot", "ankle")),
    ("thigh", ("upleg", "thigh", "upperleg", "hip")),
    ("shin", ("shin", "calf", "knee", "lowerleg", "leg")),
    ("hand", ("hand", "wrist")),
    ("forearm", ("forearm", "lowerarm", "elbow")),
    ("upperarm", ("upperarm", "uparm", "arm")),
    ("clavicle", ("clavicle", "shoulder", "collar")),
]


def classify(name: str) -> Optional[str]:
    """Best-effort canonical name for an arbitrary joint name (no profile).

    Fingers and spine indices are handled; unknown joints return None.
    """
    n = normalise(name)
    side = detect_side(name)
    for finger in _FINGERS:
        if finger in n and side:
            digits = re.findall(r"\d+", n)
            idx = int(digits[-1]) if digits else 1
            idx = max(1, min(3, idx if idx > 0 else 1))
            return f"{side}_{finger}_0{idx}"
    if any(k in n for k in ("pelvis", "hips")) or n in ("hip", "cog"):
        return "hips"
    if "spine" in n or "chest" in n:
        if "upperchest" in n:
            return "spine_03"
        raw = strip_namespace(name).lower()
        sep = re.search(r"(?:spine|chest)[_.\- ]0*(\d+)", raw)
        if sep:  # "spine_01", "spine.002": 1-based
            return f"spine_0{max(1, min(3, int(sep.group(1))))}"
        digits = re.findall(r"\d+", n)
        if "chest" in n and not digits:
            return "spine_03"
        idx = int(digits[-1]) if digits else 0  # Mixamo style: Spine, Spine1, Spine2
        return f"spine_0{min(3, idx + 1)}"
    if n == "root":
        return "root"
    for canon, keys in _KEYWORDS:
        if any(k in n for k in keys):
            if canon in ("head", "head_end", "neck"):
                return canon
            if side is None:
                return None
            return f"{side}_{canon}"
    return None


def to_canonical(joint_names: Sequence[str], profile: Optional[str] = None) -> Dict[str, str]:
    """Map rig joint names -> canonical names.

    Uses the profile when given (exact match after normalisation), then falls
    back to :func:`classify` for anything left. Each canonical name is used
    at most once (first come, in the given order).
    """
    result: Dict[str, str] = {}
    used: set = set()
    if profile:
        inverse = {normalise(v): k for k, v in PROFILES[profile].items()}
        for name in joint_names:
            canon = inverse.get(normalise(name))
            if canon and canon not in used:
                result[name] = canon
                used.add(canon)
    for name in joint_names:
        if name in result:
            continue
        canon = classify(name)
        if canon and canon not in used:
            result[name] = canon
            used.add(canon)
    return result


def auto_map(source_names: Sequence[str], target_names: Sequence[str],
             source_profile: Optional[str] = None,
             target_profile: Optional[str] = None,
             fuzzy_threshold: float = 0.82) -> Dict[str, str]:
    """Return a ``{target_joint: source_joint}`` map.

    Both sides go through canonical names; any remaining target joints are
    matched by string similarity of their normalised names (same side only).
    Profiles are auto-detected when not given and the detection score >= 0.6.
    """
    if source_profile is None:
        p, s = detect_profile(source_names)
        source_profile = p if s >= 0.6 else None
    if target_profile is None:
        p, s = detect_profile(target_names)
        target_profile = p if s >= 0.6 else None

    src_c = to_canonical(source_names, source_profile)
    tgt_c = to_canonical(target_names, target_profile)
    canon_to_src = {c: s for s, c in src_c.items()}

    mapping: Dict[str, str] = {}
    for tgt, canon in tgt_c.items():
        if canon in canon_to_src:
            mapping[tgt] = canon_to_src[canon]

    used_src = set(mapping.values())
    for tgt in target_names:
        if tgt in mapping:
            continue
        tn, tside = normalise(tgt), detect_side(tgt)
        best, best_ratio = None, 0.0
        for src in source_names:
            if src in used_src or detect_side(src) != tside:
                continue
            ratio = SequenceMatcher(None, tn, normalise(src)).ratio()
            if ratio > best_ratio:
                best, best_ratio = src, ratio
        if best is not None and best_ratio >= fuzzy_threshold:
            mapping[tgt] = best
            used_src.add(best)
    return mapping


def missing_core(mapping: Dict[str, str], target_names: Sequence[str],
                 target_profile: Optional[str] = None) -> List[str]:
    """Canonical core joints that ended up unmapped (for validation UIs)."""
    if target_profile is None:
        p, score = detect_profile(target_names)
        target_profile = p if score >= 0.6 else None
    tgt_c = to_canonical(target_names, target_profile)
    mapped_canon = {tgt_c[t] for t in mapping if t in tgt_c}
    return [c for c in CORE_JOINTS if c not in mapped_canon]


def load_profile_json(path: str, name: Optional[str] = None) -> str:
    """Register a user profile from JSON ``{"canonical": "rig_name", ...}``."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    pname = name or data.pop("_name", None) or path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    PROFILES[pname] = {k: v for k, v in data.items() if not k.startswith("_")}
    return pname


def save_mapping_json(mapping: Dict[str, str], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(mapping, fh, indent=2, sort_keys=True)
