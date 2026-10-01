"""
version.py — Única fuente de verdad de la versión de Lune CD.

Estaba repetida en theme.py (8.0) y utils.py (4.5) y ambas se habían quedado
atrás respecto a los commits. Ahora todo el mundo importa de aquí.

Desde la 11.2 también manda en los Releases de GitHub: el instalador se llama
LuneCD-Setup-<versión>.exe, el tag es v<versión> y el actualizador compara con
esto. Súbela en cada versión (packaging/ y .github/workflows/release.yml la leen).
"""

APP_VERSION = "11.3"
