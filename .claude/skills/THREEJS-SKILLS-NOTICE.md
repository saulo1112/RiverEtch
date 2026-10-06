# Vendored three.js skills

The `threejs-*` skill folders in this directory are third-party content, vendored so Claude Code loads
them automatically when working on the 3D hero in `web/`.

- **Source:** https://github.com/cloudai-x/threejs-skills (`skills/<name>/SKILL.md`)
- **Commit:** `b1c623076c661fc9b03dac19292e825a5d106823` (fetched 2026-10-06)
- **License:** the upstream repository has no LICENSE file. Its README states, under "License":
  "MIT License - Feel free to use, modify, and distribute." No copyright holder is named.
- **Local changes:** none to the content. The files were only reformatted by Prettier, because this
  repository's CI checks the formatting of every Markdown file.

## Known errata for three r186

These were checked against the `three@0.186.1` npm package. Upstream claims an audit against r160+,
so prefer the notes below where they disagree.

- **Time:** `THREE.Clock` is deprecated since r183. Use `THREE.Timer`: call `timer.update(now)` once per
  frame, then `getDelta()` and `getElapsed()`. `timer.connect(document)` pauses it in hidden tabs.
  Do not mix `getDelta()` and `getElapsedTime()` in one frame, and clamp `dt` before integrating springs.
- **Shadows:** `PCFSoftShadowMap` was removed in r186; three falls back to `PCFShadowMap` with a warning.
- **Math:** `MathUtils.smoothstep(x, min, max)` takes `x` first, unlike GLSL `smoothstep(e0, e1, x)`.
- **Color management:** hex and CSS colors are sRGB and are converted to the linear working space, so
  `Color` uniforms are linear. Non-color data maps (normal, roughness, metalness, masks) stay at
  `NoColorSpace`, not `LinearSRGBColorSpace`.
- **Geometry:**
  - `BufferGeometryUtils.computeTangents` does not exist; use `geometry.computeTangents()` (tangents
    are not needed for `normalMap` anyway).
  - `CapsuleGeometry` is `(radius, height, capSegments, radialSegments, heightSegments)`.
  - WebGL lines are always 1 px wide. Use `Line2`/`LineMaterial` or a ribbon mesh for visible widths.
  - `PointsMaterial` has one size for all points. Per-point size or brightness needs a `ShaderMaterial`.
- **Materials and textures:**
  - The second UV channel is `uv1` plus `texture.channel` (r151+), not `uv2`.
  - `RGBELoader` is deprecated since r180; use `HDRLoader`.
  - For image-based lighting without an HDR file, use
    `new PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04)`.
  - `DataTexture` defaults to `NearestFilter`, no mipmaps and `flipY = false`. Set filters and
    `generateMipmaps` explicitly when using it as a normal map.
  - A normal map has to come from a smoothed height field (finite differences or Sobel), not from
    white noise.
  - "Power-of-two only" and "disable mipmaps for NPOT" are WebGL1-era advice; three r163+ is WebGL2-only.
- **Shaders:**
  - A `ShaderMaterial` is only tone-mapped and sRGB-encoded if its fragment shader ends with
    `#include <tonemapping_fragment>` and `#include <colorspace_fragment>`. Keep the default
    `glslVersion`: `GLSL3` breaks those chunks.
  - `output_fragment` is now `opaque_fragment` and `encodings_fragment` is now `colorspace_fragment`.
    A `.replace()` on the old names silently does nothing.
  - The `extensions: { derivatives, ... }` options are obsolete; `fwidth` and friends are always
    available.
  - Fresnel: compute the normal and the view direction in the same space.
  - Vite needs `?raw` imports or inline `/* glsl */` strings for shader files.
  - Set `customProgramCacheKey` when `onBeforeCompile` output varies.
- **Post-processing:**
  - Add `OutputPass` as soon as any pass follows `RenderPass`, otherwise tone mapping and sRGB output
    are lost. FXAA/SMAA go after `OutputPass`.
  - Passing a smaller resolution to `UnrealBloomPass` does nothing, because `EffectComposer.addPass`
    resizes it. Wrap its `setSize` to downscale.
  - The "Selective Bloom" example overwrites its own bloom.
  - `FilmPass` is `(intensity, grayscale)` and `SMAAPass` takes no arguments.
  - The WebGPU section is outdated: `PostProcessing` was renamed `RenderPipeline` in r183.
- **Interaction:**
  - `scene.add(transformControls)` throws since r169; add `transformControls.getHelper()` instead.
  - `Face3` is gone.
  - Remove listeners with an `AbortController` and call `controls.dispose()` in React effects.
  - Never call `preventDefault()` on touch events in a scrolling page.
- **Lighting:** physically based light units have been the default since r155 (`useLegacyLights` was
  removed in r165), so older example intensities look much darker. `ContactShadows` is not part of
  three (it comes from drei).
- **README:** the upstream README says the skills live in `.claude/skills/` and its clone command
  points at a different repository. In upstream the files are in `skills/<name>/SKILL.md`.
