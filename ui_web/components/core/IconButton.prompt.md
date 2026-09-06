**IconButton** — square icon-only control; use for toolbar/sidebar actions (settings, clear, memory, tools, send). Provide an inline Lucide SVG as children.

```jsx
<IconButton label="Ajustes" variant="ghost"><GearSvg/></IconButton>
<IconButton label="Enviar" variant="cyan" clip><ArrowSvg/></IconButton>
```

Variants: `ghost | solid | cyan | danger`. Sizes `sm | md | lg`. Pass `active` for selected state, `clip` for the angular corner.
