"""
instalador.py — Instalador de Lune CD para usuarios nuevos (ventana con Tkinter).

Explica QUÉ hace cada componente y PARA QUÉ sirve (p. ej. "esto es para que Lune
hable"), marca lo que ya está instalado, y deja elegir qué instalar. Usa solo la
librería estándar (Tkinter viene con Python) para poder correr ANTES de instalar
nada más. Se lanza con `instalar_lune.bat` o desde Ajustes → "Instalar componentes".

La lista de componentes vive en servicios/actualizador.py (NUCLEO y OPCIONALES);
aquí hay una copia de respaldo por si ese módulo no se puede importar.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# ── Componentes (respaldo; la fuente de verdad es servicios/actualizador.py) ────
_NUCLEO_RESPALDO = {
    "Núcleo de Lune (obligatorio)": {
        "modulos": {"PyQt6": "PyQt6", "requests": "requests", "websockets": "websockets"},
        "nota": "La ventana, la conexión con los modelos y la red entre equipos. Sin esto no arranca.",
    },
}
_OPCIONALES_RESPALDO = {
    "Voz de salida (Lune habla)": {"modulos": {"edge_tts": "edge-tts", "pygame": "pygame"},
        "nota": "Para que Lune lea sus respuestas en voz alta (edge-tts necesita internet)."},
    "Voz de entrada (dictado)": {"modulos": {"faster_whisper": "faster-whisper", "sounddevice": "sounddevice"},
        "nota": "Para hablarle por micrófono y para el modo llamada. 100% local; pesa bastante."},
    "Interfaz completa (piel web animada)": {"modulos": {"PyQt6.QtWebEngineWidgets": "PyQt6-WebEngine"},
        "nota": "La interfaz animada y la mascota en video. Sin esto se usa la nativa ligera."},
    "Leer PDF": {"modulos": {"pypdf": "pypdf"}, "nota": "Para adjuntar PDF al chat."},
    "Leer Word (.docx)": {"modulos": {"docx": "python-docx"}, "nota": "Para adjuntar Word al chat."},
    "Optimizador del sistema": {"modulos": {"psutil": "psutil"}, "nota": "Monitor de CPU/RAM y limpieza."},
    "Red local (descubrir dispositivos)": {"modulos": {"zeroconf": "zeroconf"},
        "nota": "Para que Lune encuentre otros equipos con Lune en tu red."},
    "Voz 100% local (Kokoro)": {"modulos": {"kokoro_onnx": "kokoro-onnx"},
        "nota": "Lune habla sin internet. Necesita además espeak-ng y los pesos en modelos_voz/."},
    "Conversión de voz RVC (experimental)": {"modulos": {"rvc_python": "rvc-python"},
        "nota": "Cambia el timbre de voz con un modelo .pth. Muy pesado (torch)."},
}


def _tablas():
    try:
        sys.path.insert(0, str(RAIZ))
        from servicios import actualizador as A
        return A.NUCLEO, A.OPCIONALES
    except Exception:
        return _NUCLEO_RESPALDO, _OPCIONALES_RESPALDO


def _instalado(modulos: dict) -> bool:
    return all(importlib.util.find_spec(m) is not None for m in modulos)


def main() -> int:
    import tkinter as tk
    from tkinter import ttk, scrolledtext

    nucleo, opcionales = _tablas()
    win = tk.Tk()
    win.title("Instalar Lune CD")
    win.geometry("760x640")
    win.configure(bg="#0f1424")
    estilo = ttk.Style(win)
    try:
        estilo.theme_use("clam")
    except Exception:
        pass
    estilo.configure("TFrame", background="#0f1424")
    estilo.configure("TLabel", background="#0f1424", foreground="#eaf1ff", font=("Segoe UI", 10))
    estilo.configure("Titulo.TLabel", foreground="#00e5ff", font=("Segoe UI", 15, "bold"))
    estilo.configure("Nota.TLabel", foreground="#97a6c4", font=("Segoe UI", 9))
    estilo.configure("Ok.TLabel", foreground="#00e5ff", font=("Consolas", 9, "bold"))
    estilo.configure("TCheckbutton", background="#0f1424", foreground="#eaf1ff", font=("Segoe UI", 10, "bold"))
    estilo.map("TCheckbutton", background=[("active", "#0f1424")])
    estilo.configure("TButton", font=("Segoe UI", 10, "bold"))

    raiz = ttk.Frame(win, padding=16); raiz.pack(fill="both", expand=True)
    ttk.Label(raiz, text="月  Instalar Lune CD", style="Titulo.TLabel").pack(anchor="w")
    ttk.Label(raiz, style="Nota.TLabel", wraplength=720, justify="left",
              text=f"Python {sys.version.split()[0]} en {sys.executable}\n"
                   "Marca lo que quieras. Cada componente explica para qué sirve; lo ya instalado aparece con OK.").pack(anchor="w", pady=(2, 10))

    # Lista con scroll
    cont = ttk.Frame(raiz); cont.pack(fill="both", expand=True)
    canvas = tk.Canvas(cont, bg="#0f1424", highlightthickness=0)
    sb = ttk.Scrollbar(cont, orient="vertical", command=canvas.yview)
    lista = ttk.Frame(canvas)
    lista.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=lista, anchor="nw")
    canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")

    vars_ = {}
    def fila(nombre, info, obligatorio):
        ya = _instalado(info["modulos"])
        v = tk.BooleanVar(value=(obligatorio and not ya) or False)
        f = ttk.Frame(lista, padding=(0, 6)); f.pack(fill="x")
        cb = ttk.Checkbutton(f, text=nombre + ("  (obligatorio)" if obligatorio else ""), variable=v)
        cb.pack(anchor="w")
        if ya:
            v.set(False); cb.state(["disabled"])
            ttk.Label(f, text="OK · ya instalado", style="Ok.TLabel").pack(anchor="w", padx=24)
        ttk.Label(f, text=info["nota"], style="Nota.TLabel", wraplength=680, justify="left").pack(anchor="w", padx=24)
        ttk.Label(f, text="pip install " + " ".join(info["modulos"].values()), style="Nota.TLabel").pack(anchor="w", padx=24)
        vars_[nombre] = (v, info)
    for n, i in nucleo.items(): fila(n, i, True)
    for n, i in opcionales.items(): fila(n, i, False)

    ttk.Label(raiz, style="Nota.TLabel", wraplength=720, justify="left",
              text="Aparte de esto: para el modelo local instala Ollama (ollama.com) y baja un modelo con "
                   "`ollama pull <modelo>`; para Kokoro en español instala espeak-ng.").pack(anchor="w", pady=(8, 4))

    log = scrolledtext.ScrolledText(raiz, height=8, bg="#080b16", fg="#eaf1ff", insertbackground="#eaf1ff",
                                    font=("Consolas", 9), relief="flat")
    log.pack(fill="x", pady=(6, 8))

    botones = ttk.Frame(raiz); botones.pack(fill="x")
    btn = ttk.Button(botones, text="Instalar lo marcado")
    btn.pack(side="left")
    ttk.Button(botones, text="Descargar Ollama", command=lambda: webbrowser.open("https://ollama.com/download")).pack(side="left", padx=8)
    ttk.Button(botones, text="Cerrar", command=win.destroy).pack(side="right")

    def escribir(t):
        log.insert("end", t); log.see("end"); win.update_idletasks()

    def instalar():
        paquetes = []
        for v, info in vars_.values():
            if v.get():
                paquetes += list(info["modulos"].values())
        if not paquetes:
            escribir("Nada marcado.\n"); return
        btn.state(["disabled"])
        escribir(f"> {sys.executable} -m pip install {' '.join(paquetes)}\n")
        def correr():
            p = subprocess.Popen([sys.executable, "-m", "pip", "install", *paquetes],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for linea in p.stdout:
                win.after(0, escribir, linea)
            p.wait()
            win.after(0, escribir, "\nListo. Cierra esta ventana y abre Lune con iniciar_lune.vbs.\n" if p.returncode == 0
                      else f"\nTerminó con errores (código {p.returncode}). Revisa el mensaje de arriba.\n")
            win.after(0, lambda: btn.state(["!disabled"]))
        threading.Thread(target=correr, daemon=True).start()
    btn.configure(command=instalar)

    win.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
