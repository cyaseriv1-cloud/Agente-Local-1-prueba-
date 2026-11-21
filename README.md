# Antigravity V7 — Agente Local de Inteligencia Artificial

Agente local autónomo e interactivo construido con Python, CustomTkinter y Ollama.

## Características
- **Centro de mando con interfaz moderna** (CustomTkinter en modo oscuro).
- **Integración con Ollama**: soporte para streaming en tiempo real y selección dinámica de modelos locales.
- **Herramientas autónomas (Tool Calling)**:
  - Búsqueda en la web (DuckDuckGo).
  - Ejecución de comandos PowerShell en entorno controlado.
  - Lectura y escritura de archivos en Workspace.
  - Extracción de contenido de páginas web.
- **Soporte multimodal y documentos**: lectura y análisis de PDFs, documentos Word (.docx), imágenes y texto plano.
- **Ejecución de código Python in-chat**: botón directo para correr scripts y visualizar salida.
- **Gestión de sesiones múltiples**: barra lateral con historial persistente, fijado de chats (pin) y exportación a Markdown.
- **Control de temperatura y contexto**: slider en tiempo real y contador de uso de memoria.
- **Arrastrar y soltar (Drag & Drop)** y soporte para bandeja del sistema (System Tray).

## Requisitos
- Python 3.10+
- [Ollama](https://ollama.ai/) instalado y en ejecución con tus modelos descargados.

## Instalación
```bash
pip install -r requirements.txt
```

## Ejecución
Ejecuta el archivo:
```bash
python agente_gui.py
```
O simplemente haz doble clic en `Iniciar_Agente.bat`.
