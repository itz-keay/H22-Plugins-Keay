---
title: Adding grain without images
summary: "A tiny SVG noise filter gives flat UI a tactile, printed feel."
date: 2026-04-20
tag: Web
---

This site's grain is not an image. It is an SVG `feTurbulence` filter used as a CSS background:

```css
body::after {
  content: '';
  position: fixed;
  inset: 0;
  pointer-events: none;
  background-image: url("data:image/svg+xml,...feTurbulence...");
  opacity: .12;
  mix-blend-mode: overlay;
}
```

Keep the opacity low. Grain should be felt, not seen.
