# H22-Plugins-Keay

Houdini plugins by Keay.

* **[ApexKinefxStudio](ApexKinefxStudio/README.md)**: procedural rigging,
  retargeting (Mixamo / Cascadeur / UE5 → any rig), creatures (snake, insect,
  spider, quadruped, bird, jellyfish), vehicles on curves and terrain (car,
  bike, tank), secondary dynamics and crowds, built on KineFX and APEX.
* [docs/DESIGN.md](docs/DESIGN.md): the original design brainstorm.

Run the tests (no Houdini needed):

```bash
cd ApexKinefxStudio && python3 -m unittest discover -s tests -t .
```
