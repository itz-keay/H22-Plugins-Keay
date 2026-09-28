# Keay — Designer

Portfolio website for Keay. Built with [Astro](https://astro.build): modern grey theme with an orange accent, film-grain texture, glass panels, and a small **glitch** button on the right edge that wrecks the whole page for 2 seconds (just for fun).

## Pages

| Page | Path | Content comes from |
|---|---|---|
| Home | `/` | `src/data/site.ts` + featured work + latest tips |
| Work | `/work` (filterable) and `/work/<project>` | `src/content/work/*.md` |
| Tools & Tips | `/tools` and `/tools/<tip>` | toolkit in `src/data/site.ts`, tips in `src/content/tips/*.md` |
| About me | `/about` | `src/data/site.ts` |
| Contact | `/contact` | `src/data/site.ts` |

## Editing

- **Your details** (email, bio, services, experience, clients, socials, tools): `src/data/site.ts`
- **Add a project:** copy a file in `src/content/work/` and edit it. Put images in `static/work/` and set `cover: work/my-image.jpg`. Without an image, a generated cover is used (`tone: ember | slate | ash`). Set `featured: true` to show it on the home page, and use `order` to sort.
- **Add a tip:** copy a file in `src/content/tips/`.
- **Photo / CV:** put `keay.jpg` / `cv.pdf` in `static/` and set `portrait` / `resume` in `site.ts`.
- **Contact form:** create a free form at [formspree.io](https://formspree.io) and paste its URL into `formEndpoint`. Until then, the form opens the visitor's email app.
- **Colors:** CSS variables at the top of `src/styles/global.css` (`--orange`, greys).
- **Glitch effect:** `src/scripts/glitch.ts`. It respects "reduce motion" settings with a gentler version.

Quote any front-matter text that contains a colon, e.g. `summary: "Part one: part two"`.

## Run locally

```bash
npm install
npm run dev      # http://localhost:4321
npm run build    # outputs the site to public/
```

## Deploy for free with the code kept private

**Cloudflare Pages (from a private GitHub repo):** Workers & Pages → Create → Pages → Connect to Git → pick the repo.
Build command `npm run build`, output directory `public`.

**GitLab Pages (private GitLab project):** push the code to GitLab; `.gitlab-ci.yml` builds and publishes on every push to the default branch.
Then set **Settings → General → Visibility → Pages → Everyone** so the site is public while the code stays private.
