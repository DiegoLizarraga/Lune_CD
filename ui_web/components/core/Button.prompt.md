**Button** — the primary clipped-corner action control; use for any committed action (send, save, launch).

```jsx
<Button variant="primary" size="md" onClick={send}>Enviar</Button>
```

Variants: `primary` (electric cyan), `secondary` (electric blue), `pop` (acid yellow), `ghost` (cyan outline), `danger` (red). Sizes `sm | md | lg`. Pass `block` to fill width, `shadow={false}` to drop the offset shadow, and `leading`/`trailing` for icons. Label renders uppercase + tracked automatically — write it in normal case.
