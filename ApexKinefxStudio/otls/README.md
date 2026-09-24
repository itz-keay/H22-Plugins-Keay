# otls/

Digital assets are **generated**, not hand-edited. The Python and VEX in this
package are the source of truth, which keeps everything diffable in git.

Build the library with hython (any licence that can save HDAs):

```bash
hython tools/build_hdas.py              # -> otls/apex_kinefx_studio.hda
```

Assets produced (namespace `aks`, version `1.0`):

| Asset | Tool |
|---|---|
| `aks::retarget::1.0` | FBX -> FBX retarget with an *Update Joint Mapping* button |
| `aks::snake_rig::1.0` | Snake / worm on a path over terrain |
| `aks::insect_rig::1.0`, `aks::spider_rig::1.0`, `aks::quadruped_rig::1.0` | Legged walkers |
| `aks::bird_rig::1.0`, `aks::jellyfish_rig::1.0` | Flight and pulse swimming |
| `aks::car_rig::1.0`, `aks::bike_rig::1.0`, `aks::tank_rig::1.0` | Vehicles |

Apprentice/Indie licences save `.hdanc` / `.hdalc`; pass that extension to the
build script. Houdini loads any HDA in this folder automatically because the
package adds the package root to `HOUDINI_PATH`.
