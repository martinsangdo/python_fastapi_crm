# CNN — Design Tokens

> Non-color primitives extracted from the live homepage on 2026-07-24.
> All spacing/sizing is an **8px-based scale** with 4px half-steps.
> Naming follows CNN's `--primitive-*` and `--semantic-*` conventions.

---

## 1. Spacing scale

`--primitive-space-*` — used for margin, padding and gaps.

| Token | Value | | Token | Value |
|-------|-------|-|-------|-------|
| `space-none` | `0`    | | `space-32` | `32px` |
| `space-01`   | `1px`  | | `space-36` | `36px` |
| `space-02`   | `2px`  | | `space-40` | `40px` |
| `space-04`   | `4px`  | | `space-48` | `48px` |
| `space-08`   | `8px`  | | `space-56` | `56px` |
| `space-12`   | `12px` | | `space-64` | `64px` |
| `space-16`   | `16px` | | `space-72` | `72px` |
| `space-20`   | `20px` | | `space-80` | `80px` |
| `space-24`   | `24px` | |            |        |
| `space-28`   | `28px` | |            |        |

**Sizing** (`--primitive-size-*`) mirrors the same scale `1px → 80px`, used for
icon boxes, control heights and fixed dimensions.

---

## 2. Border radius

`--primitive-radius-*`

| Token | Value | Use |
|-------|-------|-----|
| `radius-none`  | `0`     | Cards, images, editorial blocks (mostly square) |
| `radius-02`    | `2px`   | Subtle inputs |
| `radius-04`    | `4px`   | Buttons, tags |
| `radius-08`    | `8px`   | Panels |
| `radius-12`    | `12px`  | Modals / larger cards |
| `radius-16`–`32` | `16–32px` | Large surfaces |
| `radius-round` | `999px` | Pills, avatars, icon buttons |

---

## 3. Typography — primitives

### Font families
| Token | Stack |
|-------|-------|
| `font-family-cnn-sans-display` | `cnn_sans_display, helveticaneue, Helvetica, Arial, Utkal, sans-serif` |
| `font-family-cnn-condensed`    | `cnn_sans_condensed, "Arial Narrow", "Helvetica Narrow", sans-serif` |
| `font-family-cnn-sans`         | `cnn_sans` |
| `font-family-noto-serif`       | `noto_serif, Georgia, "Times New Roman", serif` |

> **CNN Sans** is the proprietary brand typeface (based on Gotham), used across
> virtually all UI and headlines. **Noto Serif** is used for long-form article
> body in some templates. **CNN Sans Condensed** is used for tight headline
> decks and tickers. Arabic uses `noto_sans_arabic`.

### Font size ramp (`--primitive-type-font-size-*`)
`10, 12, 14, 16, 18, 20, 24, 30, 32, 36, 40, 42, 48, 56, 64` (px)

### Line-height ramp (`--primitive-type-line-height-*`)
`10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 36, 40, 48` (px)

### Letter-spacing (`--primitive-type-letter-spacing-*`)
| Token | Value |
|-------|-------|
| `none` | `0` |
| `25`   | `0.25px` |
| `50`   | `0.5px` |
| `100`  | `1px` |
| `125`  | `1.25px` |
| `150`  | `1.5px` |
| `1200` | `12px` (all-caps eyebrows) |

### Weight styles (`--primitive-type-font-wt-style-*`)
`Thin, Extra Light, Light, Regular, Medium, SemiBold, Bold, ExtraBold, Heavy, Black`
— each with an Italic counterpart. Headlines typically render **Bold / ExtraBold**.

---

## 4. Typography — semantic scale

Roles map size + line-height primitives into named text styles. Font family for
all roles = **CNN Sans Display**, letter-spacing `0` (except `subtitle` = `1px`).

### Headers (`--semantic-type-header-*`)
| Level | Font size | Line height |
|-------|-----------|-------------|
| H1 | `42px` | `48px` |
| H2 | `30px` | `36px` |
| H3 | `24px` | `30px` |
| H4 | `20px` | `26px` |
| H5 | `16px` | `22px` |
| H6 | `14px` | `20px` |

### Title (card / headline links) (`--semantic-type-title-*`)
| Size | Font size | Line height |
|------|-----------|-------------|
| 2xl | `32px` | `40px` |
| xl  | `24px` | `30px` |
| lg  | `20px` | `26px` |
| md  | `18px` | `24px` |
| sm  | `16px` | `22px` |
| xs  | `14px` | `20px` |

### Body / Description (`--semantic-type-body-*`, `-description-*`)
| Size | Font size | Line height (body) | Line height (description) |
|------|-----------|--------------------|---------------------------|
| xl | `18px` | `32px` | `26px` |
| lg | `16px` | `26px` | `22px` |
| md | `14px` | `20px` | `20px` |
| sm | `12px` | `16px` | `18px` |

### Action (buttons) (`--semantic-type-action-*`)
| Size | Font size | Line height |
|------|-----------|-------------|
| xl | `18px` | `32px` |
| lg | `16px` | `26px` |
| md | `14px` | `20px` |
| sm | `12px` | `16px` |

### Metadata (bylines, timestamps) (`--semantic-type-metadata-*`)
xl `18/32` · lg `16/26` · md `14/20` · sm `12/16`

### Subtitle / eyebrow (`--semantic-type-subtitle-*`) — letter-spacing `1px`
lg `16/20` · md `14/20` · S `12/16`

---

## 5. Layout & grid

- **12-column grid.** Column max-widths scale per breakpoint; the 12-col track
  maxes at `1216px → 1295px → 1376px` across large breakpoints
  (`--device-size-grid-12-col-max-width`).
- Responsive values are driven by a **breakpoint size id**: `xs, sm, md, lg, xl`
  (`--device-size-breakpoint-size-id`).
- Header horizontal margin steps: `20px (sm) → 32px (md) → 48px (lg)`
  (`--device-size-component-header-home-h-margin`).
- Zone (content section) vertical rhythm: `margin-bottom` steps `24px → 48px`.

---

## 6. Token architecture (how to consume)

```
--primitive-*            raw values (colors, px scales, font stacks)
   ↓ referenced by
--semantic-color-*       intent-based (bg-primary, action-conversion-bg …)
--semantic-type-*        role-based text styles (header-h1, title-lg …)
   ↓ referenced by
--theme-semantic-*       theme-scoped aliases (light / inverse)
--device-size-*          responsive, breakpoint-driven values
   ↓ referenced by
--theme-component-*      per-component final values
```

**Rule of thumb:** never hardcode a hex or px in components — reference a
semantic token, and switch themes/breakpoints by overriding the layer above.
