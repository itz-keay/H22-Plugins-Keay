"""Run the full self test headless, without MCP.

    hython ApexKinefxStudio/mcp/selftest_hython.py [report.json] [--hip out.hip]
        [--src mixamo.fbx --tgt character.fbx] [--agent agent.fbx]

Prints a summary and writes the JSON report (default: aks_selftest_report.json).
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
os.environ.setdefault("APEX_KINEFX_STUDIO", ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts", "python"))

import hou  # noqa: E402

from apex_studio import selftest  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("report", nargs="?", default="aks_selftest_report.json")
ap.add_argument("--hip", default="aks_selftest.hip")
ap.add_argument("--src")
ap.add_argument("--tgt")
ap.add_argument("--agent")
ap.add_argument("--cases", nargs="*")
args = ap.parse_args()

report = selftest.run(only=args.cases, retarget_source=args.src, retarget_target=args.tgt,
                      agent_fbx=args.agent, out_path=args.report)
hou.hipFile.save(args.hip)
print(f"Houdini {report['houdini']}  {report['seconds']}s")
print(f"PASSED ({len(report['passed'])}): {', '.join(report['passed'])}")
print(f"FAILED ({len(report['failed'])}): {', '.join(report['failed'])}")
for name in report["failed"]:
    case = report["cases"][name]
    print(f"\n--- {name} ---")
    if case.get("build_exception"):
        print(case["build_exception"])
    for err in case.get("errors", [])[:10]:
        print(f"  {err.get('node')}: {' | '.join(err.get('messages', []))[:500]}")
print(f"\nReport: {os.path.abspath(args.report)}\nScene:  {os.path.abspath(args.hip)}")
sys.exit(1 if report["failed"] else 0)
