import customtkinter as ctk
import threading
import subprocess
import requests
import os
import base64
import json
import uuid
import datetime
import sys
import io
import tempfile
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from tkinter import filedialog, messagebox
import tkinter as tk
import PyPDF2
import docx

# ──────────────────────────────────────────────
# Intentar importar librerías opcionales ligeras
# ──────────────────────────────────────────────
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DRAG_DROP_DISPONIBLE = True
except ImportError:
    DRAG_DROP_DISPONIBLE = False

try:
    import pystray
    from PIL import Image as PILImage, ImageDraw
    TRAY_DISPONIBLE = True
except ImportError:
    TRAY_DISPONIBLE = False

# ──────────────────────────────────────────────
# Configuración global
# ──────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

OLLAMA_URL = "http://localhost:11434/api"
WORKSPACE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Workspace")
SESSION_DIR = os.path.join(WORKSPACE_DIR, "sesiones")

for d in [WORKSPACE_DIR, SESSION_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)

DEFAULT_SYSTEM_PROMPT = f"""Eres un Súper-Agente de IA avanzado.
Tienes acceso a herramientas para buscar en internet, ejecutar comandos, y leer/crear/listar archivos en tu Workspace ({WORKSPACE_DIR}).
Siempre que necesites información externa o manejar archivos, USA TUS HERRAMIENTAS.
Responde siempre en el mismo idioma que el usuario.
"""

TOOLS = [
    {"type":"function","function":{"name":"ejecutar_comando","description":"Ejecuta un comando de PowerShell en la computadora del usuario y devuelve la salida.","parameters":{"type":"object","properties":{"comando":{"type":"string","description":"El comando de PowerShell a ejecutar."}},"required":["comando"]}}},
    {"type":"function","function":{"name":"buscar_en_internet","description":"Busca información en internet usando DuckDuckGo.","parameters":{"type":"object","properties":{"query":{"type":"string","description":"Lo que deseas buscar."}},"required":["query"]}}},
    {"type":"function","function":{"name":"leer_pagina_web","description":"Extrae el texto completo de una URL específica.","parameters":{"type":"object","properties":{"url":{"type":"string","description":"La URL de la página a leer."}},"required":["url"]}}},
    {"type":"function","function":{"name":"listar_directorio","description":"Lista todos los archivos y carpetas en una ruta específica dentro del Workspace.","parameters":{"type":"object","properties":{"ruta":{"type":"string","description":"Ruta relativa a explorar (deja vacío para la raíz del Workspace)"}}}}},
    {"type":"function","function":{"name":"leer_archivo","description":"Lee el contenido de un archivo dentro del Workspace.","parameters":{"type":"object","properties":{"nombre_archivo":{"type":"string","description":"Nombre del archivo a leer (ej. datos.txt)"}},"required":["nombre_archivo"]}}},
    {"type":"function","function":{"name":"escribir_archivo","description":"Crea o sobrescribe un archivo en el Workspace con el contenido proporcionado.","parameters":{"type":"object","properties":{"nombre_archivo":{"type":"string","description":"Nombre del archivo (ej. script.py)"},"contenido":{"type":"string","description":"Contenido completo del archivo a guardar"}},"required":["nombre_archivo","contenido"]}}},
]

# ──────────────────────────────────────────────
# Burbuja de Streaming
# ──────────────────────────────────────────────
class BurbujaStreaming:
    def __init__(self, parent_scroll, remitente, bg_color, is_user=False, on_ejecutar=None):
        self.parent_scroll = parent_scroll
        self.on_ejecutar = on_ejecutar

        self.frame_row = ctk.CTkFrame(parent_scroll, fg_color="transparent")
        self.frame_row.pack(fill="x", pady=5)

        side = "right" if is_user else "left"
        self.bubble = ctk.CTkFrame(self.frame_row, fg_color=bg_color, corner_radius=15)
        self.bubble.pack(side=side, padx=10, fill="y")

        header = ctk.CTkLabel(self.bubble, text=remitente, text_color="gray", font=("Arial", 10, "bold"))
        header.pack(anchor="w" if not is_user else "e", padx=10, pady=(5, 0))

        self.is_user = is_user
        self.widgets = []
        self.in_code_block = False
        self.buffer = ""
        self.texto_acumulado_bloque = ""
        self.texto_completo_global = ""
        self.lang_hint = ""

        self.current_box = self._crear_caja_texto()

    def _crear_caja_texto(self):
        caja = ctk.CTkTextbox(self.bubble, wrap="word", fg_color="transparent", width=550, height=40)
        caja.pack(padx=10, pady=(0, 10))
        caja.configure(state="disabled")
        self.widgets.append(caja)
        return caja

    def _crear_caja_codigo(self, lang=""):
        container = ctk.CTkFrame(self.bubble, fg_color="#1e1e1e", corner_radius=8)
        container.pack(padx=10, pady=5, fill="x")

        top_bar = ctk.CTkFrame(container, fg_color="#2d2d2d", height=28, corner_radius=8)
        top_bar.pack(fill="x")

        lang_label = ctk.CTkLabel(top_bar, text=lang if lang else "código", text_color="#888888", font=("Consolas", 10))
        lang_label.pack(side="left", padx=8)

        btn_copy = ctk.CTkButton(top_bar, text="📋 Copiar", width=70, height=22, font=("Arial", 10), fg_color="#444444", hover_color="#555555")
        btn_copy.pack(side="right", padx=5, pady=3)

        # Botón Ejecutar solo para Python
        if lang.lower() in ("python", "py", ""):
            btn_run = ctk.CTkButton(top_bar, text="▶ Ejecutar", width=80, height=22, font=("Arial", 10, "bold"), fg_color="#1a6b1a", hover_color="#237023")
            btn_run.pack(side="right", padx=(0, 4), pady=3)

        caja = ctk.CTkTextbox(container, wrap="none", fg_color="#1e1e1e", text_color="#9cdcfe", font=("Consolas", 12), width=530, height=40)
        caja.pack(padx=10, pady=(2, 10))
        caja.configure(state="disabled")

        btn_copy.configure(command=lambda c=caja: self._copiar(c.get("1.0", "end-1c")))

        if lang.lower() in ("python", "py", ""):
            btn_run.configure(command=lambda c=caja: self._ejecutar_python(c.get("1.0", "end-1c")))

        self.widgets.append(container)
        return caja

    def _copiar(self, texto):
        self.parent_scroll.clipboard_clear()
        self.parent_scroll.clipboard_append(texto)
        self.parent_scroll.update()

    def _ejecutar_python(self, codigo):
        if self.on_ejecutar:
            self.on_ejecutar(codigo)

    def _escribir(self, texto):
        if not texto:
            return
        self.current_box.configure(state="normal")
        self.current_box.insert("end", texto)
        self.texto_acumulado_bloque += texto

        lineas = len(self.texto_acumulado_bloque.split("\n")) + (len(self.texto_acumulado_bloque) // 80)
        self.current_box.configure(height=max(40, lineas * 20))
        self.current_box.see("end")
        self.current_box.configure(state="disabled")
        self.parent_scroll.after(10, lambda: self.parent_scroll._parent_canvas.yview_moveto(1.0))

    def procesar_stream(self, chunk):
        self.buffer += chunk
        self.texto_completo_global += chunk

        while "```" in self.buffer:
            idx = self.buffer.find("```")
            texto_previo = self.buffer[:idx]
            self._escribir(texto_previo)

            self.in_code_block = not self.in_code_block
            resto = self.buffer[idx + 3:]

            if self.in_code_block:
                # Detectar lenguaje en la misma línea
                nl = resto.find("\n")
                if nl != -1:
                    self.lang_hint = resto[:nl].strip()
                    resto = resto[nl + 1:]
                else:
                    self.lang_hint = ""
                self.current_box = self._crear_caja_codigo(self.lang_hint)
            else:
                self.current_box = self._crear_caja_texto()

            self.texto_acumulado_bloque = ""
            self.buffer = resto

        if len(self.buffer) > 2:
            texto_seguro = self.buffer[:-2]
            self.buffer = self.buffer[-2:]
            self._escribir(texto_seguro)

    def finalizar_stream(self):
        if self.buffer:
            self._escribir(self.buffer)
            self.buffer = ""
        return self.texto_completo_global


# ──────────────────────────────────────────────
# Aplicación Principal
# ──────────────────────────────────────────────
BaseClass = TkinterDnD.Tk if DRAG_DROP_DISPONIBLE else ctk.CTk

class AgenteGUI(BaseClass):
    def __init__(self):
        super().__init__()

        if DRAG_DROP_DISPONIBLE:
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("blue")

        self.title("Antigravity V7 — Centro de Mando")
        self.geometry("1250x850")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.system_prompt = DEFAULT_SYSTEM_PROMPT
        self.cargar_configuracion()

        self.mensajes = [{"role": "system", "content": self.system_prompt}]
        self.modelo_actual = "qwen2.5-coder:7b"
        self.temperatura = 0.7
        self.imagenes_adjuntas = []
        self.textos_adjuntos = []
        self.detener_generacion = False
        self.chat_actual = None
        self.tray_icon = None
        self._search_resultados = []
        self._search_idx = 0

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._construir_sidebar()
        self._construir_main()

        if DRAG_DROP_DISPONIBLE:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)

        self.bind_all("<Control-f>", lambda e: self._toggle_busqueda())
        self.bind_all("<Escape>", lambda e: self._cerrar_busqueda())

        threading.Thread(target=self.obtener_modelos, daemon=True).start()
        self._inicializar_sesiones()

        if TRAY_DISPONIBLE:
            threading.Thread(target=self._crear_tray, daemon=True).start()

    # ─────────────── SIDEBAR ───────────────
    def _construir_sidebar(self):
        self.sidebar_frame = ctk.CTkFrame(self, width=250, corner_radius=0, fg_color="#2b2b2b")
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(2, weight=1)
        self.sidebar_frame.grid_propagate(False)

        ctk.CTkLabel(self.sidebar_frame, text="⚡ Antigravity V7", font=("Arial", 18, "bold"), text_color="#4da6ff").grid(row=0, column=0, padx=20, pady=(20, 10))

        ctk.CTkButton(self.sidebar_frame, text="+ Nuevo Chat", fg_color="#1F6AA5", font=("Arial", 13, "bold"), command=self.crear_nuevo_chat).grid(row=1, column=0, padx=20, pady=8, sticky="ew")

        self.sidebar_scroll = ctk.CTkScrollableFrame(self.sidebar_frame, fg_color="transparent")
        self.sidebar_scroll.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)

        btn_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        btn_frame.grid(row=3, column=0, padx=10, pady=(0, 10), sticky="ew")
        ctk.CTkButton(btn_frame, text="⚙️ Config", fg_color="#555555", hover_color="#777777", command=self.abrir_configuracion).pack(fill="x", pady=3)
        ctk.CTkButton(btn_frame, text="💾 Exportar", fg_color="#2a5c2a", hover_color="#3a7c3a", command=self.exportar_chat).pack(fill="x", pady=3)

    # ─────────────── MAIN AREA ───────────────
    def _construir_main(self):
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(2, weight=1)

        # Top bar
        top = ctk.CTkFrame(self.main_frame, fg_color="#1e1e1e", corner_radius=0, height=50)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_propagate(False)

        ctk.CTkLabel(top, text="Modelo:", font=("Arial", 12)).pack(side="left", padx=(15, 5), pady=10)
        self.model_var = ctk.StringVar(value=self.modelo_actual)
        self.model_dropdown = ctk.CTkOptionMenu(top, variable=self.model_var, values=["Cargando..."], width=200, command=self.cambiar_modelo)
        self.model_dropdown.pack(side="left", pady=10)

        ctk.CTkLabel(top, text="Temp:", font=("Arial", 12)).pack(side="left", padx=(20, 5), pady=10)
        self.temp_slider = ctk.CTkSlider(top, from_=0.0, to=1.5, width=120, command=self._on_temp_change)
        self.temp_slider.set(self.temperatura)
        self.temp_slider.pack(side="left", pady=10)
        self.temp_label = ctk.CTkLabel(top, text=f"{self.temperatura:.1f}", font=("Consolas", 12, "bold"), text_color="#4da6ff", width=35)
        self.temp_label.pack(side="left", pady=10)

        ctk.CTkButton(top, text="🧹 Limpiar", fg_color="#d32f2f", hover_color="#b71c1c", width=90, command=self.limpiar_chat).pack(side="right", padx=10, pady=10)

        # Panel de búsqueda (oculto por defecto)
        self.search_frame = ctk.CTkFrame(self.main_frame, fg_color="#2a2a2a", height=42)
        self.search_frame.grid(row=1, column=0, sticky="ew")
        self.search_frame.grid_remove()
        self.search_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.search_frame, text="🔍", font=("Arial", 14)).grid(row=0, column=0, padx=10, pady=8)
        self.search_entry = ctk.CTkEntry(self.search_frame, placeholder_text="Buscar en el chat...", font=("Arial", 13))
        self.search_entry.grid(row=0, column=1, sticky="ew", pady=8)
        self.search_entry.bind("<Return>", lambda e: self._buscar_siguiente())
        self.search_entry.bind("<KeyRelease>", lambda e: self._realizar_busqueda())

        self.search_info = ctk.CTkLabel(self.search_frame, text="", font=("Arial", 11), text_color="gray")
        self.search_info.grid(row=0, column=2, padx=5)

        ctk.CTkButton(self.search_frame, text="▲", width=30, command=self._buscar_anterior).grid(row=0, column=3, padx=2)
        ctk.CTkButton(self.search_frame, text="▼", width=30, command=self._buscar_siguiente).grid(row=0, column=4, padx=2)
        ctk.CTkButton(self.search_frame, text="✕", width=30, fg_color="#555555", command=self._cerrar_busqueda).grid(row=0, column=5, padx=(2, 10))

        # Chat scroll
        self.chat_scroll = ctk.CTkScrollableFrame(self.main_frame)
        self.chat_scroll.grid(row=2, column=0, padx=10, pady=(5, 0), sticky="nsew")

        # Bottom bar
        bottom = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        bottom.grid(row=3, column=0, padx=10, pady=(5, 5), sticky="ew")
        bottom.grid_columnconfigure(1, weight=1)

        self.attach_btn = ctk.CTkButton(bottom, text="📎", width=42, height=42, command=self.adjuntar_archivo)
        self.attach_btn.grid(row=0, column=0, padx=(0, 8))

        self.input_entry = ctk.CTkEntry(bottom, placeholder_text="Escribe un mensaje... (o arrastra un archivo aquí)", font=("Arial", 14))
        self.input_entry.grid(row=0, column=1, sticky="ew", ipady=8)
        self.input_entry.bind("<Return>", lambda e: self.manejar_enter())

        self.send_btn = ctk.CTkButton(bottom, text="Enviar ➤", width=100, height=42, font=("Arial", 14, "bold"), command=self.enviar_mensaje)
        self.send_btn.grid(row=0, column=2, padx=(8, 0))

        # Status bar
        status_bar = ctk.CTkFrame(self.main_frame, fg_color="#1a1a1a", height=26, corner_radius=0)
        status_bar.grid(row=4, column=0, sticky="ew")
        status_bar.grid_propagate(False)
        status_bar.grid_columnconfigure(1, weight=1)

        self.status_label = ctk.CTkLabel(status_bar, text="Iniciando...", text_color="gray", font=("Arial", 10))
        self.status_label.grid(row=0, column=0, padx=10, pady=4, sticky="w")

        self.context_label = ctk.CTkLabel(status_bar, text="", font=("Consolas", 10), text_color="#4da6ff")
        self.context_label.grid(row=0, column=1, padx=10, pady=4, sticky="e")

        self.attachment_label = ctk.CTkLabel(status_bar, text="", text_color="#4da6ff", font=("Arial", 10, "bold"))
        self.attachment_label.grid(row=0, column=2, padx=5, pady=4, sticky="e")

        self.clear_attach_btn = ctk.CTkButton(status_bar, text="❌", width=22, height=18, fg_color="transparent", hover_color="#d32f2f", command=self.limpiar_adjuntos)
        self.clear_attach_btn.grid(row=0, column=3, padx=(0, 8))
        self.clear_attach_btn.grid_remove()

    # ─────────────── TEMPERATURA ───────────────
    def _on_temp_change(self, val):
        self.temperatura = round(float(val), 2)
        self.temp_label.configure(text=f"{self.temperatura:.1f}")

    # ─────────────── DRAG & DROP ───────────────
    def _on_drop(self, event):
        ruta = event.data.strip().strip("{}")
        self._procesar_archivo(ruta)

    # ─────────────── BÚSQUEDA ───────────────
    def _toggle_busqueda(self):
        if self.search_frame.winfo_ismapped():
            self._cerrar_busqueda()
        else:
            self.search_frame.grid()
            self.search_entry.focus_set()

    def _cerrar_busqueda(self):
        self.search_frame.grid_remove()
        self._search_resultados = []
        self.search_info.configure(text="")

    def _realizar_busqueda(self):
        query = self.search_entry.get().strip().lower()
        self._search_resultados = []
        self._search_idx = 0
        if not query:
            self.search_info.configure(text="")
            return
        for widget in self.chat_scroll.winfo_children():
            for child in widget.winfo_children():
                for sub in child.winfo_children():
                    if isinstance(sub, ctk.CTkTextbox):
                        contenido = sub.get("1.0", "end").lower()
                        if query in contenido:
                            self._search_resultados.append(sub)
        total = len(self._search_resultados)
        self.search_info.configure(text=f"1/{total}" if total else "Sin resultados")
        if self._search_resultados:
            self._buscar_siguiente()

    def _buscar_siguiente(self):
        if not self._search_resultados:
            return
        self._search_idx = (self._search_idx + 1) % len(self._search_resultados)
        widget = self._search_resultados[self._search_idx]
        widget.see("1.0")
        self.search_info.configure(text=f"{self._search_idx + 1}/{len(self._search_resultados)}")

    def _buscar_anterior(self):
        if not self._search_resultados:
            return
        self._search_idx = (self._search_idx - 1) % len(self._search_resultados)
        widget = self._search_resultados[self._search_idx]
        widget.see("1.0")
        self.search_info.configure(text=f"{self._search_idx + 1}/{len(self._search_resultados)}")

    # ─────────────── SYSTEM TRAY ───────────────
    def _crear_tray(self):
        try:
            img = PILImage.new("RGB", (64, 64), color="#1F6AA5")
            draw = ImageDraw.Draw(img)
            draw.ellipse((8, 8, 56, 56), fill="#4da6ff")
            draw.text((20, 18), "AG", fill="white")

            menu = pystray.Menu(
                pystray.MenuItem("Mostrar", self._mostrar_ventana, default=True),
                pystray.MenuItem("Salir", self._salir_completo),
            )
            self.tray_icon = pystray.Icon("Antigravity", img, "Antigravity V7", menu)
            self.tray_icon.run_detached()
        except Exception:
            pass

    def _on_close(self):
        if TRAY_DISPONIBLE and self.tray_icon:
            self.withdraw()
        else:
            self._salir_completo()

    def _mostrar_ventana(self, icon=None, item=None):
        self.after(0, self.deiconify)
        self.after(0, self.lift)

    def _salir_completo(self, icon=None, item=None):
        if self.tray_icon:
            self.tray_icon.stop()
        self.guardar_chat_actual()
        self.destroy()

    # ─────────────── CONTEXTO ───────────────
    def _actualizar_contador_contexto(self):
        total_chars = sum(len(str(m.get("content", ""))) for m in self.mensajes)
        total_msgs = len([m for m in self.mensajes if m["role"] != "system"])
        kb = total_chars / 1024
        color = "#4da6ff" if kb < 30 else ("#ffcc00" if kb < 60 else "#ff5555")
        self.context_label.configure(text=f"💬 {total_msgs} msgs | 📦 {kb:.1f} KB", text_color=color)

    # ─────────────── EXPORTAR ───────────────
    def exportar_chat(self):
        if not self.mensajes:
            return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre = f"chat_export_{ts}.md"
        ruta = os.path.join(WORKSPACE_DIR, nombre)
        lineas = [f"# Chat exportado — {ts}\n"]
        for m in self.mensajes:
            rol = m.get("role", "")
            if rol == "system":
                continue
            emoji = "👤 **Tú**" if rol == "user" else "🤖 **Agente**" if rol == "assistant" else "🛠️ **Herramienta**"
            lineas.append(f"\n## {emoji}\n")
            lineas.append(str(m.get("content", "")) + "\n")
        try:
            with open(ruta, "w", encoding="utf-8") as f:
                f.writelines(lineas)
            self.agregar_burbuja_simple("Sistema", f"✅ Chat exportado como:\n{nombre}", is_system=True)
        except Exception as e:
            self.agregar_burbuja_simple("Error", f"No se pudo exportar: {e}", is_system=True)

    # ─────────────── EJECUTOR PYTHON ───────────────
    def ejecutar_python_inline(self, codigo):
        def _run():
            self.agregar_burbuja_simple("▶ Ejecutando Python...", "", is_system=True)
            try:
                with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
                    tmp.write(codigo)
                    tmp_path = tmp.name
                resultado = subprocess.run(
                    [sys.executable, tmp_path],
                    capture_output=True, text=True, timeout=30, cwd=WORKSPACE_DIR
                )
                os.unlink(tmp_path)
                salida = resultado.stdout or ""
                errores = resultado.stderr or ""
                output = salida
                if errores:
                    output += f"\n⚠️ STDERR:\n{errores}"
                if not output.strip():
                    output = "(Sin salida)"
                self.agregar_burbuja_simple("🐍 Resultado Python", output[:3000], is_system=True)
            except subprocess.TimeoutExpired:
                self.agregar_burbuja_simple("⏱️ Timeout", "El script tardó más de 30 segundos.", is_system=True)
            except Exception as e:
                self.agregar_burbuja_simple("Error Python", str(e), is_system=True)
        threading.Thread(target=_run, daemon=True).start()

    # ─────────────── SESIONES ───────────────
    def _inicializar_sesiones(self):
        viejo = os.path.join(WORKSPACE_DIR, "historial.json")
        if os.path.exists(viejo):
            try:
                with open(viejo, "r", encoding="utf-8") as f:
                    v_data = json.load(f)
                nid = str(uuid.uuid4())
                with open(os.path.join(SESSION_DIR, f"{nid}.json"), "w", encoding="utf-8") as f:
                    json.dump({"metadata": {"titulo": "Chat Migrado", "is_pinned": False, "fecha": datetime.datetime.now().isoformat()}, "mensajes": v_data}, f, ensure_ascii=False, indent=4)
                os.remove(viejo)
            except Exception:
                pass

        archivos = [os.path.join(SESSION_DIR, f) for f in os.listdir(SESSION_DIR) if f.endswith(".json")]
        if archivos:
            ultimo = max(archivos, key=os.path.getmtime)
            self.cargar_chat(os.path.basename(ultimo).replace(".json", ""))
        else:
            self.crear_nuevo_chat()

    def crear_nuevo_chat(self):
        self.chat_actual = str(uuid.uuid4())
        self.mensajes = [{"role": "system", "content": self.system_prompt}]
        self.reconstruir_ui_chat()
        self.guardar_chat_actual(titulo="Nueva Conversación")
        self.cargar_lista_sidebar()
        self._actualizar_contador_contexto()

    def cargar_chat(self, chat_id):
        ruta = os.path.join(SESSION_DIR, f"{chat_id}.json")
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.mensajes = data.get("mensajes", [])
            self.chat_actual = chat_id
            self.reconstruir_ui_chat()
            self.cargar_lista_sidebar()
            self._actualizar_contador_contexto()
        except Exception as e:
            self.agregar_burbuja_simple("Error", f"Fallo al cargar sesión: {e}", is_system=True)

    def guardar_chat_actual(self, titulo=None, is_pinned=None):
        if not self.chat_actual:
            self.chat_actual = str(uuid.uuid4())
        ruta = os.path.join(SESSION_DIR, f"{self.chat_actual}.json")
        metadata = {"titulo": "Nueva Conversación", "is_pinned": False, "fecha": datetime.datetime.now().isoformat()}
        if os.path.exists(ruta):
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    old = json.load(f)
                metadata = old.get("metadata", metadata)
            except Exception:
                pass
        if titulo is not None:
            metadata["titulo"] = titulo
        if is_pinned is not None:
            metadata["is_pinned"] = is_pinned
        if metadata["titulo"] == "Nueva Conversación":
            for m in self.mensajes:
                if m["role"] == "user":
                    txt = m.get("content", "")
                    if txt and not txt.startswith("[SISTEMA"):
                        metadata["titulo"] = " ".join(txt.split()[:5]) + "..."
                        break
        try:
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump({"metadata": metadata, "mensajes": self.mensajes}, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

    def borrar_chat(self, chat_id):
        ruta = os.path.join(SESSION_DIR, f"{chat_id}.json")
        if os.path.exists(ruta):
            os.remove(ruta)
        if self.chat_actual == chat_id:
            self.crear_nuevo_chat()
        else:
            self.cargar_lista_sidebar()

    def cargar_lista_sidebar(self):
        for w in self.sidebar_scroll.winfo_children():
            w.destroy()
        archivos = [f for f in os.listdir(SESSION_DIR) if f.endswith(".json")]
        chats = []
        for arch in archivos:
            try:
                with open(os.path.join(SESSION_DIR, arch), "r", encoding="utf-8") as f:
                    data = json.load(f)
                meta = data.get("metadata", {})
                chats.append({"id": arch.replace(".json", ""), "titulo": meta.get("titulo", "Chat"), "is_pinned": meta.get("is_pinned", False), "fecha": meta.get("fecha", "")})
            except Exception:
                pass
        chats.sort(key=lambda x: (x["is_pinned"], x["fecha"]), reverse=True)

        for c in chats:
            es_actual = self.chat_actual == c["id"]
            bg = "#1F6AA5" if es_actual else "transparent"
            hover = "#2a7fc4" if es_actual else "#3a3a3a"

            row = ctk.CTkFrame(self.sidebar_scroll, fg_color=bg, corner_radius=6)
            row.pack(fill="x", pady=2)

            titulo_corto = c["titulo"][:21] + "…" if len(c["titulo"]) > 22 else c["titulo"]
            prefix = "📌 " if c["is_pinned"] else ""
            lbl = ctk.CTkLabel(row, text=prefix + titulo_corto, anchor="w", font=("Arial", 11))
            lbl.pack(side="left", fill="x", expand=True, padx=10, pady=7)

            def on_click(e, cid=c["id"]):
                self.cargar_chat(cid)
            lbl.bind("<Button-1>", on_click)
            row.bind("<Enter>", lambda e, r=row, h=hover: r.configure(fg_color=h))
            row.bind("<Leave>", lambda e, r=row, b=bg: r.configure(fg_color=b))
            lbl.bind("<Enter>", lambda e, r=row, h=hover: r.configure(fg_color=h))
            lbl.bind("<Leave>", lambda e, r=row, b=bg: r.configure(fg_color=b))

            def toggle_pin(cid=c["id"], pin=c["is_pinned"]):
                ruta_p = os.path.join(SESSION_DIR, f"{cid}.json")
                try:
                    with open(ruta_p, "r", encoding="utf-8") as f:
                        d = json.load(f)
                    d["metadata"]["is_pinned"] = not pin
                    with open(ruta_p, "w", encoding="utf-8") as f:
                        json.dump(d, f, ensure_ascii=False, indent=4)
                    self.cargar_lista_sidebar()
                except Exception:
                    pass

            pin_btn = ctk.CTkButton(row, text="📌" if c["is_pinned"] else "☆", width=26, height=26, fg_color="transparent", text_color="#aaaaaa", command=lambda cid=c["id"], p=c["is_pinned"]: toggle_pin(cid, p))
            pin_btn.pack(side="right", padx=(0, 4))

            if not c["is_pinned"]:
                del_btn = ctk.CTkButton(row, text="🗑", width=26, height=26, fg_color="transparent", hover_color="#8b0000", command=lambda cid=c["id"]: self.borrar_chat(cid))
                del_btn.pack(side="right")

    # ─────────────── CONFIGURACIÓN ───────────────
    def cargar_configuracion(self):
        ruta = os.path.join(WORKSPACE_DIR, "config.json")
        if os.path.exists(ruta):
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "system_prompt" in data:
                    self.system_prompt = data["system_prompt"]
                if "temperatura" in data:
                    self.temperatura = data["temperatura"]
            except Exception:
                pass

    def abrir_configuracion(self):
        win = ctk.CTkToplevel(self)
        win.title("Configuración del Agente")
        win.geometry("620x450")
        win.attributes("-topmost", True)

        ctk.CTkLabel(win, text="Instrucciones del Sistema (Personalidad/Reglas):", font=("Arial", 12, "bold")).pack(pady=(15, 5), padx=15, anchor="w")
        caja = ctk.CTkTextbox(win, width=590, height=300, wrap="word")
        caja.pack(padx=15, pady=5)
        caja.insert("1.0", self.system_prompt)

        def guardar():
            self.system_prompt = caja.get("1.0", "end").strip()
            if self.mensajes and self.mensajes[0].get("role") == "system":
                self.mensajes[0]["content"] = self.system_prompt
            try:
                with open(os.path.join(WORKSPACE_DIR, "config.json"), "w", encoding="utf-8") as f:
                    json.dump({"system_prompt": self.system_prompt, "temperatura": self.temperatura}, f, ensure_ascii=False, indent=4)
                self.agregar_burbuja_simple("Sistema", "✅ Configuración actualizada.", is_system=True)
                self.guardar_chat_actual()
            except Exception as e:
                self.agregar_burbuja_simple("Error", f"Error guardando config: {e}", is_system=True)
            win.destroy()

        ctk.CTkButton(win, text="💾 Guardar Cambios", command=guardar).pack(pady=12)

    # ─────────────── UI CHAT ───────────────
    def reconstruir_ui_chat(self):
        for w in self.chat_scroll.winfo_children():
            w.destroy()
        for m in self.mensajes:
            if m["role"] == "user":
                texto = m.get("content", "")
                if "[SISTEMA:" in texto:
                    texto = "[📄 Documento adjunto en memoria]"
                self.agregar_burbuja_simple("👤 Tú", texto, is_user=True)
            elif m["role"] == "assistant":
                b = BurbujaStreaming(self.chat_scroll, "🤖 Agente", "#2b2b3b", on_ejecutar=self.ejecutar_python_inline)
                b.procesar_stream(m.get("content", ""))
                b.finalizar_stream()
            elif m["role"] == "tool":
                self.agregar_burbuja_simple("🛠️ Herramienta", m.get("content", ""), is_system=True)

    def agregar_burbuja_simple(self, remitente, texto, is_user=False, is_system=False):
        bg = "#1f538d" if is_user else ("#2b2b3b" if not is_system else "#383838")
        b = BurbujaStreaming(self.chat_scroll, remitente, bg, is_user, on_ejecutar=self.ejecutar_python_inline)
        b.procesar_stream(texto)
        b.finalizar_stream()

    def set_status(self, text):
        self.status_label.configure(text=text)

    def cambiar_modelo(self, nuevo):
        self.modelo_actual = nuevo
        self.agregar_burbuja_simple("Sistema", f"Modelo → {nuevo}", is_system=True)

    def limpiar_chat(self):
        self.mensajes = [{"role": "system", "content": self.system_prompt}]
        self.limpiar_adjuntos()
        self.reconstruir_ui_chat()
        self.guardar_chat_actual()
        self._actualizar_contador_contexto()
        self.agregar_burbuja_simple("Sistema", "🧹 Memoria de esta sesión limpiada.", is_system=True)

    def limpiar_adjuntos(self):
        self.imagenes_adjuntas = []
        self.textos_adjuntos = []
        self._actualizar_label_adjuntos()

    def _actualizar_label_adjuntos(self):
        partes = []
        if self.imagenes_adjuntas:
            partes.append(f"🖼️ {len(self.imagenes_adjuntas)} img")
        if self.textos_adjuntos:
            partes.append(f"📄 {len(self.textos_adjuntos)} doc")
        if partes:
            self.attachment_label.configure(text=" + ".join(partes))
            self.clear_attach_btn.grid()
        else:
            self.attachment_label.configure(text="")
            self.clear_attach_btn.grid_remove()

    def obtener_modelos(self):
        try:
            r = requests.get(f"{OLLAMA_URL}/tags", timeout=10)
            if r.status_code == 200:
                modelos = [m["name"] for m in r.json().get("models", [])]
                if modelos:
                    self.model_dropdown.configure(values=modelos)
                    if self.modelo_actual not in modelos:
                        self.model_var.set(modelos[0])
                        self.modelo_actual = modelos[0]
                    else:
                        self.model_var.set(self.modelo_actual)
                    self.set_status(f"✅ {len(modelos)} modelos disponibles.")
                else:
                    self.set_status("⚠️ Sin modelos en Ollama.")
            else:
                self.set_status(f"❌ Error Ollama: {r.status_code}")
        except Exception:
            self.set_status("❌ Ollama no está ejecutándose.")

    # ─────────────── ADJUNTOS ───────────────
    def adjuntar_archivo(self):
        archivo = filedialog.askopenfilename(title="Seleccionar archivo")
        if archivo:
            self._procesar_archivo(archivo)

    def _procesar_archivo(self, archivo):
        ext = archivo.rsplit(".", 1)[-1].lower()
        if ext in ("png", "jpg", "jpeg", "bmp", "webp"):
            try:
                with open(archivo, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                self.imagenes_adjuntas.append(b64)
                self._actualizar_label_adjuntos()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo leer la imagen: {e}")
        elif ext == "pdf":
            try:
                with open(archivo, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    texto = "".join(p.extract_text() or "" for p in reader.pages)
                if not texto.strip():
                    return messagebox.showwarning("Aviso", "PDF vacío o escaneado.")
                self.textos_adjuntos.append({"nombre": os.path.basename(archivo), "contenido": texto.strip()})
                self._actualizar_label_adjuntos()
            except Exception as e:
                messagebox.showerror("Error", f"Fallo al leer PDF: {e}")
        elif ext in ("docx", "doc"):
            try:
                doc = docx.Document(archivo)
                texto = "\n".join(p.text for p in doc.paragraphs)
                if not texto.strip():
                    return messagebox.showwarning("Aviso", "Word vacío.")
                self.textos_adjuntos.append({"nombre": os.path.basename(archivo), "contenido": texto.strip()})
                self._actualizar_label_adjuntos()
            except Exception as e:
                messagebox.showerror("Error", f"Fallo al leer Word: {e}")
        else:
            try:
                with open(archivo, "r", encoding="utf-8") as f:
                    texto = f.read()
                self.textos_adjuntos.append({"nombre": os.path.basename(archivo), "contenido": texto.strip()})
                self._actualizar_label_adjuntos()
            except UnicodeDecodeError:
                messagebox.showerror("Formato", "Archivo binario o inválido.")
            except Exception as e:
                messagebox.showerror("Error", f"Error al leer: {e}")

    # ─────────────── HERRAMIENTAS ───────────────
    def ejecutar_comando(self, comando: str) -> str:
        self.agregar_burbuja_simple("🛠️ PowerShell", f"`{comando}`", is_system=True)
        try:
            proc = subprocess.Popen(["powershell", "-Command", comando], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=WORKSPACE_DIR)
            out, err = proc.communicate(timeout=30)
            if err:
                out += f"\nErrores:\n{err}"
            return (out[:2000] + "\n…[Truncada]") if len(out) > 2000 else (out if out.strip() else "Sin salida.")
        except Exception as e:
            return f"Error: {e}"

    def buscar_en_internet(self, query: str) -> str:
        self.agregar_burbuja_simple("🛠️ Web Search", query, is_system=True)
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=3))
            if not results:
                return "Sin resultados."
            return "".join(f"Título: {r['title']}\nURL: {r['href']}\nResumen: {r['body']}\n\n" for r in results)
        except Exception as e:
            return f"Error: {e}"

    def leer_pagina_web(self, url: str) -> str:
        self.agregar_burbuja_simple("🛠️ Leyendo URL", url, is_system=True)
        try:
            r = requests.get(url, timeout=15)
            texto = BeautifulSoup(r.text, "html.parser").get_text(separator="\n", strip=True)
            return texto[:3000] + ("\n…[Truncado]" if len(texto) > 3000 else "")
        except Exception as e:
            return f"Error: {e}"

    def listar_directorio(self, ruta: str = "") -> str:
        target = os.path.join(WORKSPACE_DIR, ruta)
        self.agregar_burbuja_simple("🛠️ Listando", ruta or "Workspace/", is_system=True)
        try:
            items = os.listdir(target)
            return "\n".join(items) if items else "Carpeta vacía."
        except Exception as e:
            return f"Error: {e}"

    def leer_archivo(self, nombre_archivo: str) -> str:
        ruta = os.path.join(WORKSPACE_DIR, nombre_archivo)
        self.agregar_burbuja_simple("🛠️ Leyendo archivo", nombre_archivo, is_system=True)
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                c = f.read()
            return (c[:3000] + "\n…[Truncado]") if len(c) > 3000 else c
        except Exception as e:
            return f"Error: {e}"

    def escribir_archivo(self, nombre_archivo: str, contenido: str) -> str:
        ruta = os.path.join(WORKSPACE_DIR, nombre_archivo)
        self.agregar_burbuja_simple("🛠️ Escribiendo", nombre_archivo, is_system=True)
        try:
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(contenido)
            return "✅ Archivo guardado."
        except Exception as e:
            return f"Error: {e}"

    # ─────────────── MOTOR PRINCIPAL ───────────────
    def manejar_enter(self):
        if self.send_btn.cget("text") == "Enviar ➤":
            self.enviar_mensaje()

    def parar_generacion(self):
        self.detener_generacion = True
        self.send_btn.configure(text="Deteniendo…", state="disabled")

    def enviar_mensaje(self):
        texto_usuario = self.input_entry.get().strip()
        if not texto_usuario and not self.imagenes_adjuntas and not self.textos_adjuntos:
            return
        self.input_entry.delete(0, "end")

        texto_ollama = texto_usuario
        texto_ui = texto_usuario or "[Adjunto sin texto]"

        if self.textos_adjuntos:
            texto_ui = f"[📄 Docs] {texto_ui}"
            for doc in self.textos_adjuntos:
                texto_ollama += f"\n\n[SISTEMA: Archivo '{doc['nombre']}']\n{doc['contenido']}\n[FIN {doc['nombre']}]\n"
        if self.imagenes_adjuntas:
            texto_ui = f"[🖼️ Imagen] {texto_ui}"

        msj = {"role": "user", "content": texto_ollama.strip()}
        if self.imagenes_adjuntas:
            msj["images"] = self.imagenes_adjuntas.copy()

        self.agregar_burbuja_simple("👤 Tú", texto_ui, is_user=True)
        self.mensajes.append(msj)
        self.guardar_chat_actual()
        self.cargar_lista_sidebar()
        self.limpiar_adjuntos()
        self._actualizar_contador_contexto()

        self.attach_btn.configure(state="disabled")
        self.detener_generacion = False
        self.send_btn.configure(text="🛑 Detener", fg_color="#d32f2f", hover_color="#b71c1c", command=self.parar_generacion)
        threading.Thread(target=self.procesar_agente_en_hilo, daemon=True).start()

    def procesar_agente_en_hilo(self):
        max_iter = 10
        itr = 0
        try:
            while itr < max_iter and not self.detener_generacion:
                itr += 1
                self.set_status("🧠 Pensando...")

                payload_msgs = self.mensajes.copy()
                if payload_msgs and payload_msgs[0]["role"] == "system":
                    try:
                        archivos = [a for a in os.listdir(WORKSPACE_DIR) if a not in ("historial.json", "config.json", "sesiones")]
                        if archivos:
                            inject = "\n\n[INFO SISTEMA] Archivos en Workspace:\n- " + "\n- ".join(archivos)
                            sys_cpy = payload_msgs[0].copy()
                            sys_cpy["content"] += inject
                            payload_msgs[0] = sys_cpy
                    except Exception:
                        pass

                payload = {
                    "model": self.modelo_actual,
                    "messages": payload_msgs,
                    "stream": True,
                    "tools": TOOLS,
                    "options": {"temperature": self.temperatura}
                }

                # Pre-check sin stream para detectar errores
                check = payload.copy()
                check["stream"] = False
                try:
                    test = requests.post(f"{OLLAMA_URL}/chat", json=check, timeout=900)
                    if test.status_code != 200:
                        err_msg = ""
                        try:
                            err_msg = test.json().get("error", "")
                        except Exception:
                            pass
                        retry = False
                        if "does not support tools" in str(err_msg):
                            del payload["tools"]
                            retry = True
                        if "Multimodal data provided" in str(err_msg):
                            for m in payload["messages"]:
                                m.pop("images", None)
                            retry = True
                        if not retry:
                            self.agregar_burbuja_simple("Error", f"Ollama: {test.text}", is_system=True)
                            break
                except Exception:
                    pass

                if self.detener_generacion:
                    break

                resp = requests.post(f"{OLLAMA_URL}/chat", json=payload, stream=True, timeout=900)
                if resp.status_code != 200:
                    self.agregar_burbuja_simple("Error", f"Ollama stream: {resp.text}", is_system=True)
                    break

                self.set_status("✍️ Escribiendo...")
                burbuja = BurbujaStreaming(self.chat_scroll, "🤖 Agente", "#2b2b3b", on_ejecutar=self.ejecutar_python_inline)
                tool_calls = []

                for line in resp.iter_lines():
                    if self.detener_generacion:
                        break
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        msg = chunk.get("message", {})
                        if msg.get("content"):
                            burbuja.procesar_stream(msg["content"])
                        if "tool_calls" in msg:
                            tool_calls = msg["tool_calls"]

                texto_completo = burbuja.finalizar_stream()

                if self.detener_generacion:
                    burbuja.procesar_stream("\n\n[🛑 Detenido]")
                    burbuja.finalizar_stream()

                if tool_calls and not self.detener_generacion:
                    self.mensajes.append({"role": "assistant", "content": texto_completo, "tool_calls": tool_calls})
                    for tc in tool_calls:
                        if self.detener_generacion:
                            break
                        fn = tc["function"]["name"]
                        args = tc["function"].get("arguments", {})
                        res = "Función no encontrada."
                        if fn == "ejecutar_comando":       res = self.ejecutar_comando(args.get("comando", ""))
                        elif fn == "buscar_en_internet":   res = self.buscar_en_internet(args.get("query", ""))
                        elif fn == "leer_pagina_web":      res = self.leer_pagina_web(args.get("url", ""))
                        elif fn == "listar_directorio":    res = self.listar_directorio(args.get("ruta", ""))
                        elif fn == "leer_archivo":         res = self.leer_archivo(args.get("nombre_archivo", ""))
                        elif fn == "escribir_archivo":     res = self.escribir_archivo(args.get("nombre_archivo", ""), args.get("contenido", ""))
                        self.mensajes.append({"role": "tool", "content": str(res)})
                else:
                    self.mensajes.append({"role": "assistant", "content": texto_completo})
                    self.guardar_chat_actual()
                    self.cargar_lista_sidebar()
                    self.set_status("✅ Listo.")
                    break

            if itr >= max_iter and not self.detener_generacion:
                self.agregar_burbuja_simple("Sistema", "⚠️ Límite de iteraciones alcanzado.", is_system=True)
                self.set_status("⚠️ Detenido por límite.")
        except Exception as e:
            self.agregar_burbuja_simple("Error", str(e), is_system=True)
            self.set_status("❌ Error.")
        finally:
            self._actualizar_contador_contexto()
            self.guardar_chat_actual()
            self.cargar_lista_sidebar()
            self.detener_generacion = False
            self.attach_btn.configure(state="normal")
            default_color = ctk.ThemeManager.theme["CTkButton"]["fg_color"]
            hover_color = ctk.ThemeManager.theme["CTkButton"]["hover_color"]
            self.send_btn.configure(text="Enviar ➤", state="normal", fg_color=default_color, hover_color=hover_color, command=self.enviar_mensaje)


if __name__ == "__main__":
    app = AgenteGUI()
    app.mainloop()
