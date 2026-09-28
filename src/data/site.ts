// ✏️  Edit this file to update your details everywhere on the site.
// Case studies live in src/content/work/, tips in src/content/tips/.

export const site = {
  name: 'Keay',
  role: 'Designer',
  location: 'Based anywhere, working worldwide',
  email: 'hello@keay.design',
  availability: 'Available for new projects',
  intro:
    'I design brands, interfaces and the small details in between: clear systems, bold type, and interactions that feel good to use.',
  // Paste a free Formspree endpoint (https://formspree.io) to enable the contact form.
  // Leave empty and the form opens the visitor's email app instead.
  formEndpoint: '',
  // Put a file in static/ (e.g. static/keay.jpg) and set its name here.
  portrait: '',
  resume: '',
  socials: [
    { label: 'Dribbble', url: 'https://dribbble.com/' },
    { label: 'Behance', url: 'https://www.behance.net/' },
    { label: 'Instagram', url: 'https://www.instagram.com/' },
    { label: 'LinkedIn', url: 'https://www.linkedin.com/' },
  ],
  services: [
    { title: 'Brand identity', text: 'Logos, type systems, color and guidelines that scale from favicon to billboard.' },
    { title: 'UI / UX design', text: 'Web and app interfaces, from first wireframe to polished, hand-off-ready screens.' },
    { title: 'Design systems', text: 'Components, tokens and documentation that keep teams fast and consistent.' },
    { title: 'Motion & 3D', text: 'Micro-interactions, product animations and playful visuals that add personality.' },
  ],
  about: [
    "I'm Keay, a multidisciplinary designer who likes to make complex things feel simple.",
    'For the past few years I have worked with startups, studios and independent makers, shaping everything from brand identities to full product experiences. I care about craft, clear thinking and a little bit of play.',
    'When I am not pushing pixels I am collecting type specimens, taking film photos, and breaking my own designs to see what happens.',
  ],
  experience: [
    { period: '2024 — Now', title: 'Independent Designer', org: 'Freelance' },
    { period: '2022 — 2024', title: 'Product Designer', org: 'Studio Name' },
    { period: '2020 — 2022', title: 'Junior Designer', org: 'Agency Name' },
  ],
  clients: ['Northwind', 'Lumen', 'Parcel', 'Orbit Labs', 'Fieldnote', 'Kiln'],
  tools: [
    {
      group: 'Design',
      items: [
        { name: 'Figma', note: 'Everything from sketches to design systems.' },
        { name: 'Adobe Illustrator', note: 'Logos, icons and vector work.' },
        { name: 'Photoshop', note: 'Retouching, textures and mockups.' },
      ],
    },
    {
      group: 'Motion & 3D',
      items: [
        { name: 'After Effects', note: 'Product animation and motion identity.' },
        { name: 'Spline', note: 'Quick, interactive 3D for the web.' },
        { name: 'Rive', note: 'Interactive UI animations that ship.' },
      ],
    },
    {
      group: 'Workflow',
      items: [
        { name: 'Notion', note: 'Briefs, research and project notes.' },
        { name: 'Raycast', note: 'Launcher, snippets and color picker.' },
        { name: 'Framer', note: 'High-fidelity prototypes and landing pages.' },
      ],
    },
  ],
};
