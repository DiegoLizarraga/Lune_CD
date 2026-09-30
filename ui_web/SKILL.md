---
name: lune-cd-design
description: Use this skill to generate well-branded interfaces and assets for Lune CD — a hybrid cloud/local desktop AI assistant — in its Shibuya Punk / Grind Fiction visual style, either for production or throwaway prototypes/mocks. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping.
user-invocable: true
---

# Lune CD · Shibuya Punk Design System

Read `readme.md` in this skill for the full guide (product context, voice & copy rules, visual foundations, iconography, component + UI-kit index), then explore the other files.

**The look in one breath:** Tokyo-night navy-black base, **electric cyan + electric blue** as dominant signal colors, **acid yellow** graffiti pop, cool whites/grays. Angular — **sharp edges and clipped/notched corners (`clip-path`), never rounded**. Neon glows + hard print-shadows. Scanline/grid/halftone textures. Katakana stickers. UPPERCASE `Chakra Petch` display, `Space Grotesk` body, `Space Mono` data. **No emoji** — line SVG icons only. Voice is direct, confident, with edge — no filler.

## Where things are
- `styles.css` — link this one file to get all tokens + fonts.
- `tokens/` — colors, typography, spacing, effects (glows, clips, textures), base helpers.
- `components/` — React primitives: Button, IconButton, Card, Avatar, ChatBubble, Input, Switch, Badge, StatusPill, ProviderTab. Each has a `.prompt.md` with usage.
- `ui_kits/lune-desktop/` — interactive recreation of the desktop app (sidebar + chat + settings).
- `assets/` — app logo + Lune's expression PNGs (`assets/asistente/anime/lune-*.png`) and animated WebM clips (`assets/asistente/anime-videos/`).

## How to work
If creating **visual artifacts** (slides, mocks, throwaway prototypes): copy the assets you need out of `assets/`, link `styles.css` (or inline the tokens), and build static HTML — reuse the component classes/patterns and the `.lune-backdrop` shell. Reference the `guidelines/` cards for exact swatches and specimens.

If working on **production code**: copy assets and read the token + component sources to become an expert in designing with this brand; the components are plain React referencing CSS custom properties.

If the user invokes this skill without specifics, **ask what they want to build**, ask a few focused questions (surface, audience, scope, how many variations), then act as an expert designer who outputs HTML artifacts _or_ production code as needed. Hold the line on the aesthetic: angular, electric, no emoji, direct copy.
