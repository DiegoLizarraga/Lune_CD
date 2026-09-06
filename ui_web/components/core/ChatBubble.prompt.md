**ChatBubble** — one message row for the Lune chat surface; use for both user and assistant turns.

```jsx
<ChatBubble role="user" time="14:32">Abre YouTube</ChatBubble>
<ChatBubble role="bot" provider="local" avatar={<Avatar bot ring="cyan"/>} time="14:32" streaming>
  Claro. Abriendo YouTube
</ChatBubble>
```

Props: `role` (`bot | user`), `provider` (`local | cloud` — tints the bot edge cyan/blue), `sender`, `avatar`, `time`, `streaming` (blinking caret). User bubbles fill electric blue and cut the bottom-right; bot bubbles cut the bottom-left.
