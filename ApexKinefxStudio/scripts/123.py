"""ApexKinefxStudio optional startup validation.

Houdini runs the first ``123.py`` found on HOUDINI_PATH when it starts without
a scene file. This one only does work when APEX_KINEFX_STUDIO_VALIDATE=1, so
it stays out of the way otherwise. If your studio already ships a 123.py,
delete this file (it would shadow yours, or be shadowed by it) and call
``apex_studio.validate.report()`` from your own startup script instead.
"""

import os

if os.environ.get("APEX_KINEFX_STUDIO_VALIDATE", "0") == "1":
    try:
        import apex_studio.validate

        apex_studio.validate.report(verbose=os.environ.get("APEX_KINEFX_STUDIO_LOGLEVEL") == "DEBUG")
    except Exception as exc:  # never break Houdini startup
        print(f"[ApexKinefxStudio] validation failed: {exc}")
