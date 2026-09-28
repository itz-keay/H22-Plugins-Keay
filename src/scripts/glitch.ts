const GLYPHS = '▓▒░█▚▞<>/\\|#@$%&*?!01¥§∆≠';
const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEXTAREA', 'INPUT']);

let running = false;

const rand = (min: number, max: number) => Math.random() * (max - min) + min;
const pick = <T>(list: readonly T[]) => list[Math.floor(Math.random() * list.length)];

function collectText(root: Node): Text[] {
  const nodes: Text[] = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!parent || SKIP.has(parent.tagName) || parent.closest('.glitch-btn')) return NodeFilter.FILTER_REJECT;
      return node.nodeValue?.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    },
  });
  while (walker.nextNode()) nodes.push(walker.currentNode as Text);
  return nodes;
}

function scramble(original: string, amount: number): string {
  let out = '';
  for (const ch of original) out += ch !== ' ' && Math.random() < amount ? pick([...GLYPHS]) : ch;
  return out;
}

const FILTERS = [
  'invert(1)',
  'invert(1) hue-rotate(180deg)',
  'hue-rotate(90deg) saturate(6)',
  'contrast(3) brightness(1.4)',
  'grayscale(1) contrast(4)',
  'blur(2px) saturate(8)',
] as const;

/** Wreck the page for `duration` ms, then restore everything. */
export function glitch(duration = 2000) {
  if (running) return;
  running = true;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const html = document.documentElement;

  const texts = collectText(document.body);
  const originals = new Map(texts.map((t) => [t, t.nodeValue ?? '']));

  const layer = document.createElement('div');
  layer.className = 'glitch-layer';
  layer.setAttribute('aria-hidden', 'true');
  const bars = Array.from({ length: reduced ? 0 : 14 }, () => layer.appendChild(document.createElement('i')));
  document.body.appendChild(layer);
  html.classList.add('glitching');

  const start = performance.now();
  const tick = () => {
    const t = (performance.now() - start) / duration;
    // Build up, peak, then settle back down.
    const intensity = Math.sin(Math.min(t, 1) * Math.PI);
    html.style.setProperty('--gx', `${rand(-12, 12) * intensity}px`);
    html.style.setProperty('--gs', `${rand(-4, 4) * intensity}deg`);
    html.style.setProperty('--gh', `${rand(0, 360)}deg`);

    for (const bar of bars) {
      const show = Math.random() < 0.35 + intensity * 0.5;
      bar.style.display = show ? 'block' : 'none';
      if (!show) continue;
      bar.style.top = `${rand(-5, 100)}%`;
      bar.style.height = `${rand(0.4, 14) * (0.4 + intensity)}vh`;
      bar.style.left = `${rand(-20, 10)}%`;
      bar.style.width = `${rand(40, 130)}%`;
      bar.style.backdropFilter = pick(FILTERS);
      bar.style.setProperty('-webkit-backdrop-filter', bar.style.backdropFilter);
      bar.style.transform = `translateX(${rand(-40, 40)}px)`;
      bar.style.background = Math.random() < 0.25 ? pick(['rgba(255,107,44,.35)', 'rgba(0,229,255,.25)', 'rgba(255,255,255,.12)']) : 'transparent';
    }

    for (const [node, text] of originals) {
      if (Math.random() < 0.55) node.nodeValue = scramble(text, 0.12 + intensity * 0.45);
    }
  };

  tick();
  const timer = window.setInterval(tick, reduced ? 250 : 70);

  window.setTimeout(() => {
    window.clearInterval(timer);
    for (const [node, text] of originals) node.nodeValue = text;
    layer.remove();
    html.classList.remove('glitching');
    for (const p of ['--gx', '--gs', '--gh']) html.style.removeProperty(p);
    running = false;
  }, duration);
}
