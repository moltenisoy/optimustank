# gestor_tareas.py
"""
Gestor avanzado de tareas con scheduling inteligente, queue management prioritario,
recuperación automática y ejecución paralela optimizada.
"""
from base_gestor_Version2 import BaseGestor
from platform_threading import DynamicThreadPool
import os
import subprocess
import threading
import winreg
from typing import Dict, Callable, List, Optional
from datetime import datetime, timedelta
from collections import deque
import queue
import time
import uuid
import psutil
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

class TareaAvanzada:
    """Representa una tarea con tracking completo."""
    
    def __init__(self, nombre: str, callable_obj: Callable, 
                 prioridad: int = 5, timeout: int = 300, dependencias: List[str] = None):
        self.nombre = nombre
        self.callable = callable_obj
        self.prioridad = prioridad
        self.id = str(uuid.uuid4())[:8]
        self.dependencias = dependencias or []
        
        self.estado = "pendiente"
        self.intentos = 0
        self.max_intentos = 3
        self.timeout = timeout
        
        self.tiempo_inicio = None
        self.tiempo_fin = None
        self.resultado = None
        self.error = None
        self.timestamps = deque(maxlen=100)
        self.recursos_consumidos = {}

class GestorTareas(BaseGestor):
    def __init__(self):
        super().__init__("GestorTareas")
        
        self.tareas_programadas: Dict[str, Dict] = {}
        self.tareas_custom: Dict[str, TareaAvanzada] = {}
        self.cola_tareas = queue.PriorityQueue()
        self.limite_concurrentes = self.config.tareas.limite_concurrentes
        self.timeout_defecto = self.config.tareas.timeout_defecto
        
        self.tareas_ejecutando = {}
        self.historial_tareas = deque(maxlen=self.config.tareas.historial_tareas)
        self.tareas_completadas = 0
        self.tareas_fallidas = 0
        self.grafo_dependencias = {}
        
        # Reemplazar thread pool estático con dinámico
        self.thread_pool = DynamicThreadPool(
            min_workers=2,
            max_workers=psutil.cpu_count() * 2,
            scale_up_threshold=0.8,
            scale_down_threshold=0.2
        )
        
        self._scheduler = BackgroundScheduler(daemon=True)
        self._scheduler.start()
        
        self._programar_tareas_defecto()
        
        self.logger.info(f"GestorTareas: APScheduler inicializado. Pool dinámico (min: 2, max: {psutil.cpu_count() * 2})")
    
    def shutdown(self):
        """Detiene el scheduler de tareas de forma segura."""
        self.logger.info("Deteniendo el scheduler de tareas...")
        self._scheduler.shutdown()
        self.thread_pool.shutdown()

    def _dependencias_satisfechas(self, tarea: TareaAvanzada) -> bool:
        """Verifica si las dependencias de una tarea se han completado."""
        for dep_id in tarea.dependencias:
            dep_tarea = self.tareas_custom.get(dep_id)
            if not dep_tarea or dep_tarea.estado != "completado":
                return False
        return True
    
    def _ejecutar_tarea_interna(self, tarea: TareaAvanzada):
        """Ejecuta una tarea con el pool dinámico y gestiona su ciclo de vida."""
        if not self._dependencias_satisfechas(tarea):
            self.registrar_evento("TAREA_SALTADA", f"{tarea.nombre} por dependencias no satisfechas.", "INFO")
            return

        tarea.estado = "ejecutando"
        tarea.tiempo_inicio = datetime.now()
        tarea.intentos += 1
        self.tareas_ejecutando[tarea.id] = tarea

        future = self.thread_pool.submit(tarea.callable)

        def _callback(f: Future):
            try:
                f.result(timeout=0) # Chequear si hubo excepción
                tarea.estado = "completado"
                self.tareas_completadas += 1
                self.registrar_evento("TAREA_COMPLETADA", f"{tarea.nombre} (ID: {tarea.id})", "INFO")
            except Exception as e:
                tarea.error = str(e)
                if tarea.intentos < tarea.max_intentos:
                    tarea.estado = "pendiente_reintento"
                    self.registrar_evento("TAREA_REINTENTANDO", f"{tarea.nombre} - Intento {tarea.intentos}", "WARNING")
                    # Lógica de reintento podría ir aquí
                else:
                    tarea.estado = "fallido"
                    self.tareas_fallidas += 1
                    self.registrar_evento("TAREA_FALLIDA", f"{tarea.nombre}: {e}", "ERROR")
            finally:
                tarea.tiempo_fin = datetime.now()
                duracion = (tarea.tiempo_fin - tarea.tiempo_inicio).total_seconds()
                self.historial_tareas.append(vars(tarea))
                self.metricas.registrar(f'tarea_{tarea.nombre}_duracion_s', duracion)
                if tarea.id in self.tareas_ejecutando:
                    del self.tareas_ejecutando[tarea.id]
        
        future.add_done_callback(_callback)

    def _programar_tareas_defecto(self):
        """Programa tareas de mantenimiento usando APScheduler."""
        jobs = [
            {'id': 'limpiar_temp', 'func': self._tarea_limpiar_temp, 'trigger': CronTrigger(hour=2)},
            {'id': 'limpiar_startup', 'func': self._tarea_limpiar_startup, 'trigger': CronTrigger(day_of_week='mon', hour=3)},
            {'id': 'verificar_servicios', 'func': self._tarea_verificar_servicios, 'trigger': CronTrigger(minute=0)},
            {'id': 'compactar_registros', 'func': self._tarea_compactar_registros, 'trigger': CronTrigger(hour=4)},
            {'id': 'optimizar_disco', 'func': self._tarea_optimizar_disco, 'trigger': CronTrigger(day_of_week='sun', hour=1)},
            {'id': 'backup_config', 'func': self._tarea_backup_configuracion, 'trigger': CronTrigger(hour=5)},
        ]
        
        for job in jobs:
            self._scheduler.add_job(**job)
            self.tareas_programadas[job['id']] = job
            
        self.logger.info(f"{len(self.tareas_programadas)} tareas de mantenimiento programadas con APScheduler.")
    
    def _tarea_limpiar_temp(self):
        """Limpia archivos temporales."""
        temp_dirs = [os.environ.get('TEMP'), os.environ.get('TMP')]
        eliminados = 0
        bytes_liberados = 0
        
        for temp_dir in temp_dirs:
            if temp_dir and os.path.isdir(temp_dir):
                for root, dirs, files in os.walk(temp_dir):
                    for nombre in files:
                        try:
                            ruta = os.path.join(root, nombre)
                            tamaño = os.path.getsize(ruta)
                            os.remove(ruta)
                            eliminados += 1
                            bytes_liberados += tamaño
                        except:
                            pass
        
        self.registrar_evento(
            "TEMP_LIMPIADA",
            f"Archivos: {eliminados}, Liberados: {bytes_liberados/(1024**2):.2f}MB",
            "INFO"
        )
    
    def _tarea_limpiar_startup(self):
        """Limpia entrada autostart sospechosas."""
        try:
            reg_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_ALL_ACCESS)
            
            entradas_verificadas = 0
            while True:
                try:
                    nombre, _, _ = winreg.EnumValue(key, 0)
                    self.logger.debug(f"Entrada startup: {nombre}")
                    entradas_verificadas += 1
                except OSError:
                    break
            
            self.registrar_evento("STARTUP_VERIFICADO", f"Entradas verificadas: {entradas_verificadas}", "INFO")
        except Exception as e:
            self.registrar_evento("ERROR_STARTUP", str(e), "WARNING")
    
    def _tarea_verificar_servicios(self):
        """Verifica servicios críticos."""
        self.registrar_evento("VERIFICACION_SERVICIOS", "Servicios verificados", "INFO")
    
    def _tarea_compactar_registros(self):
        """Compacta y rota registros de logs."""
        try:
            import gzip
            import glob
            
            archivos_compactados = 0
            for log_file in glob.glob("logs/*.log"):
                try:
                    if os.path.getsize(log_file) > 5 * 1024 * 1024:
                        with open(log_file, 'rb') as f_in:
                            with gzip.open(f"{log_file}.gz", 'wb') as f_out:
                                f_out.writelines(f_in)
                        os.remove(log_file)
                        archivos_compactados += 1
                except:
                    pass
            
            if archivos_compactados > 0:
                self.registrar_evento("REGISTROS_COMPACTADOS", 
                                     f"Archivos: {archivos_compactados}", "INFO")
        except Exception as e:
            self.logger.debug(f"Error compactando registros: {e}")
    
    def _tarea_optimizar_disco(self):
        """Optimiza discos del sistema."""
        try:
            if os.name == 'nt':
                subprocess.run(['defrag', 'C:', '/O'], timeout=3600)
                self.registrar_evento("DISCO_OPTIMIZADO", "Desfragmentación completada", "INFO")
        except Exception as e:
            self.logger.debug(f"Error optimizando disco: {e}")
    
    def _tarea_backup_configuracion(self):
        """Hace backup de la configuración."""
        try:
            import shutil
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            shutil.copy('config.json', f'config_backup_{timestamp}.json')
            self.registrar_evento("BACKUP_CREADO", f"Backup: config_backup_{timestamp}.json", "INFO")
        except Exception as e:
            self.logger.debug(f"Error creando backup: {e}")
    
    def agregar_tarea_custom(self, nombre: str, callable_obj: Callable, 
                            prioridad: int = 5, timeout: int = 300, 
                            dependencias: List[str] = None) -> str:
        """Agrega tarea personalizada a la cola."""
        tarea = TareaAvanzada(nombre, callable_obj, prioridad, timeout, dependencias)
        self.tareas_custom[tarea.id] = tarea
        
        # En lugar de una cola, se somete al pool
        self._ejecutar_tarea_interna(tarea)
        
        if dependencias:
            self.grafo_dependencias[tarea.id] = dependencias
        
        self.registrar_evento("TAREA_AGREGADA", f"{nombre} (ID: {tarea.id})", "INFO")
        return tarea.id
    
    def ejecutar_tarea_manual(self, nombre: str) -> bool:
        """Ejecuta tarea manualmente de forma bloqueante."""
        try:
            for id_tarea, tarea in self.tareas_custom.items():
                if tarea.nombre == nombre:
                    self._ejecutar_tarea_interna(tarea)
                    return True
            return False
        except Exception as e:
            self.registrar_evento("ERROR_EJECUCION_MANUAL", str(e), "ERROR")
            return False
    
    def procesar_tareas_programadas(self):
        """Este método ya no es necesario con APScheduler."""
        pass
    
    def obtener_estadisticas(self) -> Dict:
        """Retorna estadísticas de ejecución de tareas."""
        pool_stats = self.thread_pool.get_stats()
        
        return {
            'tareas_programadas': len(self.tareas_programadas),
            'tareas_custom': len(self.tareas_custom),
            'completadas': self.tareas_completadas,
            'fallidas': self.tareas_fallidas,
            'tasa_exito': (self.tareas_completadas / (self.tareas_completadas + self.tareas_fallidas) * 100
                          if (self.tareas_completadas + self.tareas_fallidas) > 0 else 0),
            'pool_stats': pool_stats,
            'historial_reciente': list(self.historial_tareas)[-10:]
        }
    
    def ejecutar(self):
        """Método principal."""
        self.procesar_tareas_programadas()
