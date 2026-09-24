# Houdini MCP: let Claude build and test ApexKinefxStudio in your Houdini

```
Claude (Claude Code / Claude Desktop, on your PC)
   │  MCP (stdio)
   ▼
mcp/server.py          normal Python, pip install mcp
   │  JSON over 127.0.0.1:18900
   ▼
apex_studio/bridge.py  runs INSIDE Houdini (GUI or hython)
   │  hou
   ▼
Houdini 22             builds networks, cooks them, reports errors
```

Claude must run **on the same PC as Houdini**: Claude Code in a terminal, or
Claude Desktop. A cloud session can't reach your machine.

## 1. Get the code (Windows)

```powershell
cd "C:\Users\Itz_Keay\Videos\Houdini Rig Expert"
git clone -b feature/apex-kinefx-studio https://github.com/esskayG/H22-Plugins-Keay.git
```

This creates `...\Houdini Rig Expert\H22-Plugins-Keay\ApexKinefxStudio`.

## 2. Install the package in Houdini

Copy `ApexKinefxStudio\ApexKinefxStudio.json` to
`C:\Users\Itz_Keay\Documents\houdini22.0\packages\` (create `packages` if
needed), then edit the path in it. Use forward slashes:

```json
"env": [
    { "APEX_KINEFX_STUDIO": "C:/Users/Itz_Keay/Videos/Houdini Rig Expert/H22-Plugins-Keay/ApexKinefxStudio" },
    { "APEX_KINEFX_STUDIO_LOGLEVEL": "INFO" }
],
```

Restart Houdini, then check in the Python Shell: `import apex_studio; print(apex_studio.__version__)`.

## 3. Install the MCP server's dependency

Use a regular Python 3.10+ (not Houdini's):

```powershell
py -m pip install "mcp>=1.2"
```

(`server.py` works with both MCP SDK 1.x and 2.x.)

## 4. Register it with Claude

**Claude Code** (run in the repo folder):

```powershell
claude mcp add houdini `
  -e AKS_HYTHON="C:\Program Files\Side Effects Software\Houdini 22.0.XXX\bin\hython.exe" `
  -- py "C:\Users\Itz_Keay\Videos\Houdini Rig Expert\H22-Plugins-Keay\ApexKinefxStudio\mcp\server.py"
```

Replace `22.0.XXX` with your installed build. `AKS_HYTHON` is optional; it
lets Claude start a headless Houdini by itself.

**Claude Desktop**: edit `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "houdini": {
      "command": "py",
      "args": ["C:\\Users\\Itz_Keay\\Videos\\Houdini Rig Expert\\H22-Plugins-Keay\\ApexKinefxStudio\\mcp\\server.py"],
      "env": { "AKS_HYTHON": "C:\\Program Files\\Side Effects Software\\Houdini 22.0.XXX\\bin\\hython.exe" }
    }
  }
}
```

## 5. Start the bridge

Pick one:

* **Houdini GUI** (you can watch the networks appear): ApexKinefxStudio shelf
  → **Start MCP Bridge**, or in the Python Shell:
  `import apex_studio.bridge as b; b.start()`
* **Headless**: ask Claude to call `launch_houdini_bridge`, or run
  `hython mcp\start_bridge_hython.py` yourself.

## 6. Test

Ask Claude something like:

> Use the houdini MCP: check houdini_status, run run_selftest, then fix every
> error it reports in the package files, reload_package, and rerun until it passes.

| Tool | What it does |
|---|---|
| `houdini_status` | Houdini version, scene, package version/root |
| `launch_houdini_bridge` | Starts headless hython with the bridge |
| `run_selftest` | Builds every tool (terrain + curves included), cooks frames 1/12/24/48 and reports build exceptions, node errors/warnings (including VEX compile errors), unresolved native parms, joint counts, NaNs and "does it move" checks |
| `build_tool` | Builds one tool with options and checks it |
| `check_network` | Cooks an existing container and reports problems |
| `node_info` | Errors, parms, VEX snippet and geometry summary of a node |
| `set_parm` | Changes a parameter or expression |
| `run_houdini_python` | Runs Python in Houdini (`result = ...` is returned) |
| `reload_package` | Re-imports apex_studio after editing files, no restart |
| `probe_node_types` | Lists this build's KineFX/APEX/crowd nodes and how the package resolved them |
| `clean_test_scene` / `save_hip` | Tidy up / save the scene to inspect by hand |
| `run_unit_tests` | Runs the pure-Python tests |

Retarget and crowd cases need FBX files: pass `retarget_source_fbx` /
`retarget_target_fbx` (e.g. a Mixamo clip and your character) and `agent_fbx`
to `run_selftest`.

## Without MCP

The same test runs headless and writes a JSON report plus a `.hip` to inspect:

```powershell
& "C:\Program Files\Side Effects Software\Houdini 22.0.XXX\bin\hython.exe" `
  mcp\selftest_hython.py report.json --hip selftest.hip
```

## Security

The bridge only listens on 127.0.0.1, but `run_houdini_python` executes any
code inside Houdini. To require a shared secret, set the same
`AKS_BRIDGE_TOKEN` for Houdini and for the MCP server (for example with
`-e AKS_BRIDGE_TOKEN=...` in `claude mcp add`). Don't forward port 18900.
