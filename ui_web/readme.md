# Lune CD · Shibuya Punk Design System

A complete brand + UI design system for **Lune CD** — a hybrid (cloud/local) desktop AI assistant — re-skinned in a **Shibuya Punk / Grind Fiction** aesthetic. Electric cyan and electric blue lead; acid yellow pops; everything else is Tokyo-night ink and cool steel. This project compiles into a runtime component library plus a gallery of foundation, component and product cards visible in the **Design System** tab.

> Built for desktop. Angular, high-contrast, neon-on-night. No emoji chrome, no chat-app softness — the product has teeth.

---

## 1 · Product context

**Lune CD** (v9.0) is a Python/PyQt6 desktop application: an AI assistant named **Lune** that runs against either **OpenRouter (Nube / cloud)** or **Ollama (Local / offline)**, with persistent memory, instant desktop "tools", edge-tts voice, characters, an optimizer, history, an optional desktop-assistant mode (Lune steps out of the window and floats over the desktop), and a synced Telegram bot. Lune is an **anime cel-shaded character** (a navy-suited secretary with a crescent-moon hairclip, die-cut with a white sticker outline) with 9 expression states: composed, happy, angry, surprised, wave, thinking, nervous, dismiss (+ base portrait) — in `assets/asistente/anime/`. (The earlier pixel-art set lives in the app's `lune_face/` folder.)

The original app shipped with a dark purple-accented UI and emoji iconography. **This design system replaces that** with a radical Shibuya Punk direction: angular clipped geometry, electric-blue/cyan signal colors, acid-yellow graffiti accents, katakana stickers, scanline and grid textures, and hard print-shadows — while keeping the existing blue/yellow/navy brand DNA and Lune's pixel-art look, both of which already sit squarely inside the aesthetic.

**Source repository (input):**
- GitHub — [`DiegoLizarraga/Lune_CD`](https://github.com/DiegoLizarraga/Lune_CD) (branch `master`). The PyQt6 app (`main.py`), config (`datos.json`), tools (`tools.py`), memory (`memoria.py`), Lune's expression set (`lune_face/`), and the app icon (`lune_icon.png`) were read to derive product behaviour, copy, layout, and brand assets. Explore it further to deepen any recreation.

> Reader note: you may not have access to that repo. Key assets and behaviours have been copied into this project (`assets/`, the `Lune Desktop` UI kit) so the system stands alone.

---

## 2 · Content fundamentals — voice & copy

**Language:** Spanish (Mexican / `es-MX`). UI labels are concise and often **UPPERCASE in the display font** ("RED NEURONAL", "CONFIGURACIÓN GENERAL"). System readouts use lowercase monospace ("openrouter/auto", "cpu 18%").

**Voice — the redesign's biggest copy shift:** the original Lune was warm and a little chatty, peppered with emoji ("Buenos días. ¿En qué te puedo ayudar hoy? 👀"). The Shibuya Punk Lune is **direct, confident, with edge and personality — no emoji, no filler.**

| Original (soft / emoji) | Shibuya Punk Lune (direct / punk) |
|---|---|
| "Buenos días. ¿En qué te puedo ayudar hoy? 👀" | "Lune en línea. Dime qué necesitas." |
| "¡Perfecto! Con gusto te ayudo 😊" | "Listo. Lo tengo. ¿Seguimos?" |
| "Estoy buscando esa información…" | "Tirando del modelo. Respuesta lista." |
| "Lo guardé en mi memoria ✅" | "Anotado. No se me olvida." |

**Rules of voice**
- **No emoji** anywhere in UI chrome or assistant copy. Iconography is SVG (see §5).
- **Second person, direct** ("Dime qué necesitas", "Pídemelo"). Lune refers to herself in first person with quiet confidence ("Aquí mando yo").
- **Short sentences.** Cut filler. "Sin relleno" is literally in her system prompt.
- **Mono for machine, display for human.** Commands, tokens, model names, timestamps → `Space Mono`. Headings, names, actions → `Chakra Petch`, uppercase.
- **Katakana as texture, not language.** ルネ (Lune), 月 (moon/night), 渋谷 (Shibuya), 夜 (night) appear as graffiti stickers/accents — decorative, never load-bearing for meaning.

---

## 3 · Visual foundations

**Aesthetic:** Shibuya Punk / Grind Fiction — late-90s/Y2K Tokyo street + video-game UI. Cel-shaded, graffiti, high-saturation, sharp and angular.

**Color** — deep navy-black base (`--ink-900` `#080B16`) under everything. Two **dominant signal colors**: electric **cyan** `#00E5FF` (primary, local/offline, live states) and electric **blue** `#1E55FF` (secondary, cloud, user bubbles). **Acid yellow** `#FFE000` is the graffiti pop — used sparingly for stickers, hazard dividers, the moon. Neutrals are cool: white, `--paper` `#EAF1FF`, and steel grays. Red `#FF3B5C` exists only for destructive/error states. See the **Colors** cards.

**Type** — `Chakra Petch` (angular techno) for all display/headings, set **UPPERCASE with wide tracking**; `Space Grotesk` for body/UI; `Space Mono` for data, code, timestamps, model names; `Noto Sans JP` (900) for katakana accents. Hero headings can carry a cyan text-glow. *Loaded from Google Fonts — see substitution note in §7.*

**Geometry & corners** — **sharp by default.** "Rounding" is expressed as **clipped/notched corners** via `clip-path`, never `border-radius` (the only exceptions: status pills and the switch). Core clips: `--clip-tr` (single top-right cut — buttons, tabs, chips), `--clip-notch` (top-right + bottom-left — the signature card), `--clip-blade`, `--clip-tag`. Borders are thick (1.5–3px) and dark or neon.

**Backgrounds & texture** — never flat. The app shell uses `.lune-backdrop`: ink + a faint technical **grid** + cyan/blue radial blooms. Panels add **scanlines** (`--tex-scanline`), **halftone** dot fields, or **hazard stripes** (yellow/black diagonal) for dividers and warnings. Lune sits in a scanlined stage with a cyan radial glow.

**Light, shadow, glow** — two shadow systems: **neon glows** (`--glow-cyan/-blue/-yellow`, soft outer halo + 1px ring) for live/focused/active elements, and **hard print-shadows** (`--shadow-hard`, a solid offset block, no blur) for buttons and the brand mark — the sticker/screen-print look. Cards get a soft depth shadow only when floating.

**Motion** — fast and snappy, never bouncy. `--ease-snap` (fast-in, hard-settle) and `--ease-out`; durations 120/200/360ms. Buttons **translate down-right on press** (the hard shadow collapses underneath). Status LEDs and typing dots pulse. All decorative animation respects `prefers-reduced-motion`.

**Hover / press states** — hover brightens fills slightly (`brightness(1.08)`) or fills a faint tinted background on ghosts; **press translates** and clears the shadow. Focus shows a 2px white or cyan outline offset from the clip.

**Cards** — the default surface is `Card`: notched corners, 1.5px steel border, ink fill, optional cyan/blue/yellow border tone, optional grid texture, scanline overlay, and a cyan corner "tick". Tonal variants signal context (cyan = local/primary, blue = cloud).

**Imagery vibe** — cel-shaded anime **pixel-art**, die-cut with a white sticker outline on black. Cool, high-saturation, neon-lit. Lune is always presented in a glowing, scanlined stage.

**Layout rules** — desktop app: fixed **248px sidebar** (provider switch + Lune's stage + actions), fixed **60px topbar** (active provider + status pill), scrolling chat/settings center column (max ~760px), fixed **88px input bar**. Content centers within a max width; chrome is full-bleed.

See the **Spacing**, **Effects**, **Type** and **Colors** card groups in the Design System tab for live specimens of all of the above.

---

## 4 · Components

Reusable React primitives (compiled into `_ds_bundle.js`, exposed on `window.LuneCDShibuyaPunkDesignSystem_8598db`). Each has a `.jsx`, a `.d.ts` props contract, a `.prompt.md`, and lives in a group folder with an `@dsCard` thumbnail.

| Component | Group | Role |
|---|---|---|
| `Button` | core | Clipped action button — 5 variants, 3 sizes, hard shadow |
| `IconButton` | core | Square icon-only control (toolbar / send / stop) |
| `Card` | core | Notched surface panel — tones, grid/scan/tick options |
| `Avatar` | core | Clipped Lune / bot / initials avatar with ring + status dot |
| `ChatBubble` | core | One chat row — blue user fill, provider-tinted bot edge |
| `Input` | forms | Clipped text field / textarea with cyan focus glow |
| `Switch` | forms | Angular on/off toggle |
| `Badge` | feedback | Mono tag chip — solid & outline |
| `StatusPill` | feedback | Pulsing-LED status (live / busy / error / off) |
| `ProviderTab` | navigation | Sidebar Nube ↔ Local selector |

---

## 5 · Iconography — see ICONOGRAPHY (§ below)

---

## 6 · UI kit

- **`ui_kits/lune-desktop/`** — a high-fidelity, interactive recreation of the Lune CD desktop window: sidebar (brand lockup, provider switch, reactive Lune stage, Telegram toggle, action nav), topbar with live status, an empty **welcome** state, a working **chat** (type a message or a command → user bubble, typing indicator, streamed reply or a tool-action card; Lune reacts), and the **Configuración General** settings panel. Composes the design-system components. Open `index.html`.

---

## 7 · ICONOGRAPHY

- **No emoji, no Unicode glyphs as icons.** The original app leaned on emoji (☁️ 🦙 🤖 ⚙️ 🧠 🛠 🔊); the redesign replaces every one with a **line SVG icon** (Lucide-style, 2px stroke, round caps) defined in `ui_kits/lune-desktop/icons.jsx` (Cloud, Cpu, Gear, Brain, Tool, Volume, Send, Stop, Telegram, Moon, Search, Bolt, External). Stroke icons inherit `currentColor` so they tint cyan/blue/yellow with their context.
- **Filled glyphs** (Send arrow, Stop square, Bolt) are used only where a solid mark reads better at small sizes.
- **Brand marks are PNG raster assets**, not icons: the app logo (`assets/lune-logo.png`) and Lune's anime expression set (`assets/asistente/anime/lune-*.png`, plus the animated VP9 clips in `assets/asistente/anime-videos/lune-*.webm` and the welcome portrait `lune_inicio.png`).
- **Katakana** (Noto Sans JP) functions as decorative iconography — sticker tags (ルネ / 月 / 夜 / 渋谷), never as functional labels.
- **Substitution flag:** if you need a wider icon set, **Lucide** ([lucide.dev](https://lucide.dev)) is the closest match to the hand-built set here (same 2px stroke, 24px grid) and can be linked from CDN.

### Font substitution flag
All four typefaces (`Chakra Petch`, `Space Grotesk`, `Space Mono`, `Noto Sans JP`) are loaded from **Google Fonts via CDN** in `tokens/fonts.css`, not self-hosted. For a fully offline/production build, download the `.woff2` files and replace the `@import` with local `@font-face` rules. **No original Lune brand font was provided** — these are an intentional aesthetic selection, not a match to a prior typeface. Flag for the user if a specific brand font exists.

---

## 8 · Index / manifest

```
styles.css                     ← consumers link THIS (an @import manifest only)
tokens/
  fonts.css                    ← Google Fonts @import
  colors.css                   ← ink, cyan, blue, yellow, neutrals + semantic aliases
  typography.css               ← families, scale, roles
  spacing.css                  ← 8px scale, radii, border widths, layout metrics
  effects.css                  ← glows, hard shadows, clip-paths, textures, motion
  base.css                     ← reset + .lune-backdrop / .lune-overline / .lune-scanlines helpers
components/
  core/        Button · IconButton · Card · Avatar · ChatBubble (+ cards)
  forms/       Input · Switch (+ card)
  feedback/    Badge · StatusPill (+ card)
  navigation/  ProviderTab (+ card)
guidelines/                    ← foundation specimen cards (Colors, Type, Spacing, Effects, Brand)
ui_kits/
  lune-desktop/                ← interactive desktop-app recreation (index.html + jsx)
assets/
  lune-logo.png                ← app mark
  asistente/anime/             ← lune-*.png (9 expression states) + lune_inicio.png (welcome)
  asistente/anime-videos/      ← lune-*.webm (VP9 animated clips; QtWebEngine has no H.264)
SKILL.md                       ← Agent-Skill entry point
readme.md                      ← this file
```

Generated automatically (do not edit): `_ds_bundle.js`, `_ds_manifest.json`, `_adherence.oxlintrc.json`.

---

## 9 · Caveats

- Fonts are CDN Google Fonts and an aesthetic pick — no original brand font was provided (see §7).
- The desktop app's real backend (OpenRouter / Ollama / Telegram / voice / tools) is **not** wired — the UI kit fakes responses and tool actions for demonstration.
**Qt adaptation note:** the production app is Qt, which can't do `clip-path`, soft layered shadows or webfonts reliably. When designing for the real app: replace clipped corners with **near-straight radii (2–3px)** and **thick neon borders (2–3px)**, keep glows as sparse icon-level effects, and fall back to Segoe UI / Consolas / Yu Gothic UI. The HTML system here is the ideal brand expression; Qt gets the pragmatic translation.

- Lune ships with the anime expression set (9 states) in `assets/asistente/anime/`; source sprite sheet + base portrait in `uploads/`.
