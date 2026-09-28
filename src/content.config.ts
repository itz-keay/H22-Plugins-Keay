import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

const work = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/work' }),
  schema: z.object({
    title: z.string(),
    client: z.string(),
    year: z.number(),
    category: z.enum(['Branding', 'UI/UX', 'Motion', 'Print']),
    summary: z.string(),
    role: z.string().optional(),
    // Image in static/, e.g. "work/lumen-cover.jpg". Without one, a generated cover is used.
    cover: z.string().optional(),
    // Cover style when there is no image: "ember" (orange) or "slate" (grey).
    tone: z.enum(['ember', 'slate', 'ash']).default('slate'),
    featured: z.boolean().default(false),
    order: z.number().default(0),
    draft: z.boolean().default(false),
  }),
});

const tips = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/tips' }),
  schema: z.object({
    title: z.string(),
    summary: z.string(),
    date: z.coerce.date(),
    tag: z.string(),
    draft: z.boolean().default(false),
  }),
});

export const collections = { work, tips };
