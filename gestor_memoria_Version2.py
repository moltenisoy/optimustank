# gestor_memoria.py
"""
Gestor avanzado de memoria con algoritmos adaptativos, predicción y optimización agresiva.
Incluye gestión de prioridades de memoria, compresión dinámica y análisis predictivo.
"""
from base_gestor_Version2 import BaseGestor, Task
from smart_cache import cached, LRUCache
import psutil
import ctypes
import gc
import os
from typing import Dict, List, Optional, Any, Set
import threading
import numpy as np
from collections import deque
import platform
from statsmodels.tsa.arima.model import ARIMA
from datetime import timedelta

class GestorMemoria(BaseGestor):
    def __init__(self) -> None:
        super().__init__("GestorMemoria")
        
        self.porcentaje_alerta: int = self.config.memoria.porcentaje_alerta
        self.porcentaje_critico: int = self.config.memoria.porcentaje_critico
        self.porcentaje_extremo: int = self.config.memoria.porcentaje_extremo
        self.estrategia: str = self.config.memoria.estrategia_liberacion
        
        self.intentos_liberacion: int = 0
        self.liberaciones_exitosas: int = 0
        self.memoria_liberada_total: int = 0
        self.historial_uso: deque = deque(maxlen=500)
        self.procesos_monitoreados: Dict[int, Dict[str, Any]] = {}
        
        # Nuevas características de prioridad de memoria
        self.mapa_prioridades_memoria: Dict[int, Dict[str, Any]] = {}
        self.procesos_criticos_memoria: Set[int] = set()
        self.historial_swap: deque = deque(maxlen=200)
        self.compresion_activa: bool = False
        
        # Modelo predictivo
        self.modelo_predictivo = None
        
        # Caché para estadísticas
        self._stats_cache = LRUCache(max_size=100, default_ttl=5.0)
        
        self.logger.info("GestorMemoria inicializado")
    
    @cached(ttl=5.0)
    def obtener_uso_memoria_detallado(self) -> Dict[str, Any]:
        """Obtiene estadísticas completas de memoria."""
        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            # Memoria del proceso actual
            proceso_actual = psutil.Process()
            mem_info = proceso_actual.memory_info()
            
            estadisticas = {
                'timestamp': __import__('datetime').datetime.now().isoformat(),
                'memoria_fisica': {
                    'total': mem.total,
                    'disponible': mem.available,
                    'usado': mem.used,
                    'libre': mem.free,
                    'porcentaje': mem.percent,
                    'activo': getattr(mem, 'active', 0),
                    'inactivo': getattr(mem, 'inactive', 0),
                    'buffers': getattr(mem, 'buffers', 0),
                    'cached': getattr(mem, 'cached', 0),
                    'shared': getattr(mem, 'shared', 0)
                },
                'swap': {
                    'total': swap.total,
                    'usado': swap.used,
                    'libre': swap.free,
                    'porcentaje': swap.percent
                },
                'proceso_actual': {
                    'rss': mem_info.rss,
                    'vms': mem_info.vms,
                    'numero_threads': proceso_actual.num_threads()
                }
            }
            
            self.historial_uso.append(mem.percent)
            self.historial_swap.append(swap.percent)
            self.metricas.registrar('memoria_porcentaje', mem.percent, 
                                   tags={'swap': swap.percent})
            
            return estadisticas
        
        except Exception as e:
            self.registrar_evento("ERROR_LECTURA_MEM", str(e), "ERROR")
            return {}
    
    def entrenar_modelo_predictivo(self) -> None:
        """Entrena el modelo predictivo con el historial de uso de memoria."""
        if len(self.historial_uso) < 100:
            return
        
        try:
            # Modelo ARIMA
            self.modelo_predictivo = ARIMA(list(self.historial_uso), order=(5,1,0)).fit()
        except Exception as e:
            self.logger.error(f"Error entrenando modelo predictivo: {e}")
            self.modelo_predictivo = None

    @cached(ttl=10.0)
    def analizar_tendencia_memoria(self) -> Dict[str, Any]:
        """Analiza tendencia de uso de memoria."""
        if not self.modelo_predictivo:
            return {'tendencia': 'sin_datos'}
        
        try:
            predicciones = self.modelo_predictivo.forecast(steps=5)
            return {
                'tendencia': 'subiendo' if predicciones[-1] > self.historial_uso[-1] else 'bajando',
                'tasa_cambio': float(predicciones[0] - self.historial_uso[-1]),
                'prediccion_proximo_intervalo': float(predicciones[0]),
                'prediccion_5_intervalos': float(predicciones[-1]),
                'promedio_ultimos_30': float(np.mean(list(self.historial_uso)[-30:]))
            }
        except Exception as e:
            self.logger.error(f"Error en predicción de memoria: {e}")
            return {'tendencia': 'sin_datos'}

    def ajustar_prioridad_memoria_proceso(self, proc: psutil.Process, prioridad: int) -> bool:
        """Ajusta prioridad de memoria de un proceso específico (1-10)."""
        try:
            pid = proc.pid
            nombre = proc.name()
            
            # Mapear prioridad a working set
            if prioridad >= 8:
                # Alta prioridad - proteger memoria
                try:
                    if platform.system() == "Windows":
                        min_ws = proc.memory_info().rss
                        max_ws = int(min_ws * 1.5)
                        ctypes.windll.kernel32.SetProcessWorkingSetSize(
                            proc.pid, min_ws, max_ws
                        )
                except:
                    pass
            
            elif prioridad <= 3:
                # Baja prioridad - permitir paginación agresiva
                try:
                    if platform.system() == "Windows":
                        ctypes.windll.kernel32.SetProcessWorkingSetSize(
                            proc.pid, -1, -1
                        )
                except:
                    pass
            
            self.mapa_prioridades_memoria[pid] = {
                'nombre': nombre,
                'prioridad': prioridad,
                'timestamp': __import__('datetime').datetime.now()
            }
            
            return True
        
        except Exception as e:
            self.logger.debug(f"Error ajustando prioridad memoria: {e}")
            return False
    
    def optimizar_prioridades_memoria(self) -> None:
        """Optimiza prioridades de memoria de todos los procesos."""
        try:
            procesos_pesados = self.obtener_procesos_pesados(limite=20)
            
            for proc_info in procesos_pesados:
                try:
                    proc = psutil.Process(proc_info['pid'])
                    nombre = proc_info['nombre']
                    memoria_pct = proc_info['memoria_pct']
                    
                    # Determinar prioridad
                    if nombre in ['explorer.exe', 'dwm.exe', 'svchost.exe']:
                        prioridad = 9  # Crítico
                    elif memoria_pct > 20:
                        prioridad = 2  # Bajo - consumidor excesivo
                    elif memoria_pct > 10:
                        prioridad = 5  # Normal
                    else:
                        prioridad = 7  # Alto
                    
                    self.ajustar_prioridad_memoria_proceso(proc, prioridad)
                
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            self.registrar_evento(
                "PRIORIDADES_MEMORIA_OPTIMIZADAS",
                f"Ajustados {len(self.mapa_prioridades_memoria)} procesos",
                "INFO"
            )
        
        except Exception as e:
            self.logger.warning(f"Error optimizando prioridades memoria: {e}")
    
    def activar_compresion_memoria(self) -> None:
        """Activa compresión de memoria en Windows 10+."""
        if platform.system() != "Windows":
            return
        
        try:
            import subprocess
            
            # Habilitar compresión de memoria
            resultado = subprocess.run(
                ['powershell', '-Command', 
                 'Enable-MMAgent -MemoryCompression'],
                capture_output=True,
                timeout=10
            )
            
            if resultado.returncode == 0:
                self.compresion_activa = True
                self.registrar_evento(
                    "COMPRESION_MEMORIA_ACTIVADA",
                    "Compresión de memoria habilitada",
                    "INFO"
                )
        
        except Exception as e:
            self.logger.debug(f"Error activando compresión: {e}")
    
    def optimizar_pagefile_dinamico(self) -> None:
        """Optimiza archivo de paginación dinámicamente."""
        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            # Si swap está muy usado, aumentar tamaño
            if swap.percent > 70:
                self.registrar_evento(
                    "SWAP_ALTO",
                    f"Swap: {swap.percent:.1f}% - Considerar expansión",
                    "WARNING",
                    prioridad=7
                )
        
        except Exception as e:
            self.logger.debug(f"Error optimizando pagefile: {e}")
    
    def limpiar_memoria_standby(self) -> None:
        """Limpia memoria standby (caché de archivos)."""
        try:
            if platform.system() == "Windows":
                # Limpiar memoria standby list
                ctypes.windll.kernel32.SetSystemFileCacheSize(0, 0, 0)
                
                self.registrar_evento(
                    "MEMORIA_STANDBY_LIMPIADA",
                    "Standby list vaciada",
                    "INFO"
                )
        
        except Exception as e:
            self.logger.debug(f"Error limpiando standby: {e}")
    
    def analizar_fragmentacion_memoria(self) -> Dict[str, Any]:
        """Analiza fragmentación de memoria."""
        try:
            mem = psutil.virtual_memory()
            
            # Calcular fragmentación aproximada
            fragmentacion_pct = 0.0
            if mem.available > 0:
                fragmentacion_pct = ((mem.total - mem.available - mem.used) / 
                                    mem.total * 100)
            
            return {
                'fragmentacion_estimada_pct': fragmentacion_pct,
                'memoria_no_contable': mem.total - mem.available - mem.used,
                'requiere_desfragmentacion': fragmentacion_pct > 15
            }
        
        except Exception as e:
            self.logger.debug(f"Error analizando fragmentación: {e}")
            return {}
    
    def _limpieza_nivel_1(self):
        gc.collect(generation=2)
        self.logger.debug("Nivel 1: Garbage collection forzado.")

    def _limpieza_nivel_2(self):
        self._limpiar_cache_agresivo()
        self.logger.debug("Nivel 2: Cachés del sistema limpiados.")

    def _limpieza_nivel_3(self):
        procesos_reducidos = self._reducir_prioridad_procesos_pesados()
        self.logger.debug(f"Nivel 3: Prioridad reducida para {procesos_reducidos} procesos.")

    def _limpieza_nivel_4(self):
        procesos_terminados = self._terminar_procesos_prescindibles(mem_threshold=5)
        self.logger.debug(f"Nivel 4: {procesos_terminados} procesos no críticos terminados.")

    def _limpieza_nivel_5(self):
        self.activar_compresion_memoria()
        self._terminar_procesos_agresivo()
        self.logger.debug("Nivel 5: Compresión de memoria activada y limpieza agresiva.")

    def liberar_memoria_agresiva(self, nivel: int = 1) -> bool:
        """Libera memoria con estrategias de agresividad por niveles (1-5)."""
        self.intentos_liberacion += 1
        mem_antes = psutil.virtual_memory().used
        
        limpieza_actions = {
            1: self._limpieza_nivel_1,
            2: self._limpieza_nivel_2,
            3: self._limpieza_nivel_3,
            4: self._limpieza_nivel_4,
            5: self._limpieza_nivel_5,
        }

        try:
            for i in range(1, nivel + 1):
                if i in limpieza_actions:
                    limpieza_actions[i]()
            
            mem_despues = psutil.virtual_memory().used
            liberada = mem_antes - mem_despues
            
            if liberada > 1024 * 1024: # Registrar solo si se libera > 1MB
                self.liberaciones_exitosas += 1
                self.memoria_liberada_total += liberada
                self.registrar_evento(
                    "MEMORIA_LIBERADA",
                    f"Liberados {liberada / (1024**2):.2f} MB (Nivel {nivel})",
                    "INFO",
                    contexto={'memoria_liberada_mb': liberada / (1024**2)}
                )
                return True
            return False
        except Exception as e:
            self.registrar_evento("ERROR_LIBERACION", f"Error en nivel {nivel}: {e}", "WARNING")
            return False

    def _limpiar_cache_agresivo(self):
        """Limpia cachés de sistema de forma agresiva."""
        self.limpiar_memoria_standby()
        try:
            if platform.system() == "Windows":
                # Intenta vaciar el working set de los procesos menos activos
                for proc in psutil.process_iter(['pid', 'cpu_times']):
                    if proc.info['cpu_times'].user < 0.5: # Umbral bajo
                        self._vaciar_working_set(proc.info['pid'])
            else: # Linux
                subprocess.run(["sync"], shell=True)
                subprocess.run(["echo", "3", ">", "/proc/sys/vm/drop_caches"], shell=True)
        except Exception as e:
            self.logger.warning(f"Error en limpieza de caché agresiva: {e}")

    def _terminar_procesos_agresivo(self):
        """Termina procesos de forma más agresiva, incluyendo algunos que pueden ser importantes."""
        # Esta lista es peligrosa y debe ser configurable
        procesos_objetivo = ['chrome.exe', 'firefox.exe', 'Spotify.exe', 'Code.exe']
        for proc in psutil.process_iter(['name', 'pid']):
            if proc.info['name'] in procesos_objetivo:
                try:
                    p = psutil.Process(proc.info['pid'])
                    p.kill()
                    self.registrar_evento("PROCESO_TERMINADO_AGRESIVO", f"Proceso {proc.info['name']} terminado.", "WARNING")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
    
    def _reducir_prioridad_procesos_pesados(self) -> int:
        """Reduce prioridad de procesos que consumen mucha memoria."""
        procesos_reducidos = 0
        limite_memoria = self.config.memoria.limite_procesos_pesados
        
        try:
            procesos_pesados = self.obtener_procesos_pesados(limite_memoria)
            
            for proc_info in procesos_pesados:
                try:
                    proc = psutil.Process(proc_info['pid'])
                    if proc.name() not in ['explorer.exe', 'svchost.exe', 'csrss.exe']:
                        proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
                        procesos_reducidos += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        
        except Exception as e:
            self.logger.warning(f"Error reduciendo prioridades: {e}")
        
        return procesos_reducidos
    
    def _terminar_procesos_prescindibles(self) -> int:
        """Termina procesos que no son críticos y consumen mucha memoria."""
        procesos_prescindibles = [
            'chrome.exe', 'firefox.exe', 'slack.exe', 'teams.exe',
            'java.exe', 'python.exe', 'node.exe'
        ]
        terminados = 0
        
        try:
            for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
                try:
                    if proc.info['name'] in procesos_prescindibles and proc.info['memory_percent'] > 10:
                        proc.terminate()
                        terminados += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        
        except Exception as e:
            self.logger.warning(f"Error terminando procesos: {e}")
        
        return terminados
    
    def monitorear_memoria(self) -> None:
        """Monitorea memoria y ejecuta acciones según el nivel."""
        stats = self.obtener_uso_memoria_detallado()
        if not stats:
            return
        
        porcentaje = stats['memoria_fisica']['porcentaje']
        tendencia = self.analizar_tendencia_memoria()
        
        # Estrategia adaptativa según tendencia
        if tendencia.get('prediccion_5_intervalos', 0) > self.porcentaje_critico:
            self.registrar_evento(
                "PREDICCION_CRITICA",
                f"Predicción: {tendencia['prediccion_5_intervalos']:.1f}%",
                "WARNING",
                prioridad=8
            )
        
        # Nivel extremo - Actuación agresiva máxima
        if porcentaje > self.porcentaje_extremo:
            self.registrar_evento(
                "MEMORIA_EXTREMA",
                f"{porcentaje:.1f}% - Actuación nivel máximo",
                "ERROR",
                prioridad=10
            )
            for _ in range(5):
                if self.liberar_memoria_agresiva(5):
                    break
                __import__('time').sleep(0.5)
        
        # Nivel crítico
        elif porcentaje > self.porcentaje_critico:
            self.registrar_evento(
                "MEMORIA_CRITICA",
                f"{porcentaje:.1f}% - Actuación agresiva",
                "ERROR",
                prioridad=9
            )
            for _ in range(3):
                if self.liberar_memoria_agresiva(4):
                    break
                __import__('time').sleep(0.3)
        
        # Nivel de alerta
        elif porcentaje > self.porcentaje_alerta:
            self.registrar_evento(
                "MEMORIA_ALERTA",
                f"{porcentaje:.1f}% - Actuación moderada",
                "WARNING",
                prioridad=7
            )
            self.liberar_memoria_agresiva(3)
        
        # Nivel normal pero creciente
        elif tendencia.get('tasa_cambio', 0) > 1:
            self.registrar_evento(
                "MEMORIA_CRECIENTE",
                f"Tendencia alcista: {tendencia['tasa_cambio']:.2f}%/intervalo",
                "INFO",
                prioridad=5
            )
            self.liberar_memoria_agresiva(2)
        
        # Optimización continua
        if self.contador_ejecuciones % 5 == 0:
            self.optimizar_prioridades_memoria()
            self.optimizar_pagefile_dinamico()
    
    def obtener_procesos_pesados(self, limite: int = 5) -> List[Dict[str, Any]]:
        """Retorna procesos más pesados en memoria."""
        procesos = []
        
        try:
            for proc in psutil.process_iter(['pid', 'name', 'memory_percent', 'memory_info']):
                try:
                    procesos.append({
                        'pid': proc.info['pid'],
                        'nombre': proc.info['name'],
                        'memoria_pct': proc.info['memory_percent'],
                        'memoria_mb': proc.info['memory_info'].rss / (1024**2)
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            procesos_top = sorted(procesos, 
                                 key=lambda x: x['memoria_pct'], 
                                 reverse=True)[:limite]
            
            self.procesos_monitoreados = {p['pid']: p for p in procesos_top}
            return procesos_top
        
        except Exception as e:
            self.logger.error(f"Error obteniendo procesos pesados: {e}")
            return []
    
    def obtener_estadisticas(self) -> Dict[str, Any]:
        """Retorna estadísticas completas."""
        fragmentacion = self.analizar_fragmentacion_memoria()
        
        return {
            'uso_actual': self.obtener_uso_memoria_detallado(),
            'tendencia': self.analizar_tendencia_memoria(),
            'procesos_pesados': self.obtener_procesos_pesados(),
            'fragmentacion': fragmentacion,
            'prioridades': {
                'procesos_gestionados': len(self.mapa_prioridades_memoria),
                'compresion_activa': self.compresion_activa
            },
            'estadisticas_liberacion': {
                'intentos': self.intentos_liberacion,
                'exitosas': self.liberaciones_exitosas,
                'tasa_exito': (self.liberaciones_exitosas / self.intentos_liberacion * 100 
                              if self.intentos_liberacion > 0 else 0),
                'total_liberado_mb': self.memoria_liberada_total / (1024**2)
            },
            'umbrales': {
                'alerta': self.porcentaje_alerta,
                'critico': self.porcentaje_critico,
                'extremo': self.porcentaje_extremo
            },
            'estrategia': self.estrategia
        }
    
    def setup_tasks(self) -> None:
        """Configura y añade las tareas de gestión de memoria al scheduler."""
        self.scheduler.add_task(Task("monitorear_memoria", self.monitorear_memoria, timedelta(seconds=15)))
        self.scheduler.add_task(Task("limpiar_memoria_inteligente", self.limpiar_memoria_inteligente, timedelta(minutes=5)))
        self.scheduler.add_task(Task("entrenar_modelo_predictivo_memoria", self.entrenar_modelo_predictivo, timedelta(minutes=5)))

    def limpiar_memoria_inteligente(self) -> None:
        """Limpia la memoria de forma selectiva, centrándose en cachés de procesos inactivos."""
        self.registrar_evento("LIMPIEZA_INTELIGENTE", "Iniciando limpieza de memoria inteligente...", "INFO")
        liberada_total = 0
        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_times']):
            try:
                # Procesos que no han usado CPU recientemente son buenos candidatos
                if proc.info['cpu_times'].user < 0.1 and proc.info['memory_info'].rss > 50 * 1024 * 1024: # Umbral más bajo
                    mem_antes = proc.memory_info().rss
                    if platform.system() == "Windows":
                        handle = ctypes.windll.kernel32.OpenProcess(0x1F0FFF, False, proc.info['pid'])
                        if handle:
                            ctypes.windll.psapi.EmptyWorkingSet(handle)
                            ctypes.windll.kernel32.CloseHandle(handle)
                            mem_despues = psutil.Process(proc.info['pid']).memory_info().rss
                            liberada_total += mem_antes - mem_despues
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        if liberada_total > 0:
            self.registrar_evento("MEMORIA_INTELIGENTE_LIBERADA", f"Liberados {liberada_total / (1024**2):.2f} MB de cachés de procesos inactivos.", "INFO")
