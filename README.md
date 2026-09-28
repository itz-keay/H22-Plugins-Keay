# Portfolio

A personal portfolio built with [Astro](https://astro.build) and deployed free with **GitLab Pages**. The source code stays private; only the built website is public.

## Features

- Home page with hero, about, skills, featured projects, experience, education and contact
- Projects page with tag filters, plus a detail page for each project, written in Markdown
- Dark / light mode (follows the system setting, remembers the visitor's choice)
- Responsive, accessible, zero JavaScript frameworks, fast
- SEO meta and Open Graph tags, custom 404 page
- Optional CV download and profile photo
- Auto-deploys on every push to the default branch

## Make it yours

| What | Where |
|---|---|
| Name, bio, skills, experience, links | `src/data/profile.ts` |
| Projects | one `.md` file per project in `src/content/projects/` |
| Photo, CV, project images | put files in `static/` and reference them by file name |
| Colors | CSS variables at the top of `src/styles/global.css` |

Set `draft: true` in a project's front matter to hide it.

## Run locally

```bash
npm install
npm run dev      # http://localhost:4321
npm run build    # outputs to public/
```

## Deploy on GitLab Pages (private repo)

1. Create a **private** project on GitLab and push this code to it.
2. GitLab runs `.gitlab-ci.yml` automatically. Wait for the `pages` job to pass (**Build → Pipelines**).
3. Go to **Deploy → Pages** to see your site URL.
4. **Important:** In a private project, Pages is visible only to project members by default. To make the site public, go to
   **Settings → General → Visibility, project features, permissions → Pages** and choose **Everyone**. The code stays private.
5. Optional: add a custom domain under **Deploy → Pages → New domain**.

Base paths are handled automatically: the build reads GitLab's `CI_PAGES_URL`, so the site works at both `name.gitlab.io` and `name.gitlab.io/project`.
