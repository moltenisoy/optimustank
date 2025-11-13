# gestor_gui.py
"""
GUI profesional avanzada con tkinter, métricas en tiempo real, tray y dashboard.
"""
import threading
import sys
import platform
from base_gestor import BaseGestor
from typing import Dict, Callable, List
from datetime import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from tkinter import font as tkfont
import queue

try:
    import pystray
    from pystray import Icon, MenuItem, Menu
    from PIL import Image, ImageDraw
    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False

try:
    from win10toast import ToastNotifier
    HAS_TOAST = True
except ImportError:
    HAS_TOAST = False

class GUIManager(BaseGestor):
    def __init__(self):
        super().__init__("GestorGUI", intervalo_ejecucion=1)
        
        if not platform.machine().endswith('64'):
            sys.exit("Esta aplicación requiere arquitecturas x64 (64 bits).")
        
        self.root = tk.Tk()
        self.root.title("Optimizador de Sistema Avanzado v2.0")
        self.root.geometry("1200x700")
        self.root.withdraw()
        
        self.theme = self.config.get('gui.theme', 'dark')
        self.animaciones_habilitadas = self.config.get('gui.animaciones_habilitadas', True)
        self.graficar_metricas = self.config.get('gui.graficar_metricas', True)
        
        self.notifier = ToastNotifier() if HAS_TOAST else None
        self.icon = self._create_tray_icon() if HAS_PYSTRAY else None
        
        self.cola_eventos = queue.Queue()
        self.info_text = None
        self.eventos_text = None
        self.metricas_labels = {}
        self.graficos = {}
        
        self._setup_theme()
        self._build_gui()
        
        self.logger.info("GUIManager inicializado")
    
    def _setup_theme(self):
        """Configura tema visual profesional."""
        style = ttk.Style()
        style.theme_use('clam')
        
        if self.theme == "dark":
            bg_color = '#1e1e1e'
            fg_color = '#ffffff'
            accent = '#0078d4'
            
            style.configure('TFrame', background=bg_color, foreground=fg_color)
            style.configure('TLabel', background=bg_color, foreground=fg_color)
            style.configure('TButton', background=accent, foreground=fg_color)
            style.configure('TNotebook', background=bg_color)
            style.configure('TNotebook.Tab', padding=[20, 10])
            
            self.bg_color = bg_color
            self.fg_color = fg_color
            self.accent = accent
        else:
            self.bg_color = '#ffffff'
            self.fg_color = '#000000'
            self.accent = '#0078d4'
    
    def _create_image(self, width=64, height=64):
        """Crea imagen para icono de bandeja."""
        image = Image.new('RGB', (width, height), '#0078d4')
        draw = ImageDraw.Draw(image)
        draw.rectangle((10, 10, 54, 54), outline='#ffffff', width=2)
        draw.ellipse((25, 25, 39, 39), fill='#ffffff')
        return image
    
    def _create_tray_icon(self):
        """Crea icono en bandeja del sistema."""
        if not HAS_PYSTRAY:
            return None
        
        try:
            image = Image.open("1.ico")
        except FileNotFoundError:
            image = self._create_image()

        menu = Menu(
            MenuItem('Modo Juego', self._toggle_game_mode),
            MenuItem('Configuracion', self._open_settings_window),
            MenuItem('-'),
            MenuItem('Cerrar Asistente', self._exit_app)
        )
        
        return Icon("OptimizadorSistema", image, "Optimizador de Sistema", menu=menu)

    def _toggle_game_mode(self):
        pass

    def _open_settings_window(self):
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Configuración")
        settings_window.geometry("600x400")

        notebook = ttk.Notebook(settings_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Whitelist Tab
        whitelist_frame = ttk.Frame(notebook)
        notebook.add(whitelist_frame, text="Whitelist")
        self._build_whitelist_tab(whitelist_frame)

        # Game List Tab
        game_list_frame = ttk.Frame(notebook)
        notebook.add(game_list_frame, text="Game List")
        self._build_game_list_tab(game_list_frame)

        # Thermal Throttling Tab
        thermal_frame = ttk.Frame(notebook)
        notebook.add(thermal_frame, text="Thermal Throttling")
        self._build_thermal_tab(thermal_frame)
    
    def _build_whitelist_tab(self, parent):
        label = ttk.Label(parent, text="Processes to ignore:")
        label.pack(pady=5)

        self.whitelist_listbox = tk.Listbox(parent)
        self.whitelist_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        for process in self.config.get('gui.whitelist', []):
            self.whitelist_listbox.insert(tk.END, process)

        button_frame = ttk.Frame(parent)
        button_frame.pack(fill=tk.X, padx=5, pady=5)

        add_button = ttk.Button(button_frame, text="Add", command=self._add_to_whitelist)
        add_button.pack(side=tk.LEFT, padx=5)

        remove_button = ttk.Button(button_frame, text="Remove", command=self._remove_from_whitelist)
        remove_button.pack(side=tk.LEFT, padx=5)

    def _add_to_whitelist(self):
        pass

    def _remove_from_whitelist(self):
        pass

    def _build_game_list_tab(self, parent):
        label = ttk.Label(parent, text="Games for special treatment:")
        label.pack(pady=5)

        self.game_list_listbox = tk.Listbox(parent)
        self.game_list_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        for game in self.config.get('gui.game_list', []):
            self.game_list_listbox.insert(tk.END, game)

        button_frame = ttk.Frame(parent)
        button_frame.pack(fill=tk.X, padx=5, pady=5)

        add_button = ttk.Button(button_frame, text="Add", command=self._add_to_game_list)
        add_button.pack(side=tk.LEFT, padx=5)

        remove_button = ttk.Button(button_frame, text="Remove", command=self._remove_from_game_list)
        remove_button.pack(side=tk.LEFT, padx=5)

    def _add_to_game_list(self):
        pass

    def _remove_from_game_list(self):
        pass

    def _build_thermal_tab(self, parent):
        # Show temperature in tray
        self.show_temp_var = tk.BooleanVar(value=self.config.get('gui.show_temp_in_tray', False))
        show_temp_check = ttk.Checkbutton(parent, text="Show temperature in system tray", variable=self.show_temp_var, command=self._update_config)
        show_temp_check.pack(pady=5)

        # Monitoring interval
        interval_frame = ttk.Frame(parent)
        interval_frame.pack(fill=tk.X, padx=5, pady=5)
        interval_label = ttk.Label(interval_frame, text="Monitoring interval (seconds):")
        interval_label.pack(side=tk.LEFT, padx=5)
        self.interval_var = tk.StringVar(value=self.config.get('thermal_throttling.monitoring_interval', 1))
        interval_entry = ttk.Entry(interval_frame, textvariable=self.interval_var)
        interval_entry.pack(side=tk.LEFT, padx=5)

        # Soft threshold
        soft_threshold_frame = ttk.Frame(parent)
        soft_threshold_frame.pack(fill=tk.X, padx=5, pady=5)
        soft_threshold_label = ttk.Label(soft_threshold_frame, text="Soft throttling threshold (°C):")
        soft_threshold_label.pack(side=tk.LEFT, padx=5)
        self.soft_threshold_var = tk.StringVar(value=self.config.get('thermal_throttling.soft_threshold', 70))
        soft_threshold_entry = ttk.Entry(soft_threshold_frame, textvariable=self.soft_threshold_var)
        soft_threshold_entry.pack(side=tk.LEFT, padx=5)

        # Aggressive threshold
        aggressive_threshold_frame = ttk.Frame(parent)
        aggressive_threshold_frame.pack(fill=tk.X, padx=5, pady=5)
        aggressive_threshold_label = ttk.Label(aggressive_threshold_frame, text="Aggressive throttling threshold (°C):")
        aggressive_threshold_label.pack(side=tk.LEFT, padx=5)
        self.aggressive_threshold_var = tk.StringVar(value=self.config.get('thermal_throttling.aggressive_threshold', 75))
        aggressive_threshold_entry = ttk.Entry(aggressive_threshold_frame, textvariable=self.aggressive_threshold_var)
        aggressive_threshold_entry.pack(side=tk.LEFT, padx=5)

        # Save button
        save_button = ttk.Button(parent, text="Save", command=self._update_config)
        save_button.pack(pady=10)

    def _update_config(self):
        self.config.set('gui.show_temp_in_tray', self.show_temp_var.get())
        self.config.set('thermal_throttling.monitoring_interval', int(self.interval_var.get()))
        self.config.set('thermal_throttling.soft_threshold', int(self.soft_threshold_var.get()))
        self.config.set('thermal_throttling.aggressive_threshold', int(self.aggressive_threshold_var.get()))
        messagebox.showinfo("Configuración", "Configuración guardada.")

    def _build_gui(self):
        """Construye interfaz gráfica profesional."""
        # Frame principal con padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Título
        title_font = tkfont.Font(family="Helvetica", size=16, weight="bold")
        title = ttk.Label(main_frame, text="Optimizador de Sistema - Dashboard", 
                         font=title_font)
        title.pack(pady=10)
        
        # Notebook (pestañas)
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Tab 1: Dashboard en tiempo real
        frame_dashboard = ttk.Frame(notebook)
        notebook.add(frame_dashboard, text="📊 Dashboard")
        self._build_dashboard_tab(frame_dashboard)
        
        # Tab 2: Métricas detalladas
        frame_metricas = ttk.Frame(notebook)
        notebook.add(frame_metricas, text="📈 Métricas")
        self._build_metricas_tab(frame_metricas)
        
        # Tab 3: Eventos
        frame_eventos = ttk.Frame(notebook)
        notebook.add(frame_eventos, text="📋 Eventos")
        self._build_eventos_tab(frame_eventos)
        
        # Tab 4: Control
        frame_control = ttk.Frame(notebook)
        notebook.add(frame_control, text="⚙️ Control")
        self._build_control_tab(frame_control)
        
        # Tab 5: Configuración
        frame_config = ttk.Frame(notebook)
        notebook.add(frame_config, text="🔧 Configuración")
        self._build_config_tab(frame_config)
        
        # Barra de estado
        self.status_bar = ttk.Label(self.root, text="Sistema optimizado ✓", 
                                    relief=tk.SUNKEN)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Barra de herramientas
        toolbar = ttk.Frame(main_frame)
        toolbar.pack(fill=tk.X, pady=5)
        
        ttk.Button(toolbar, text="▶ Optimizar Ahora", 
                  command=self._iniciar_optimizacion).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="⏸ Pausar", 
                  command=self._pausar_optimizacion).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="↻ Actualizar", 
                  command=self._actualizar_metricas).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="💾 Guardar Diagnóstico", 
                  command=self._guardar_diagnostico).pack(side=tk.LEFT, padx=5)
    
    def _build_dashboard_tab(self, parent):
        """Construye tab de dashboard en tiempo real."""
        # Frame para métricas principales
        metricas_frame = ttk.LabelFrame(parent, text="Métricas del Sistema", padding=10)
        metricas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Grid de métricas
        metricas = [
            ('cpu_uso', 'CPU Uso', '%'),
            ('memoria_uso', 'Memoria', '%'),
            ('gpu_uso', 'GPU Uso', '%'),
            ('temperatura_cpu', 'Temp CPU', '°C'),
            ('latencia_red', 'Latencia Red', 'ms'),
            ('procesos_activos', 'Procesos', '#')
        ]
        
        for row, (key, label, unidad) in enumerate(metricas):
            ttk.Label(metricas_frame, text=label + ":").grid(row=row, column=0, sticky="w")
            
            self.metricas_labels[key] = ttk.Label(metricas_frame, text="--", 
                                                  foreground=self.accent)
            self.metricas_labels[key].grid(row=row, column=1, sticky="e")
            
            ttk.Label(metricas_frame, text=unidad).grid(row=row, column=2, sticky="w")
        
        # Frame para estado de módulos
        modulos_frame = ttk.LabelFrame(parent, text="Estado de Módulos", padding=10)
        modulos_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        modulos = ['CPU', 'Memoria', 'GPU', 'Redes', 'Kernel', 'Tareas']
        
        for idx, modulo in enumerate(modulos):
            row = idx // 3
            col = idx % 3
            
            frame = ttk.Frame(modulos_frame)
            frame.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)
            
            ttk.Label(frame, text=modulo, font=("Helvetica", 10, "bold")).pack()
            
            self.metricas_labels[f'estado_{modulo}'] = ttk.Label(
                frame, text="✓ Activo", foreground="green"
            )
            self.metricas_labels[f'estado_{modulo}'].pack()
    
    def _build_metricas_tab(self, parent):
        """Construye tab de métricas detalladas."""
        frame_metricas = ttk.LabelFrame(parent, text="Histórico de Métricas", padding=10)
        frame_metricas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.metricas_text = scrolledtext.ScrolledText(frame_metricas, height=20, width=100)
        self.metricas_text.pack(fill=tk.BOTH, expand=True)
        self.metricas_text.config(state=tk.DISABLED)
    
    def _build_eventos_tab(self, parent):
        """Construye tab de eventos."""
        frame_eventos = ttk.LabelFrame(parent, text="Registro de Eventos", padding=10)
        frame_eventos.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Botones de filtro
        filter_frame = ttk.Frame(frame_eventos)
        filter_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(filter_frame, text="Todos").pack(side=tk.LEFT, padx=5)
        ttk.Button(filter_frame, text="Errores").pack(side=tk.LEFT, padx=5)
        ttk.Button(filter_frame, text="Advertencias").pack(side=tk.LEFT, padx=5)
        ttk.Button(filter_frame, text="Info").pack(side=tk.LEFT, padx=5)
        
        self.eventos_text = scrolledtext.ScrolledText(frame_eventos, height=20, width=100)
        self.eventos_text.pack(fill=tk.BOTH, expand=True)
        self.eventos_text.config(state=tk.DISABLED)
    
    def _build_control_tab(self, parent):
        """Construye tab de controles."""
        frame_botones = ttk.LabelFrame(parent, text="Acciones Rápidas", padding=10)
        frame_botones.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(frame_botones, text="🧹 Liberar Memoria", 
                  command=self._liberar_memoria).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_botones, text="💾 Optimizar Disco", 
                  command=self._optimizar_disco).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_botones, text="🌐 Limpiar DNS", 
                  command=self._limpiar_dns).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_botones, text="🔄 Reiniciar Servicios", 
                  command=self._reiniciar_servicios).pack(side=tk.LEFT, padx=5)
        
        frame_config = ttk.LabelFrame(parent, text="Configuración del Sistema", padding=10)
        frame_config.pack(fill=tk.X, padx=5, pady=5)
        
        self.var_agresivo = tk.BooleanVar()
        ttk.Checkbutton(frame_config, text="Modo Agresivo", 
                       variable=self.var_agresivo).pack(anchor=tk.W)
        
        self.var_autoopt = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame_config, text="Auto-optimización", 
                       variable=self.var_autoopt).pack(anchor=tk.W)
        
        self.var_notif = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame_config, text="Notificaciones", 
                       variable=self.var_notif).pack(anchor=tk.W)
    
    def _build_config_tab(self, parent):
        """Construye tab de configuración."""
        frame_config = ttk.LabelFrame(parent, text="Parámetros del Sistema", padding=10)
        frame_config.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Sliders para configuración
        configs = [
            ('cpu_umbral_alto', 'Umbral CPU Alto (%)', 50, 100),
            ('memoria_alerta', 'Alerta Memoria (%)', 50, 100),
            ('temperatura_gpu', 'Temperatura GPU Alerta (°C)', 40, 100)
        ]
        
        for key, label, min_val, max_val in configs:
            frame = ttk.Frame(frame_config)
            frame.pack(fill=tk.X, padx=5, pady=5)
            
            ttk.Label(frame, text=label).pack(side=tk.LEFT)
            
            slider = ttk.Scale(frame, from_=min_val, to=max_val, orient=tk.HORIZONTAL)
            slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
            
            valor_label = ttk.Label(frame, text=str(min_val))
            valor_label.pack(side=tk.LEFT)
            
            def actualizar(v, lbl=valor_label):
                lbl.config(text=str(int(float(v))))
            
            slider.config(command=actualizar)
    
    def actualizar_metricas(self, datos: Dict):
        """Actualiza métricas en GUI."""
        try:
            # Extraer valores
            if 'cpu' in datos:
                cpu_info = datos['cpu']
                if isinstance(cpu_info, dict):
                    promedio = cpu_info.get('carga_promedio', cpu_info.get('carga', {}).get('promedio', 0))
                    self.metricas_labels['cpu_uso'].config(text=f"{promedio:.1f}")
            
            if 'memoria' in datos:
                mem_info = datos['memoria']
                if isinstance(mem_info, dict):
                    uso = mem_info.get('uso_actual', mem_info.get('memoria_fisica', {}).get('porcentaje', 0))
                    if isinstance(uso, dict):
                        uso = uso.get('porcentaje', 0)
                    self.metricas_labels['memoria_uso'].config(text=f"{uso:.1f}")
            
            if 'gpu' in datos:
                gpu_info = datos['gpu']
                if isinstance(gpu_info, dict):
                    metricas = gpu_info.get('metricas', {})
                    if metricas:
                        uso_gpu = list(metricas.values())[0].get('uso_gpu_pct', 0) if metricas else 0
                        self.metricas_labels['gpu_uso'].config(text=f"{uso_gpu:.1f}")
            
        except Exception as e:
            self.logger.debug(f"Error actualizando métricas GUI: {e}")
    
    def agregar_evento_gui(self, tipo: str, mensaje: str, nivel: str = "INFO"):
        """Agrega evento a la GUI."""
        if self.eventos_text:
            self.eventos_text.config(state=tk.NORMAL)
            timestamp = datetime.now().strftime('%H:%M:%S')
            icono = "❌" if nivel == "ERROR" else "⚠️" if nivel == "WARNING" else "ℹ️"
            texto = f"[{timestamp}] {icono} {tipo}: {mensaje}\n"
            
            self.eventos_text.insert(tk.END, texto)
            self.eventos_text.see(tk.END)
            self.eventos_text.config(state=tk.DISABLED)
    
    def mostrar_notificacion(self, titulo: str, mensaje: str, duracion: int = 5):
        """Muestra notificación toast."""
        if self.notifier and self.var_notif.get():
            try:
                self.notifier.show_toast(titulo, mensaje, duration=duracion, threaded=True)
            except:
                pass
    
    def mostrar_panel(self, icon=None, item=None):
        """Muestra panel de control."""
        self.root.deiconify()
        self.root.lift()
    
    def mostrar_estado(self, icon=None, item=None):
        """Muestra estado actual."""
        self.mostrar_notificacion("Estado", "Sistema optimizado ✓", 3)
    
    def _iniciar_optimizacion(self, icon=None, item=None):
        """Inicia optimización."""
        self.mostrar_notificacion("Optimización", "Iniciada ▶", 2)
        self.status_bar.config(text="Optimización en progreso... ⏳")
    
    def _pausar_optimizacion(self, icon=None, item=None):
        """Pausa optimización."""
        self.mostrar_notificacion("Pausa", "Optimización pausada ⏸", 2)
        self.status_bar.config(text="Pausado ⏸")
    
    def _actualizar_metricas(self):
        """Fuerza actualización de métricas."""
        self.status_bar.config(text="Actualizando métricas... ↻")
    
    def _liberar_memoria(self):
        """Libera memoria del sistema."""
        self.mostrar_notificacion("Memoria", "Liberando... 🧹", 2)
    
    def _optimizar_disco(self):
        """Optimiza disco."""
        self.mostrar_notificacion("Disco", "Optimizando... 💾", 2)
    
    def _limpiar_dns(self):
        """Limpia caché DNS."""
        self.mostrar_notificacion("DNS", "Limpiando caché... 🌐", 2)
    
    def _reiniciar_servicios(self):
        """Reinicia servicios."""
        self.mostrar_notificacion("Servicios", "Reiniciando... 🔄", 2)
    
    def _guardar_diagnostico(self):
        """Guarda diagnóstico completo."""
        self.mostrar_notificacion("Diagnóstico", "Guardando archivo... 💾", 3)
    
    def _exit_app(self, icon=None, item=None):
        """Cierra la aplicación."""
        if self.icon:
            self.icon.stop()
        self.activo = False
        self.root.quit()
    
    def ejecutar(self):
        """Mantiene GUI actualizada."""
        try:
            self.root.update_idletasks()
        except:
            pass
    
    def run(self):
        """Ejecuta la GUI."""
        if self.icon:
            tray_thread = threading.Thread(target=self.icon.run, daemon=True)
            tray_thread.start()
        
        try:
            self.root.mainloop()
        except:
            pass