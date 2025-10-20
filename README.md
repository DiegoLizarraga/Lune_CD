Lune CD: Tu Asistente Virtual de Escritorio
Python Version
License
Groq API En este caso


Lune CD no es solo una adorable mascota de escritorio; es un asistente virtual inteligente diseñado para integrarse profundamente en tu flujo de trabajo. Inspirado en aplicaciones como Phase Pal, Lune CD combina la interacción visual de una mascota con la potencia de un agente de IA capaz de automatizar tareas, recordar información y ayudarte con tu día a día directamente desde tu escritorio.

🌟 Características Principales
 *Mascota de Escritorio Animada: Interactúa con Lune a través de clics y observa sus animaciones (feliz, normal, hablando).
 *Chatbot Integrado (Groq API): Mantén conversaciones naturales con un potente modelo de lenguaje (Llama 3) directamente desde tu terminal.
 *Integración con el Sistema Operativo: Abre aplicaciones como Visual Studio Code, tu navegador o la calculadora con simples comandos de voz o texto.
 *Gestión de Notas y Recordatorios: Toma notas rápidas y establece recordatorios inteligentes que Lune te notificará en el momento indicado.
 *Análisis de Pantalla Inteligente (OCR): Lune monitorea tu pantalla (con tu permiso) y puede recordar temas importantes que veas, recordándolos más tarde.
 *Sistema de Notificaciones: Recibe notificaciones del sistema para tus recordatorios y alertas importantes.
 *Arquitectura Modular: Código bien organizado en módulos independientes, facilitando la extensión y el mantenimiento.
 --Estructura del Proyecto
El proyecto está diseñado con una arquitectura modular para facilitar su comprensión y expansión.


··Instalacion y Configuracion··
Sigue estos pasos para poner a Lune CD en funcionamiento en tu máquina.

Prerrequisitos
Python 3.8 o superior.
Git.
Tesseract OCR (para el analisis de pantalla).
1. Clonar el Repositorio
bash

Line Wrapping

Collapse
Copy
1
2
git clone https://github.com/DiegoLizarraga/Lune_CD.git
cd Lune_CD
2. Crear un Entorno Virtual (Recomendado)
bash

Line Wrapping

Collapse
Copy
1
2
3
4
5
python -m venv venv
# En Windows
venv\Scripts\activate
# En macOS/Linux
source venv/bin/activate
3. Instalar Dependencias
bash

Line Wrapping

Collapse
Copy
1
pip install -r requirements.txt
4. Instalar Tesseract OCR
Esta dependencia es crucial para la funcionalidad de analisis de pantalla.

Windows: Descarga el instalador desde la página oficial de Tesseract. Asegúrate de marcar la opción para añadir Tesseract al PATH durante la instalación.
macOS: Usa Homebrew: brew install tesseract
Linux (Debian/Ubuntu): sudo apt-get install tesseract-ocr tesseract-ocr-spa
5. Configurar tu API Key de Groq
Obtén tu API Key gratuita en Groq Console.
Abre el archivo lune_config.json (se creará la primera vez que ejecutes la app) o edítalo directamente.
Reemplaza "TU_API_KEY_AQUI" con tu clave real.
json

Line Wrapping

Collapse
Copy
1
2
3
4
⌄
{
    "api_key": "gsk_your_real_api_key_here",
    ...
}
 Cómo Usar Lune CD
Ejecutar la Aplicación
Una vez configurado, simplemente ejecuta:

bash

Line Wrapping

Collapse
Copy
1
python main.py
Verás a Lune en tu pantalla y se iniciará una sesión de chat en tu terminal.

Comandos de Voz/Texto
Puedes interactuar con Lune escribiendo en la terminal. Aquí tienes algunos ejemplos:

Comando
Descripción
abre el compilador	Abre Visual Studio Code.
abre el navegador	Abre tu navegador web por defecto.
toma nota comprar leche	Guarda una nota rápida.
lista mis notas	Muestra todas tus notas guardadas.
recuérdame la reunión a las 15:00	Programa un recordatorio.
recuérdame llamar a mamá en 30 minutos	Programa un recordatorio relativo.
busca en pantalla tarea	Busca un tema en el historial de pantalla.
información del sistema	Muestra datos sobre tu PC.
salir	Cierra la sesión de chat.

Atajos de Teclado
Ctrl + T: Abre o enfoca la terminal de chat.
Ctrl + N: Haz que Lune sonría por un momento.
Ctrl + Q: Cierra la aplicación por completo.
 Configuración
Puedes personalizar el comportamiento de Lune CD editando el archivo lune_config.json.

screen_monitoring: Activa o desactiva el monitoreo de pantalla y ajusta el intervalo.
notifications: Configura la duración y si quieres sonido en las notificaciones.
reminders: Ajusta la frecuencia con la que se comprueban los recordatorios.
ui: Cambia el tamaño o la posición inicial de la mascota.
🤝 Cómo Contribuir
¡Las contribuciones son lo que hace que la comunidad de código abierto sea un lugar increíble para aprender, inspirar y crear! Cualquier contribución que hagas será muy apreciada.

Haz un Fork del proyecto.
Crea tu Rama de Funcionalidad (git checkout -b feature/FuncionIncreible).
Haz Commit de tus Cambios (git commit -m 'Añadiendo una Función Increíble').
Haz Push a la Rama (git push origin feature/FuncionIncreible).
Abre un Pull Request.

 Agradecimientos
A Groq por proporcionar una API increíblemente rapida y accesible para modelos de lenguaje. (aparte de ser gratis)
A la hatsune miku por ser mi inspiracion para hacer este proyecto 🙏🙏🙏
