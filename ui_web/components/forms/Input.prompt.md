**Input** — clipped-corner text field with cyan focus glow; use for all single-line and multi-line text entry (API keys, prompts, messages, settings).

```jsx
<Input label="API Key de OpenRouter" type="password" placeholder="sk-or-..." hint="Se guarda localmente" />
<Input label="System Prompt" textarea rows={4} />
```

Props: `label`, `required`, `leading` (glyph inside field), `hint`, `error`, `textarea`. All native input/textarea attributes pass through.
