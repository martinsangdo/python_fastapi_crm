# CNN — Style Guide & Visual Language

> How the tokens in `01-theme.md` and `02-tokens.md` combine into CNN's
> recognizable look. Observed from `edition.cnn.com` on 2026-07-24.

---

## 1. Design principles

1. **News-first, ink-on-paper.** Near-black text (`#0c0c0c`) on white
   (`#ffffff`). The page reads like a dense, authoritative newspaper front.
2. **Red is a scalpel, not a paintbrush.** CNN red (`#cc0000`) appears only on
   the logo, "LIVE"/breaking flags, the subscribe CTA, and thin accent rules.
3. **Hierarchy through type + space, not color.** Weight, size and generous
   whitespace on an 8px grid do the ranking; most cards are monochrome.
4. **Square, editorial blocks.** Imagery and cards default to `radius-none` —
   crisp rectangles; only pills/avatars/icon-buttons go fully round.
5. **Systematic & responsive.** Every value is a token resolved through a
   primitive→semantic→theme→component pipeline, recomputed per breakpoint.

---

## 2. Color usage

| Intent | Token / value |
|--------|---------------|
| Page background | `#ffffff` (`bg-primary`) |
| Body & headline text | `#0c0c0c` (`neutral-800`) |
| Muted metadata (byline, timestamp) | `#6e6e6e` (`neutral-500`) |
| Hairline dividers | `#e6e6e6` (`neutral-300`) |
| Brand / breaking / logo | `#cc0000` (`brand-primary`) |
| Primary button | black bg `#0c0c0c`, white text |
| Conversion CTA ("Subscribe") | red bg `#cc0000`, white text |
| Dark surfaces (footer, video, menu) | `#0c0c0c` bg, white text/icons |
| Section color-coding | brand accents (politics blue, business green, travel orange) |

Link behavior: default black → **hover lightens to grey** (`#6e6e6e`) rather than
turning blue — reinforcing the monochrome editorial feel.

---

## 3. Typography in practice

- **One family does almost everything: CNN Sans Display** (Gotham-derived
  geometric sans). Fallback: `helveticaneue, Helvetica, Arial`.
- **Headlines**: CNN Sans, Bold/ExtraBold, tight line-heights. Lead story uses
  `header-h1` (42/48) down to card titles at `title-sm/md` (16–18px).
- **Condensed variant** (`cnn_sans_condensed`) for tight decks, tickers, tags.
- **Serif (Noto Serif)** reserved for some long-form article body.
- **Eyebrows / kickers**: `subtitle` role, uppercase, `1px` letter-spacing,
  small (12–14px) — often the section name above a headline.
- **Metadata** (bylines, "2 hours ago"): 12–14px, `neutral-500` grey.

Type scale is a fixed ramp — `10,12,14,16,18,20,24,30,32,36,40,42,48,56,64` —
so any custom size should snap to one of these steps.

---

## 4. Spacing & layout

- **8px base unit**, 4px half-steps. Component padding and gaps come from
  `space-04 … space-80`; vertical section rhythm is `24–48px`.
- **12-column grid**, content maxing around **1216–1376px** wide on desktop.
- Page gutters step up responsively: `20px → 32px → 48px`.
- Breakpoint ids: `xs, sm, md, lg, xl` — layouts (right-rail on/off, caption
  placement, image widths) are toggled per id rather than by ad-hoc media queries.

---

## 5. Core components

**Header / masthead**
- White bar, black icon set, red CNN logo mark.
- Hamburger "menu" opens a **dark drawer** (`bg-inverse` `#0c0c0c`, white links).
- Persistent **red "Subscribe"** conversion button; black secondary/sign-in.
- Sticky sub-nav of section links.

**Primary navigation sections**
`US · World · Politics · Business · Health · Entertainment · Style · Travel ·
Sport · Science · Climate · Weather` (plus Markets, Opinion, Video, Underscored).

**Cards (the atomic unit of the homepage)**
- Square image (`radius-none`) + headline (`title-*`) + optional kicker + byline.
- Monochrome; rank shown via size (lead card large, list cards small stacked).
- Hover lightens the headline to grey.

**Buttons**
- Primary: solid black, white text, `radius-04`, `action-*` type sizes.
- Conversion: solid red (`#cc0000`).
- Pills (topic chips, filters): `radius-round`, thin border.

**Breaking / Live**
- Red flag or dot using `brand-primary` / `red-500`, uppercase label.

**Footer**
- Full-width **dark** block (`#0c0c0c`), white link columns, multi-column
  sitemap, condensed type.

---

## 6. Motion & interaction

- Restrained, utilitarian: color/opacity transitions on hover (headline → grey,
  scrims via black/white alpha tokens over imagery).
- No decorative animation on content; the emphasis stays on speed and legibility.

---

## 7. Cheat sheet

```css
/* CNN look in a nutshell */
--bg:        #ffffff;   /* page            */
--ink:       #0c0c0c;   /* text / headlines*/
--muted:     #6e6e6e;   /* metadata        */
--rule:      #e6e6e6;   /* dividers        */
--brand:     #cc0000;   /* CNN red         */
--font:      cnn_sans_display, helveticaneue, Helvetica, Arial, sans-serif;
--radius:    0;         /* square editorial blocks */
--radius-pill: 999px;   /* chips / avatars */
--unit:      8px;       /* spacing base    */
/* Headline: CNN Sans Bold, 42/48. Body: 16/26. Kicker: 12px uppercase, +1px tracking. */
```
