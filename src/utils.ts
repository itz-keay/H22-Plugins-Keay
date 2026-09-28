/** Prefix a site-relative path with the deploy base (e.g. /portfolio/). */
export function url(path = ''): string {
  if (/^[a-z]+:/i.test(path)) return path;
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');
  return `${base}/${path.replace(/^\//, '')}`;
}

export function formatDate(date: Date): string {
  return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}
