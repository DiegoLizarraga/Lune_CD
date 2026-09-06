**ProviderTab** — the sidebar selector for switching AI provider (Lune AI Nube ↔ Local); the signature navigation pattern of the app.

```jsx
<ProviderTab icon={<CloudSvg/>} name="Lune AI (Nube)" desc="Enrutamiento inteligente" accent="blue" active />
<ProviderTab icon={<CpuSvg/>}  name="Lune AI (Local)" desc="Modelo offline" accent="cyan" onClick={...} />
```

Props: `icon`, `name`, `desc`, `accent` (`cyan` for local, `blue` for cloud), `active`. Lights its icon + LED when active.
