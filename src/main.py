#!/usr/bin/env python3
"""
Lune CD v4.0 - Mascota Virtual de Escritorio
Tu compañera IA siempre disponible
"""

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from src.ui.pet_window import LunePetWindow
from src.utils.config import Config

def main():
    # Configurar atributos para Windows
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('lunecode.mascota.v4')
    
    # Crear aplicación
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # No cerrar al cerrar ventanas
    
    # Cargar configuración
    config = Config()
    
    # Crear ventana de la mascota
    lune = LunePetWindow(config)
    lune.show()
    
    print("🌙 Lune CD v4.0 iniciada")
    print("✨ ¡Tu mascota virtual está lista!")
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()