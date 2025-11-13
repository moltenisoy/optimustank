# base_gestor.py
"""
Clase base avanzada para todos los gestores del sistema.
Proporciona funcionalidad común: logging, métricas, configuración, eventos, threading.
"""
import json
import logging
import logging.handlers
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Type
from collections import deque
import threading
import queue
import hashlib
import pickle
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pydantic import BaseModel, Field
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Nuevas importaciones
from dependency_container import ServiceContainer
from memory_utils import EventoAvanzadoPool, GestorRegistry
from core_events import get_tracer, EventoAvanzado


# Modelos de Pydantic para la validación de la configuración
class SistemaConfig(BaseModel):
    nombre: str = "OptimizadorSistemaAvanzado"
    version: str = "2.1.0"
    modo_debug: bool = False
    arquitectura_requerida: str = "x64"


class PrioridadesConfig(BaseModel):
    cpu_umbral_alto: int = 80
    cpu_umbral_bajo: int = 10
    cpu_critico: int = 95
    whitelist: List[str] = ["explorer.exe", "svchost.exe"]
    blacklist: List[str] = ["malware.exe"]
    ajuste_dinamico: bool = True
    historial_max: int = 200


class RedesConfig(BaseModel):
    trafico_umbral: int = 1024 * 1024 * 100
    latencia_maxima: int = 100
    latencia_critica: int = 200
    monitores_simultaneos: int = 5
    optimizar_dns: bool = True
    tcp_tuning: bool = True


class MemoriaConfig(BaseModel):
    porcentaje_alerta: int = 85
    porcentaje_critico: int = 95
    porcentaje_extremo: int = 98
    estrategia_liberacion: str = "agresiva"
    swap_agresivo: bool = True
    compresion_habilitada: bool = True
    limite_procesos_pesados: int = 10


class KernelConfig(BaseModel):
    auto_tuning: bool = True
    aggressive_mode: bool = False
    aggressive_level: int = 5
    cache_optimization: bool = True
    pagefile_tuning: bool = True
    memory_protection: bool = False
    power_throttle: bool = False


class CPUConfig(BaseModel):
    balanceo_inteligente: bool = True
    afinidad_dinamica: bool = True
    distribucion_nucleos: str = "optima"
    hilos_monitoreados_max: int = 1000
    non_critical_processes: List[str] = ['chrome.exe', 'spotify.exe']


class GPUConfig(BaseModel):
    monitores_habilitados: List[str] = ["NVIDIA", "AMD", "Intel"]
    temperatura_alerta: int = 75
    temperatura_critica: int = 85
    uso_umbral: int = 90
    boost_dinamico: bool = True
    power_limit_tuning: bool = True


class ServiciosConfig(BaseModel):
    monitores_criticos: List[str] = ["RpcSs", "DcomLaunch", "WinRM"]
    auto_recuperacion: bool = True
    reinicio_max_intentos: int = 3
    eliminacion_procesos_muertos: bool = True


class TareasConfig(BaseModel):
    limite_concurrentes: int = 5
    timeout_defecto: int = 300
    reintentos_defecto: int = 3
    historial_tareas: int = 500


class GUIConfig(BaseModel):
    theme: str = "dark"
    update_interval: int = 500
    fps_target: int = 60
    animaciones_habilitadas: bool = True
    notificaciones_habilitadas: bool = True
    logs_gui_max: int = 10000
    graficar_metricas: bool = True
    show_temp_in_tray: bool = False
    game_list: List[str] = []
    whitelist: List[str] = ["explorer.exe", "svchost.exe", "dwm.exe"]


class ThermalThrottlingConfig(BaseModel):
    monitoring_interval: int = 1
    soft_threshold: int = 70
    aggressive_threshold: int = 75


class LoggingConfig(BaseModel):
    level: str = "INFO"
    max_lines: int = 50000
    rotacion_tamaño: int = 10 * 1024 * 1024
    rotacion_dias: int = 7
    formato_timestamp: str = "%Y-%m-%d %H:%M:%S.%f"


class SinergiasConfig(BaseModel):
    feedback_loop: bool = True
    prevencion_cascada: bool = True
    coordinacion_modulos: bool = True
    prediccion_carga: bool = True


class AppConfig(BaseModel):
    sistema: SistemaConfig = Field(default_factory=SistemaConfig)
    prioridades: PrioridadesConfig = Field(default_factory=PrioridadesConfig)
    redes: RedesConfig = Field(default_factory=RedesConfig)
    memoria: MemoriaConfig = Field(default_factory=MemoriaConfig)
    kernel: KernelConfig = Field(default_factory=KernelConfig)
    cpu: CPUConfig = Field(default_factory=CPUConfig)
    gpu: GPUConfig = Field(default_factory=GPUConfig)
    servicios: ServiciosConfig = Field(default_factory=ServiciosConfig)
    tareas: TareasConfig = Field(default_factory=TareasConfig)
    gui: GUIConfig = Field(default_factory=GUIConfig)
    thermal_throttling: ThermalThrottlingConfig = Field(default_factory=ThermalThrottlingConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    sinergias: SinergiasConfig = Field(default_factory=SinergiasConfig)


class EventBus:
    """Event bus con manejo asíncrono y prioridades."""
    def __init__(self) -> None:
        self.listeners: Dict[str, List[Callable]] = defaultdict(list)
        self.lock: threading.RLock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix='EventBus')

    def subscribe(self, event_type: str, callback: Callable) -> None:
        with self.lock:
            if callback not in self.listeners[event_type]:
                self.listeners[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        with self.lock:
            if callback in self.listeners[event_type]:
                self.listeners[event_type].remove(callback)

    def publish(self, event: 'EventoAvanzado') -> None:
        with self.lock:
            callbacks = self.listeners.get(event.tipo, [])
        
        for callback in callbacks:
            self._executor.submit(self._execute_callback, callback, event)
    
    def _execute_callback(self, callback: Callable, event: 'EventoAvanzado'):
        try:
            callback(event)
        except Exception as e:
            logging.error(f"Error in event bus callback for event {event.tipo}: {e}")

    def shutdown(self):
        self._executor.shutdown(wait=True)


class ConfigChangeHandler(FileSystemEventHandler):
    def __init__(self, config_manager: 'ConfigManager'):
        self.config_manager = config_manager

    def on_modified(self, event):
        if not event.is_directory and Path(event.src_path) == self.config_manager.config_file:
            logging.info(f"Config file {event.src_path} modified. Reloading.")
            self.config_manager.reload()


class ConfigManager:
    """Gestor de configuración mejorado con watchdog."""
    
    def __init__(self, config_file: str = "config.json"):
        self.config_file: Path = Path(config_file).resolve()
        self.config: AppConfig = self._load_config()
        self.lock: threading.RLock = threading.RLock()
        self.watchers: Dict[str, List[Callable]] = {}
        
        self._observer = Observer()
        self._observer.schedule(ConfigChangeHandler(self), str(self.config_file.parent), recursive=False)
        self._observer.start()
    
    def _load_config(self) -> AppConfig:
        if self.config_file.exists():
            try:
                with self.config_file.open('r', encoding='utf-8') as f:
                    config_data = json.load(f)
                return AppConfig(**config_data)
            except (json.JSONDecodeError, TypeError) as e:
                logging.error(f"Error loading or parsing config file: {e}")
        return AppConfig()

    def reload(self):
        """Recarga la configuración desde el archivo."""
        with self.lock:
            self.config = self._load_config()
    
    def get(self, key: str, default: Any = None) -> Any:
        with self.lock:
            keys = key.split('.')
            value = self.config
            for k in keys:
                if hasattr(value, k):
                    value = getattr(value, k)
                else:
                    return default
            return value
    
    def set(self, key: str, value: Any) -> None:
        with self.lock:
            keys = key.split('.')
            config = self.config
            for k in keys[:-1]:
                config = getattr(config, k)
            setattr(config, keys[-1], value)
            self.save()
            self._notificar_watchers(key, value)
    
    def save(self) -> None:
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config.model_dump(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Error guardando config: {e}")
    
    def agregar_watcher(self, clave: str, callback: Callable) -> None:
        """Añade observador de cambios de configuración."""
        if clave not in self.watchers:
            self.watchers[clave] = []
        self.watchers[clave].append(callback)
    
    def _notificar_watchers(self, clave: str, valor: Any) -> None:
        """Notifica a watchers cuando cambia configuración."""
        if clave in self.watchers:
            for callback in self.watchers[clave]:
                try:
                    callback(valor)
                except Exception as e:
                    logging.error(f"Error en watcher: {e}")
    
    def stop_monitoring(self):
        self._observer.stop()
        self._observer.join()


class Task:
    def __init__(self, name: str, action: Callable[[], None], interval: timedelta, condition: Optional[Callable[[], bool]] = None):
        self.name: str = name
        self.action: Callable[[], None] = action
        self.interval: timedelta = interval
        self.condition: Optional[Callable[[], bool]] = condition
        self.last_run: Optional[datetime] = None

    def should_run(self) -> bool:
        if self.condition and not self.condition():
            return False
        if self.last_run is None:
            return True
        return datetime.now() - self.last_run >= self.interval

    def run(self) -> None:
        self.last_run = datetime.now()
        self.action()


class Scheduler:
    def __init__(self) -> None:
        self.tasks: List[Task] = []
        self.lock: threading.RLock = threading.RLock()
        self.running: bool = False
        self.thread: Optional[threading.Thread] = None

    def add_task(self, task: Task) -> None:
        with self.lock:
            self.tasks.append(task)

    def _run(self) -> None:
        while self.running:
            with self.lock:
                for task in self.tasks:
                    if task.should_run():
                        try:
                            task.run()
                        except Exception as e:
                            logging.error(f"Error running task {task.name}: {e}")
            time.sleep(1)

    def start(self) -> None:
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def stop(self) -> None:
        self.running = False
        if self.thread:
            self.thread.join()

# Las instancias globales se eliminarán y se gestionarán a través del contenedor


class GameModeManager:
    def __init__(self, adapter: 'PlatformAdapter') -> None:
        self.adapter = adapter
        self.game_mode_active: bool = False
        # Inyección de dependencias
        container = ServiceContainer()
        self.event_bus = container.get('event_bus')
        self.scheduler = container.get('scheduler')

    def _publish_event(self, tipo: str, mensaje: str):
        """Publica un evento usando el pool."""
        evento = EventoAvanzadoPool.create(tipo, mensaje, modulo="GameModeManager")
        self.event_bus.publish(evento)
        EventoAvanzadoPool.recycle(evento)

    def check_game_mode(self) -> None:
        is_fullscreen = self.adapter.is_fullscreen_game_running()
        if is_fullscreen and not self.game_mode_active:
            self.game_mode_active = True
            self._publish_event("GameModeStarted", "Game mode started")
        elif not is_fullscreen and self.game_mode_active:
            self.game_mode_active = False
            self._publish_event("GameModeStopped", "Game mode stopped")

    def setup_tasks(self) -> None:
        self.scheduler.add_task(Task("check_game_mode", self.check_game_mode, timedelta(seconds=5)))


class MetricasColector:
    """Colector avanzado de métricas con estadísticas, percentiles y predicción."""
    
    def __init__(self, max_registros: int = 10000) -> None:
        self.metricas: deque = deque(maxlen=max_registros)
        self.metricas_por_tipo: Dict[str, deque] = {}
        self.lock: threading.RLock = threading.RLock()
        self.estadisticas_cache: Dict[str, Any] = {}
        self.cache_timeout: timedelta = timedelta(seconds=5)
    
    def registrar(self, metrica: str, valor: float, tags: Optional[Dict] = None, 
                  unidad: str = "", umbral_alerta: Optional[float] = None) -> None:
        with self.lock:
            registro = {
                'timestamp': datetime.now(),
                'metrica': metrica,
                'valor': valor,
                'tags': tags or {},
                'unidad': unidad,
                'umbral_alerta': umbral_alerta
            }
            self.metricas.append(registro)
            
            if metrica not in self.metricas_por_tipo:
                self.metricas_por_tipo[metrica] = deque(maxlen=1000)
            self.metricas_por_tipo[metrica].append(valor)
            
            self.estadisticas_cache.clear()
    
    def obtener_promedio(self, metrica: str, ventana: int = 100) -> Optional[float]:
        with self.lock:
            valores = [m['valor'] for m in list(self.metricas)[-ventana:] 
                      if m['metrica'] == metrica]
            return sum(valores) / len(valores) if valores else None
    
    def obtener_estadisticas(self, metrica: str) -> Dict[str, Any]:
        """Retorna estadísticas completas: min, max, promedio, desv, percentiles."""
        with self.lock:
            if metrica not in self.metricas_por_tipo:
                return {}
            
            valores = list(self.metricas_por_tipo[metrica])
            if not valores:
                return {}
            
            import statistics
            import numpy as np
            
            return {
                'minimo': min(valores),
                'maximo': max(valores),
                'promedio': statistics.mean(valores),
                'mediana': statistics.median(valores),
                'desv_estandar': statistics.stdev(valores) if len(valores) > 1 else 0,
                'p25': np.percentile(valores, 25),
                'p50': np.percentile(valores, 50),
                'p75': np.percentile(valores, 75),
                'p95': np.percentile(valores, 95),
                'p99': np.percentile(valores, 99)
            }
    
    def obtener_ultimas(self, metrica: str, cantidad: int = 10) -> List[Dict[str, Any]]:
        with self.lock:
            return [{'timestamp': m['timestamp'].isoformat(), 
                     'valor': m['valor'],
                     'tags': m['tags']} 
                   for m in list(self.metricas)[-cantidad:] 
                   if m['metrica'] == metrica]
    
    def exportar_metricas(self, archivo: str) -> None:
        """Exporta métricas a archivo CSV."""
        try:
            import csv
            with open(archivo, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'metrica', 'valor', 'tags', 'unidad'])
                with self.lock:
                    for m in self.metricas:
                        writer.writerow([
                            m['timestamp'].isoformat(),
                            m['metrica'],
                            m['valor'],
                            json.dumps(m['tags']),
                            m['unidad']
                        ])
        except Exception as e:
            logging.error(f"Error exportando métricas: {e}")


class BaseGestor(ABC):
    """Clase base avanzada para todos los gestores del sistema."""
    
    def __init__(self, nombre: str) -> None:
        self.nombre: str = nombre
        self.activo: bool = True
        self.paused: bool = False
        
        # Inyección de dependencias
        container = ServiceContainer()
        self.config = container.get('config')
        self.event_bus = container.get('event_bus')
        self.scheduler = container.get('scheduler')
        self.metricas = container.get('metrics')
        self.tracer = get_tracer()

        self.logger: logging.Logger = self._setup_logger()
        self.lock: threading.RLock = threading.RLock()

        # Salud del módulo
        self.ultimo_latido: datetime = datetime.now()
        self.contador_ejecuciones: int = 0
        self.contador_errores: int = 0
        self.tiempo_promedio_ejecucion: float = 0

        # Registrar en registry con weak reference
        registry = GestorRegistry()
        registry.register(self.nombre, self)
    
    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger(self.nombre)
        log_level = self.config.logging.level
        logger.setLevel(getattr(logging, log_level))
        
        # Handler de archivo con rotación
        log_file = f"logs/{self.nombre}.log"
        Path(log_file).parent.mkdir(exist_ok=True)
        
        handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=self.config.logging.rotacion_tamaño,
            backupCount=5
        )
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s] - %(message)s',
            datefmt=self.config.logging.formato_timestamp
        )
        handler.setFormatter(formatter)
        
        # Evitar duplicados
        if not logger.handlers:
            logger.addHandler(handler)
        
        return logger
    
    def registrar_evento(self, tipo: str, mensaje: str, nivel: str = "INFO",
                        prioridad: int = 5, contexto: Optional[Dict] = None) -> None:
        """Registra evento avanzado con pool y tracing."""
        with self.tracer.trace(f"{self.nombre}.{tipo}") as span:
            evento = EventoAvanzadoPool.create(
                tipo=tipo,
                mensaje=mensaje,
                nivel=nivel,
                modulo=self.nombre,
                contexto=contexto or {},
                prioridad=prioridad
            )
            span.set_tag('evento_id', evento.id)
            span.set_tag('prioridad', prioridad)
            
            # Logging
            getattr(self.logger, nivel.lower())(f"[{tipo}] {mensaje}")
            
            # Publicar en el bus de eventos
            self.event_bus.publish(evento)

            # Reciclar el evento después de su uso
            EventoAvanzadoPool.recycle(evento)

    def pausar(self) -> None:
        """Pausa el gestor temporalmente."""
        self.paused = True
        self.registrar_evento("PAUSA", f"{self.nombre} pausado")
    
    def reanudar(self) -> None:
        """Reanuda el gestor."""
        self.paused = False
        self.registrar_evento("REANUDACION", f"{self.nombre} reanudado")
    
    def detener(self) -> None:
        """Detiene el gestor."""
        self.activo = False
        self.logger.info(f"{self.nombre} detenido")
    
    @abstractmethod
    def setup_tasks(self) -> None:
        """Configura y añade las tareas al scheduler. Debe ser implementado por subclases."""
        pass

    def get_gestor(self, nombre: str) -> Optional['BaseGestor']:
        """Obtiene referencia a otro gestor a través del registry."""
        registry = GestorRegistry()
        return registry.get(nombre)

    def obtener_estado_salud(self) -> Dict[str, Any]:
        """Retorna estado de salud del módulo."""
        tiempo_sin_latido = (datetime.now() - self.ultimo_latido).total_seconds()
        
        return {
            'modulo': self.nombre,
            'activo': self.activo,
            'pausado': self.paused,
            'tiempo_sin_latido': tiempo_sin_latido,
            'contador_ejecuciones': self.contador_ejecuciones,
            'contador_errores': self.contador_errores,
            'tiempo_promedio_ejecucion': self.tiempo_promedio_ejecucion,
            'tasa_error': (self.contador_errores / self.contador_ejecuciones * 100 
                          if self.contador_ejecuciones > 0 else 0)
        }
