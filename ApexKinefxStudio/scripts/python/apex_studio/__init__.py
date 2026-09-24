"""ApexKinefxStudio - procedural rigging, retargeting and crowd tools for Houdini.

Modules
-------
retarget          Universal retargeting (Mixamo / Cascadeur / UE5 / custom -> any rig)
rigging.bipeds    Humanoid autorig (canonical skeleton, skinning, APEX character)
rigging.creatures Snake, insect/spider, quadruped, bird, jellyfish
rigging.vehicles  Car / truck / bike / tank on curves and terrain
dynamics          Spring chains, jiggle, vibration, velocity drag
crowd             Agents, stadium crowds, SOP state machine crowds, DOP crowds
hda               Convert built networks into digital assets
validate          Environment report
core              Pure-Python math and data (no ``hou``; unit tested)

Quick start (Houdini Python Shell)::

    import apex_studio as aks
    aks.rigging.vehicles.build_vehicle(vehicle_type="car")
    aks.rigging.creatures.build_snake()
    aks.retarget.build_retarget("/path/mixamo_run.fbx", "/path/my_character.fbx")
"""

__version__ = "0.1.0"

from . import compat, core  # noqa: F401  (always importable)

if compat.HOU_AVAILABLE:  # pragma: no cover - Houdini only
    from . import crowd, dynamics, hda, network, retarget, validate  # noqa: F401
    from . import rigging  # noqa: F401
    from .rigging import bipeds, creatures, vehicles  # noqa: F401
