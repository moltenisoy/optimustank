# gestor_disco.py
"""
Gestor avanzado de disco con optimización de I/O, prioridades de escritura,
caché inteligente y desfragmentación predictiva.
"""
from base_gestor import BaseGestor
import psutil
import os
import platform
from typing import Dict, List, Optional
from collections import deque
import subprocess
import threading

from datetime import timedelta

from platform_threading import PlatformAdapterFactory

class GestorDisco(BaseGestor):
    def __init__(self):
        super().__init__("GestorDisco")
        
        self.adapter = PlatformAdapterFactory.create_adapter()
        self.umbral_uso = self.config.get('disco.umbral_uso', 90)
        self.umbral_io = self.config.get('disco.umbral_io', 80)
        self.optimizar_ssd = self.config.get('disco.optimizar_ssd', True)
        
        self.historial_io = deque(maxlen=200)
        self.mapa_prioridades_io = {}
        self.discos_monitoreados = {}
        self.operaciones_optimizadas = 0
        
        self.logger.info("GestorDisco inicializado")
    
    def obtener_estadisticas_discos(self) -> Dict:
        """Obtiene estadísticas detalladas de todos los discos."""
        try:
            discos = {}
            
            for particion in psutil.disk_partitions():
                try:
                    uso = psutil.disk_usage(particion.mountpoint)
                    
                    discos[particion.device] = {
                        'mountpoint': particion.mountpoint,
                        'fstype': particion.fstype,
                        'total_gb': uso.total / (1024**3),
                        'usado_gb': uso.used / (1024**3),
                        'libre_gb': uso.free / (1024**3),
                        'porcentaje_uso': uso.percent,
                        'es_ssd': self.adapter.is_ssd(particion.device)
                    }
                except PermissionError:
                    pass
            
            self.discos_monitoreados = discos
            return discos
        
        except Exception as e:
            self.logger.error(f"Error obteniendo estadísticas discos: {e}")
            return {}
    
    def ajustar_prioridad_io_proceso(self, proc, prioridad: int):
        """Ajusta prioridad de I/O de un proceso (1-10)."""
        try:
            pid = proc.pid
            nombre = proc.name()
            
            # Mapear prioridad a clases de I/O
            if prioridad >= 8:
                clase_io = psutil.IOPRIO_CLASS_RT  # Tiempo real
            elif prioridad >= 5:
                clase_io = psutil.IOPRIO_CLASS_BE  # Best effort
            else:
                clase_io = psutil.IOPRIO_CLASS_IDLE  # Idle
            
            try:
                proc.ionice(clase_io)
                
                self.mapa_prioridades_io[pid] = {
                    'nombre': nombre,
                    'prioridad': prioridad,
                    'clase_io': clase_io,
                    'timestamp': __import__('datetime').datetime.now()
                }
                
                return True
            
            except (AttributeError, psutil.AccessDenied, psutil.NoSuchProcess):
                return False
        
        except Exception as e:
            self.logger.debug(f"Error ajustando prioridad I/O: {e}")
            return False
    
    def optimizar_prioridades_escritura(self):
        """Optimiza prioridades de escritura de todos los procesos."""
        try:
            ajustes = 0
            
            for proc in psutil.process_iter(['pid', 'name', 'io_counters']):
                try:
                    nombre = proc.info['name']
                    io_counters = proc.info.get('io_counters')
                    
                    if not io_counters:
                        continue
                    
                    escrituras = io_counters.write_bytes
                    
                    # Determinar prioridad según tasa de escritura
                    if nombre in ['System', 'svchost.exe', 'services.exe']:
                        prioridad = 8  # Alta para procesos críticos
                    elif escrituras > 100 * 1024 * 1024:  # > 100MB
                        prioridad = 3  # Baja para escritores pesados
                    elif escrituras > 10 * 1024 * 1024:  # > 10MB
                        prioridad = 5  # Normal
                    else:
                        prioridad = 7  # Alta para escritores ligeros
                    
                    if self.ajustar_prioridad_io_proceso(proc, prioridad):
                        ajustes += 1
                
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            if ajustes > 0:
                self.operaciones_optimizadas += ajustes
                self.registrar_evento(
                    "PRIORIDADES_IO_OPTIMIZADAS",
                    f"Ajustados {ajustes} procesos",
                    "INFO"
                )
        
        except Exception as e:
            self.logger.warning(f"Error optimizando prioridades I/O: {e}")
    
    def optimizar_cache_disco(self):
        """Optimiza caché de disco del sistema."""
        try:
            if platform.system() == "Windows":
                # Ajustar tamaño de caché de disco
                subprocess.run(
                    ['fsutil', 'behavior', 'set', 'memoryusage', '2'],
                    capture_output=True,
                    timeout=5
                )
                
                self.registrar_evento(
                    "CACHE_DISCO_OPTIMIZADO",
                    "Caché de disco ajustado",
                    "INFO"
                )
            else:
                # En Linux, ajustar vm.dirty_ratio
                subprocess.run(
                    ['sysctl', '-w', 'vm.dirty_ratio=15'],
                    capture_output=True,
                    timeout=5
                )
        
        except Exception as e:
            self.logger.debug(f"Error optimizando caché disco: {e}")
    
    def optimizar_ssd_trim(self):
        """Optimiza SSD con TRIM."""
        if not self.optimizar_ssd:
            return
        
        try:
            discos = self.obtener_estadisticas_discos()
            
            for disco, info in discos.items():
                if info.get('es_ssd'):
                    self.adapter.run_trim(disco)
                    self.registrar_evento(
                        "SSD_TRIM_EJECUTADO",
                        f"TRIM en {disco}",
                        "INFO"
                    )
        
        except Exception as e:
            self.logger.debug(f"Error ejecutando TRIM: {e}")
    
    def monitorear_uso_disco(self):
        """Monitorea uso de disco y genera alertas."""
        try:
            discos = self.obtener_estadisticas_discos()
            
            for disco, info in discos.items():
                if info['porcentaje_uso'] > self.umbral_uso:
                    self.registrar_evento(
                        "DISCO_LLENO",
                        f"{disco}: {info['porcentaje_uso']:.1f}% usado",
                        "WARNING",
                        prioridad=8
                    )
        
        except Exception as e:
            self.logger.debug(f"Error monitoreando disco: {e}")
    
    def limpiar_archivos_temporales(self, dias_antiguedad: int = 7):
        """Limpia archivos temporales más antiguos que un número de días."""
        try:
            archivos_eliminados = 0
            bytes_liberados = 0
            now = time.time()
            
            temp_dirs = [
                os.environ.get('TEMP'),
                os.environ.get('TMP'),
                'C:\\Windows\\Temp' if platform.system() == 'Windows' else '/tmp'
            ]
            
            for temp_dir in filter(None, temp_dirs):
                if os.path.isdir(temp_dir):
                    for root, _, files in os.walk(temp_dir):
                        for nombre_archivo in files:
                            try:
                                ruta_completa = os.path.join(root, nombre_archivo)
                                if os.path.getmtime(ruta_completa) < now - (dias_antiguedad * 86400):
                                    tamano = os.path.getsize(ruta_completa)
                                    os.remove(ruta_completa)
                                    archivos_eliminados += 1
                                    bytes_liberados += tamano
                            except (FileNotFoundError, PermissionError):
                                continue
            
            if archivos_eliminados > 0:
                self.registrar_evento(
                    "TEMPORALES_LIMPIADOS",
                    f"Archivos: {archivos_eliminados}, Liberados: {bytes_liberados/(1024**2):.2f}MB",
                    "INFO"
                )
        
        except Exception as e:
            self.logger.debug(f"Error limpiando temporales: {e}")
    
    def obtener_estadisticas(self) -> Dict:
        """Retorna estadísticas completas."""
        return {
            'discos': self.obtener_estadisticas_discos(),
            'io': self.obtener_estadisticas_io(),
            'prioridades': {
                'procesos_gestionados': len(self.mapa_prioridades_io)
            },
            'operaciones_optimizadas': self.operaciones_optimizadas,
            'umbrales': {
                'uso': self.umbral_uso,
                'io': self.umbral_io
            }
        }
    
    def setup_tasks(self):
        """Configura y añade las tareas de optimización de disco al scheduler."""
        scheduler.add_task(Task("monitorear_uso_disco", self.monitorear_uso_disco, timedelta(seconds=60)))
        scheduler.add_task(Task("optimizar_prioridades_io", self.optimizar_prioridades_escritura, timedelta(seconds=120)))
        scheduler.add_task(Task("optimizar_cache_disco", self.optimizar_cache_disco, timedelta(minutes=5)))
        scheduler.add_task(Task("limpiar_temporales", self.limpiar_archivos_temporales, timedelta(days=7), self._can_run_maintenance))
        scheduler.add_task(Task("optimizar_ssd_trim", self.optimizar_ssd_trim, timedelta(days=15), self._can_run_maintenance))

        # Suscripción a eventos de modo juego
        event_bus.subscribe("GameModeStarted", self._on_game_mode_started)
        event_bus.subscribe("GameModeStopped", self._on_game_mode_stopped)

    def _on_game_mode_started(self, event):
        """Evita que los discos duros entren en modo de suspensión."""
        self.registrar_evento("GAME_MODE_DISCO", "Evitando suspensión de discos duros...", "INFO")
        self._manage_hdd_power_settings(prevent_sleep=True)

    def _on_game_mode_stopped(self, event):
        """Restaura la configuración de energía de los discos duros."""
        self.registrar_evento("GAME_MODE_DISCO", "Restaurando configuración de energía de discos...", "INFO")
        self._manage_hdd_power_settings(prevent_sleep=False)

    def _manage_hdd_power_settings(self, prevent_sleep: bool):
        """Activa o desactiva la suspensión de discos duros."""
        if platform.system() != "Windows":
            return
        
        minutos = "0" if prevent_sleep else "20"
        subprocess.run(
            ['powercfg', '/change', 'disk-timeout-ac', minutos],
            capture_output=True, timeout=5
        )

    def _can_run_maintenance(self):
        """Condición para ejecutar tareas de mantenimiento."""
        try:
            cpu_usage = psutil.cpu_percent()
            disk_io = psutil.disk_io_counters()
            mem_usage = psutil.virtual_memory().percent

            if cpu_usage > 80 or disk_io.read_bytes + disk_io.write_bytes > 100 * 1024 * 1024 or mem_usage > 80:
                self.registrar_evento("MANTENIMIENTO_POSPUESTO", "Carga del sistema demasiado alta.", "INFO")
                return False
            return True
        except Exception:
            return False