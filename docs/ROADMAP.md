# HBLink (B2H / H2B) — Commercial Release Roadmap

Target: sell a **Studio** and an **Indie** edition of the Houdini ⇄ Blender bridge on Blender Market (now Superhive).
Rule for every item: **one change → test → sign-off → next change.** Nothing is marked done without a test result.

Status legend: `[ ]` todo · `[~]` in progress · `[x]` done + tested · `(?)` hypothesis, must be verified before fixing

---

## Phase 0 — Groundwork (do first, blocks everything)

### 0.1 Repository / folder structure
The original plugin is **never edited**. Studio is derived from it; Indie is derived from Studio later, only on the owner's command.

```
original/        # untouched reference copy of the full HBLink plugin (read-only)
studio/          # commercial edition — all work in Phases 1–4 happens here
indie/           # created later from studio/ on owner's command
shared/tests/    # test scenes, checklists, results log
docs/            # this roadmap, user docs, changelog
```
- [ ] Add the current full plugin source under `original/` (repo currently only has a LICENSE).
- [ ] Copy to `studio/`.

### 0.2 Licensing & ownership (decide before writing code)
- [ ] **Repo LICENSE is currently Apache-2.0 (open source).** This contradicts "not open source". Replace with a proprietary license for `studio/` and `indie/`.
- [ ] **Blender GPL constraint:** any Blender add-on that imports `bpy` must be GPL-compatible — Blender Market sells GPL add-ons. The Blender-side code *cannot* be legally closed. The Houdini-side code (HDAs/Python) is not bound by Blender's GPL. → Put protection/licensing value on the Houdini side and in the product (support, updates), not in hiding Blender code.
- [ ] Add ownership notice in every source file header + a root `AGENTS.md` / `CLAUDE.md`:
  "Proprietary. Only the Admin (owner) may modify or release this plugin. AI assistants must not redistribute, relicense or publish this code."
  Note: this is a *notice*, not technical enforcement.
- [ ] Studio vs Indie packaging: verify Houdini licence formats (Studio → `.hda`, Indie → `.hdalc`) and what each Houdini licence type can load.

---

## Phase 1 — Scope cut (Studio copy only)

Product = **two nodes only: `B2H` and `H2B`.** Everything else is removed.

| # | Remove / change | Why |
|---|---|---|
| 1.1 | Delete all nodes except B2H and H2B | Focused product |
| 1.2 | Remove **V-Ray** entirely | Scope = Cycles ⇄ Karma only |
| 1.3 | Remove **Procedural** tab entirely | Confusing; material-bake part moves to 3.4 |

Test gate: plugin loads in Houdini + Blender with no errors, B2H and H2B basic geo round-trip still works.

---

## Phase 2 — UI clean-up (B2H node)

| # | Change | Done when |
|---|---|---|
| 2.1 | Move **Build Lights / Cameras** off the first tab to its own tab | First tab = core geo transfer only |
| 2.2 | **Output** tab: document what it does; rename/merge or remove | A new user can explain the tab from its tooltip |
| 2.3 | **Asset Library** tab: define its one purpose; simplify or remove | Same as above |
| 2.4 | **Animation & Cache** tab: compact to — Bake animation onto existing skeleton · Bake frame range · Velocity / motion blur · Play from cache | Character-export removed; tab labelled *Experimental* |
| 2.5 | Import **skeleton + rest pose** (B2H) | Rig arrives in Houdini as KineFX skeleton with rest pose |

Test gate per item.

---

## Phase 3 — Bug fixes (grouped by area)

Each item: reproduce → root-cause → fix → retest. `(?)` = my likely cause, not yet confirmed.

### 3.1 Materials / viewport
- [ ] **B2H: material not shown in viewport until reload/edit.** (?) Material network is built after geo cooks, so viewport isn't dirtied — force a recook/refresh after material creation.
- [ ] **H2B: merged Pyro + geo gets the same VDB material.** Assign materials per primitive type / `name` attribute, not per object.
- [ ] **H2B RBD: inside/outside groups lost** (needed for shading). (?) Groups not exported as face sets / material slots — convert to `shop_materialpath` or face-sets on export.

### 3.2 Velocity / motion blur
- [ ] **Curves: no velocity in Blender.**
- [ ] **Vellum: no velocity / motion blur.**
- [ ] Verify `v` → Blender velocity attribute for all types (mesh, points, curves, volumes).

### 3.3 Volumes / caches
- [ ] **Stale cache: old smoke sim still shown after replacing with candle sim.** (?) Same cache path reused and Blender keeps the loaded sequence — use unique/versioned cache paths or force reload.
- [ ] **Pyro bake not supported** — fix, or document as limitation at release.
- [ ] **Bonfire preset DOP: pyro bake + old cache keeps showing** (likely same root cause as stale cache).
- [ ] **Fireworks preset crashes** — get crash log, reproduce minimal case.
- [ ] **VDB from Polygons arrives as volume, not mesh.** (?) Expected: SDF is a volume. Offer option: send as volume, or convert to polygons (convert already works).
- [ ] **H2B cache mode slower than Houdini cache** — profile (write format, compression, per-frame overhead).

### 3.4 Skeletons / rigs
- [ ] **H2B sends skeleton as curves.** Convert KineFX skeleton → Blender Armature (+ skinned mesh).

Test gate: every bug has a saved repro scene in `shared/tests/` that passes after the fix.

---

## Phase 4 — New H2B features (after bugs are clean)

Priority order (highest artist value first):

1. [ ] **Rigged export**: armature + mesh (pairs with 3.4). Reverse direction auto-creates a Bone Deform in Houdini.
2. [ ] **Split meshes by `name` attribute** into separate Blender objects.
3. [ ] **/obj-level export**: cameras, lights, nulls.
4. [ ] **Blender-side send selection**: send individual object / light / camera or whole scene.
5. [ ] **Particle control in Blender**: scale/instance particles from attributes (`pscale`, `Cd`, etc.).
6. [ ] **Bake Houdini material → Blender** (geo only; replaces the removed Procedural tab bake).

---

## Phase 5 — Competitor research (can run in parallel with Phase 1–2)

Compare against **Blendini** and **HTB – Houdini to Blender Exporter**.

| Question | Blendini | HTB | HBLink |
|---|---|---|---|
| Transfer format / pipeline (Alembic, USD, VDB, custom?) | | | |
| Rigged character support | yes (armature + mesh) | | |
| `name`-based mesh split | yes | | |
| /obj cams, lights, nulls | yes | | |
| Particle attribute control | yes | | |
| Velocity / motion blur | | | |
| Bidirectional (B2H) | | | yes |
| Materials (Cycles ⇄ Karma) | | | yes |
| Licensing / copy protection | | | |
| Price | | | |

Output: "what we lack" list (→ Phase 4) and "what we do better" list (→ store page).
Source: Blendini intro video in folder + product pages.

---

## Phase 6 — Release testing

- [ ] Official Blender demo scenes, **realistic → stylized** (log results in `shared/tests/results.md`).
- [ ] Houdini shelf presets: Fireworks, Bonfire, Pyro, Vellum, RBD, Candle, Smoke.
- [ ] Houdini + Blender version matrix (min supported versions).
- [ ] Clean-machine install test for Studio and Indie builds.

## Phase 7 — Indie edition (only on owner's command)
- [ ] Copy `studio/` → `indie/`, apply Indie limits / `.hdalc` packaging.
- [ ] Repeat Phase 6 on Indie.

## Phase 8 — Blender Market launch
- [ ] Docs: install, quick start, known limitations (anything left from Phase 3).
- [ ] Store page: comparison vs competitors (from Phase 5), demo video.
- [ ] Versioning + changelog.

---

## Working order (one at a time)
0.1 → 0.2 → 1.1 → 1.2 → 1.3 → 2.1 … 2.5 → 3.x (by area) → 4.1 … 4.6 → 6 → 7 → 8
Phase 5 research may run alongside Phases 1–2.
