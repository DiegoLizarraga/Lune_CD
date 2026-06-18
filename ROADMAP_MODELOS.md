# 🧩 ROADMAP — Modelos y Avatares de Lune (estilo Mate-Engine)

> *Inspirado en [Mate-Engine](https://github.com/shinyflvre/Mate-Engine): una mascota de*
> *escritorio con modelos animados, mods e intercambio de personajes.*
> *Aquí está el plan para que Lune evolucione de imágenes a modelos vivos.* 🌙

---

## 🎯 Visión

Hoy Lune muestra su estado con imágenes `.png` y videos `.mp4`. La meta es que
puedas **cambiar el "cuerpo" de Lune** (avatar) como quien cambia de skin, e incluso
soltar modelos animados de la comunidad — igual que Mate-Engine permite cargar
modelos VRM y mods.

---

## ✅ Fase 1 — Avatar Packs (¡ya implementado en v8.0!)

Sistema base de packs de expresiones intercambiables.

- Cada pack es una subcarpeta en `lune_face/packs/<nombre>/`.
- Contiene los mismos archivos que `lune_face/` (`lune_normal.png`, `pensando.mp4`, etc.).
- Se elige desde **⚙️ Configuración General → 🎨 Modelo visual de Lune**.
- `default` usa directamente la carpeta `lune_face/`.

**Cómo crear tu primer pack:**
```text
lune_face/
└── packs/
    └── lune_neon/
        ├── lune_normal.png
        ├── lune_happy.png
        ├── pensando.mp4
        └── ...   (los archivos que quieras sobreescribir)
```
Si falta un archivo en el pack, Lune cae automáticamente al de `lune_face/`.

---

## 🔜 Fase 2 — Manifiesto de Pack (`pack.json`)

Metadatos por pack para hacerlo autodescriptivo:
```json
{
  "nombre": "Lune Neon",
  "autor": "Tú",
  "version": "1.0",
  "tipo": "imagenes",
  "voz": "es-MX-DaliaNeural",
  "colores": { "accent": "#7c6af7" }
}
```
- Permite que cada pack traiga su propio tema de color y voz.
- Validación y vista previa en el selector.

---

## 🔮 Fase 3 — Live2D (2D animado)

- Integrar un runtime Live2D (p. ej. vía `live2d-py` o un widget web embebido).
- Estados (`happy`, `thinking`, …) se mapean a **motions/expressions** del modelo.
- Lip-sync básico sincronizado con el motor de voz (`edge-tts`).

## 🔮 Fase 4 — VRM / 3D (como Mate-Engine)

- Visor 3D para modelos `.vrm` (humanoides estándar).
- Animaciones idle, gestos y reacciones por estado emocional.
- Modo "mascota de escritorio": ventana sin bordes, siempre encima, arrastrable.
- Posible integración con un runtime externo (Unity/Godot) vía IPC, o un visor
  GL embebido en Qt.

## 🔮 Fase 5 — Tienda de Mods / Comunidad

- Importar packs con un clic (arrastrar `.zip`).
- Repositorio comunitario de avatares y voces.

---

## 🛠️ Notas técnicas

- El punto de extensión actual está en [main.py](main.py): `get_face_info()`,
  `set_active_pack()`, `listar_packs()` y la constante `PACKS_DIR`.
- La selección persiste en `config.json` → `avatar.pack`.
- Para Live2D/VRM, lo más limpio es introducir una clase `AvatarRenderer` con
  implementaciones `ImagenRenderer` (actual), `Live2DRenderer`, `VRMRenderer`,
  y que `LuneFaceWidget` delegue en la activa.

> *Paso a paso, sin prisa. Primero packs, luego me muevo de verdad.* — Lune 🌙
