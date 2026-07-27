# CNN — Theme & Color Foundations

> Extracted from the live homepage (`edition.cnn.com` / `www.cnn.com`) on 2026-07-24.
> CNN ships a Style-Dictionary–style token pipeline with three layers:
> **Primitive → Semantic → Theme/Component**. Colors below are the raw primitive
> values; everything else in the UI is expressed as a `var()` reference into these.

---

## 1. Brand palette

The identity is built on the classic **CNN red** (`#cc0000`) plus a set of
section-brand accents used to color-code verticals.

| Token | Value | Role |
|-------|-------|------|
| `--primitive-color-brand-primary`     | `#cc0000` | Core CNN red — logo, primary CTAs, accents |
| `--primitive-color-brand-secondary`   | `#ff3f3f` | Brighter red — hovers / inverse surfaces |
| `--primitive-color-brand-tertiary`    | `#a4001e` | Deep red — pressed / gradients |
| `--primitive-color-brand-politics`    | `#3061f3` | Politics vertical |
| `--primitive-color-brand-business`    | `#66c9af` | Business vertical |
| `--primitive-color-brand-travel`      | `#f06c00` | Travel vertical |
| `--primitive-color-brand-underscored` | `#6a29d5` | "CNN Underscored" commerce brand |

---

## 2. Neutral scale

The workhorse of the whole UI. Text, backgrounds, borders and icons are almost
entirely neutrals — color is reserved for the red accent and section tags.

| Token | Value | Typical use |
|-------|-------|-------------|
| `--primitive-color-neutral-100` | `#ffffff` | Page background (light) |
| `--primitive-color-neutral-200` | `#f8f8f8` | Secondary background / cards |
| `--primitive-color-neutral-300` | `#e6e6e6` | Dividers, tertiary background |
| `--primitive-color-neutral-400` | `#b1b1b1` | Disabled, tertiary border |
| `--primitive-color-neutral-500` | `#6e6e6e` | Muted / metadata text |
| `--primitive-color-neutral-600` | `#404040` | Tertiary text/icon |
| `--primitive-color-neutral-700` | `#262626` | Secondary text/icon |
| `--primitive-color-neutral-800` | `#0c0c0c` | Primary text, inverse background |

---

## 3. Extended color ramps

Each hue ships as a 100→800 ramp (light→dark). Used for tags, data-viz,
editorial theming and status states.

| Ramp | 100 | 200 | 300 | 400 | 500 | 600 | 700 | 800 |
|------|-----|-----|-----|-----|-----|-----|-----|-----|
| **Red**    | `#ffd5d5` | `#ffaaaa` | `#ff7979` | `#ff3f3f` | `#d50000` | `#a20000` | `#720000` | `#450000` |
| **Blue**   | `#d7dbfc` | `#aeb8fa` | `#7b8ff7` | `#3061f2` | `#2152d5` | `#173da4` | `#0c266e` | `#041443` |
| **Green**  | `#c9fddd` | `#97fbc3` | `#58e59e` | `#4bc88a` | `#3da672` | `#2b7a53` | `#1b5437` | `#0b2f1d` |
| **Teal**   | `#c6fbf6` | `#92f8f0` | `#73dcd3` | `#60b9b1` | `#4d9791` | `#346a66` | `#164541` | `#0a2927` |
| **Purple** | `#e5dbf8` | `#cdb6f1` | `#b28ae0` | `#9656d1` | `#8143b8` | `#62318e` | `#462166` | `#2d1444` |
| **Pink**   | `#fed6d9` | `#fdaab2` | `#fc7989` | `#fc2f59` | `#d00f40` | `#9e092f` | `#6f041e` | `#44010f` |
| **Orange** | `#ffdbd0` | `#ffb9a1` | `#ff9360` | `#ff7c00` | `#cd6200` | `#984700` | `#612b00` | `#401a00` |
| **Yellow** | `#ffe4c3` | `#ffd088` | `#ffc248` | `#f0b100` | `#c99400` | `#9a7100` | `#6c4e00` | `#463100` |

---

## 4. Alpha (transparency) tokens

Used for scrims, overlays and hover states over imagery. Base colors are
`#0c0c0c` (black) and `#ffffff` (white) at fixed opacities.

| Opacity | Black token | White token |
|---------|-------------|-------------|
| 5%  | `#0c0c0c1a` | `#ffffff1a` |
| 20% | `#0c0c0c33` | `#ffffff33` |
| 40% | `#0c0c0c66` | `#ffffff66` |
| 50% | `#0c0c0c80` | `#ffffff80` |
| 60% | `#0c0c0c99` | `#ffffff99` |
| 80% | `#0c0c0ccc` | `#ffffffcc` |
| 90% | `#0c0c0ce6` | `#ffffffe6` |

---

## 5. Semantic color mapping

The UI never uses primitives directly — it references a **semantic** layer that
gives colors intent. Key mappings (light theme):

### Surfaces
| Semantic token | Resolves to | Value |
|----------------|-------------|-------|
| `bg-primary`   | `neutral-100` | `#ffffff` |
| `bg-secondary` | `neutral-200` | `#f8f8f8` |
| `bg-tertiary`  | `neutral-300` | `#e6e6e6` |
| `bg-inverse`   | `neutral-800` | `#0c0c0c` |

### Text / Icon
| Semantic token | Resolves to | Value |
|----------------|-------------|-------|
| `icon-primary` / `link-primary`   | `neutral-800` | `#0c0c0c` |
| `icon-secondary` | `neutral-700` | `#262626` |
| `icon-tertiary`  | `neutral-600` | `#404040` |
| `icon-quartenary`| `neutral-500` | `#6e6e6e` |
| `icon-inverse`   | `neutral-100` | `#ffffff` |
| `icon-accent` / `border-accent` | `red-500` | `#d50000` |

### Borders
| Semantic token | Resolves to | Value |
|----------------|-------------|-------|
| `border-primary`    | `neutral-800` | `#0c0c0c` |
| `border-secondary`  | `neutral-500` | `#6e6e6e` |
| `border-tertiary`   | `neutral-400` | `#b1b1b1` |
| `border-quartenary` | `neutral-300` | `#e6e6e6` |
| `border-quinary`    | `neutral-200` | `#f8f8f8` |

### Actions (buttons)
| Semantic token | Resolves to | Value |
|----------------|-------------|-------|
| `action-primary-bg`       | `neutral-800` | `#0c0c0c` (black button) |
| `action-primary-text`     | `neutral-100` | `#ffffff` |
| `action-conversion-bg`    | `brand-primary` | `#cc0000` (red "Subscribe" CTA) |
| `action-conversion-text`  | `neutral-100` | `#ffffff` |
| `action-conversion-inverse-bg` | `red-400` | `#ff3f3f` |

### Links (interaction states)
`link-primary` default → `neutral-800`, **hover** → `neutral-500` (`#6e6e6e`),
**press** → `neutral-600` (`#404040`), **focus** → `neutral-800`.

---

## 6. Theming model

- **Light theme is the default.** A parallel **inverse / dark** context exists
  (`bg-inverse` = `#0c0c0c`, `icon-inverse`/`link-inverse` = `#ffffff`) used for
  dark hero panels, video overlays, footers and menu drawers rather than a full
  site-wide dark mode.
- Tokens flow **primitive → semantic (`--semantic-color-*`) → theme
  (`--theme-semantic-color-*`) → component (`--theme-component-*`)**. To retheme,
  override at the semantic layer and everything downstream follows.
- Color is deliberately **restrained**: near-black text on white, red reserved
  for brand/CTA/accent, section ramps for editorial color-coding.
