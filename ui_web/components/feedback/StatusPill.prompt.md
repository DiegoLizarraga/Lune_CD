**StatusPill** — pill with a pulsing LED; use in the topbar / sidebar to show connection or activity state.

```jsx
<StatusPill status="live" />          // "Listo"
<StatusPill status="busy">Procesando…</StatusPill>
```

States: `live` (cyan, pulsing), `busy` (yellow), `error` (red), `off` (gray). Default label is Spanish; override via children.
