"""
setup.py — Instalador para Lune CD v7.0
Permite ejecutar "lune" desde cualquier carpeta en la terminal.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Leer README
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

setup(
    name="lune-cd",
    version="7.0.0",
    description="🌙 Asistente de escritorio con memoria, OpenRouter + Claude Code integration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Lune CD Contributors",
    author_email="",
    url="https://github.com/DiegoLizarraga/Lune_CD",
    license="MIT",
    
    # Packages
    packages=find_packages(),
    
    # Dependencias
    install_requires=[
        "PyQt6>=6.6.0",
        "requests>=2.31.0",
        "gtts>=2.5.0",
        "pygame>=2.5.0",
        "python-telegram-bot>=20.0",
        "psutil>=5.9.0",
        "pyautogui>=0.9.54",
        "pynput>=1.7.6",
        "python-dotenv>=1.0.0",
        "aiofiles>=23.0.0",
        "pyperclip>=1.8.2",
        "edge-tts>=6.1.0",
    ],
    
    # Scripts CLI
    entry_points={
        "console_scripts": [
            "lune=lune_cli:main",
        ],
    },
    
    # Metadatos
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: Spanish",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Office/Business",
    ],
    
    python_requires=">=3.10",
    include_package_data=True,
    zip_safe=False,
)
