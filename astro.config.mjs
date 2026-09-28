// @ts-check
import { defineConfig } from 'astro/config';

// GitLab CI provides CI_PAGES_URL (e.g. https://name.gitlab.io/portfolio).
// We derive `site` and `base` from it so links work on any Pages URL.
const pagesUrl = process.env.CI_PAGES_URL ? new URL(process.env.CI_PAGES_URL) : null;

export default defineConfig({
  site: pagesUrl ? pagesUrl.origin : 'http://localhost:4321',
  base: pagesUrl ? pagesUrl.pathname : '/',
  trailingSlash: 'ignore',
  // GitLab Pages serves the `public/` folder, so build into it and keep
  // static assets (images, resume PDF) in `static/` instead.
  outDir: './public',
  publicDir: './static',
});
