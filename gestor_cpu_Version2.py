# gestor_cpu.py
"""
Gestor avanzado de CPU con balanceo inteligente, afinidad dinámica, predicción de carga
y gestión de prioridades de procesamiento.
"""
from base_gestor import BaseGestor, event_bus, Task, scheduler
import psutil
import os
from typing import Dict, List, Tuple, Any, Set
import numpy as np
from collections import deque
import threading
from statsmodels.tsa.arima.model import ARIMA
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense


from datetime import timedelta

class GestorCPU(BaseGestor):
    def __init__(self) -> None:
        super().__init__("GestorCPU")
        
        self.cpu_total: int = psutil.cpu_count(logical=True)
        self.cpu_fisico: int = psutil.cpu_count(logical=False)
        self.carga_nucleos: List[float] = [0.0] * self.cpu_total
        self.historial_carga: deque = deque(maxlen=500)
        self.proceso_actual: psutil.Process = psutil.Process()
        self.afinidad_dinamica: bool = self.config.cpu.afinidad_dinamica
        self.balanceo_inteligente: bool = self.config.cpu.balanceo_inteligente
        
        self.mapa_procesos_nucleos: Dict[int, int] = {}
        self.picos_detectados: int = 0
        self.balanceos_realizados: int = 0
        
        # Nuevas características de prioridades de procesamiento
        self.mapa_prioridades_cpu: Dict[int, Dict[str, Any]] = {}
        self.historial_prioridades: deque = deque(maxlen=300)
        self.procesos_tiempo_real: Set[int] = set()
        self.politicas_scheduling: Dict[str, Any] = {}
        
        # Modelo predictivo
        self.modelo_predictivo = None
        self._last_train_size = 0
        
        self.logger.info(f"GestorCPU: {self.cpu_fisico} físicos, {self.cpu_total} lógicos")
    
    def obtener_carga_nucleos_detallada(self) -> Dict[str, Any]:
        """Obtiene carga detallada por núcleo con estadísticas."""
        try:
            cargas = psutil.cpu_percent(interval=0.05, percpu=True)
            contexto = psutil.cpu_stats()
            freq = psutil.cpu_freq(percpu=False)
            
            self.carga_nucleos = cargas
            self.historial_carga.append(np.mean(cargas))
            
            return {
                'cargas_por_nucleo': cargas,
                'promedio': np.mean(cargas),
                'desviacion': float(np.std(cargas)),
                'minima': min(cargas),
                'maxima': max(cargas),
                'desbalance': max(cargas) - min(cargas),
                'frecuencia_actual': freq.current if freq else 0,
                'frecuencia_maxima': freq.max if freq else 0,
                'contextos': contexto.ctx_switches if contexto else 0,
                'interrupciones': contexto.interrupts if contexto else 0
            }
        except Exception as e:
            self.logger.error(f"Error obteniendo carga: {e}")
            return {}
    
    def ajustar_prioridad_cpu_proceso(self, proc: psutil.Process, prioridad: int, tiempo_real: bool = False) -> bool:
        """Ajusta prioridad de CPU de un proceso (1-10, 10=máxima)."""
        try:
            pid = proc.pid
            nombre = proc.name()
            
            # Mapear prioridad a clases de prioridad del sistema
            if tiempo_real or prioridad >= 9:
                clase_prioridad = psutil.REALTIME_PRIORITY_CLASS
            elif prioridad >= 7:
                clase_prioridad = psutil.HIGH_PRIORITY_CLASS
            elif prioridad >= 5:
                clase_prioridad = psutil.NORMAL_PRIORITY_CLASS
            elif prioridad >= 3:
                clase_prioridad = psutil.BELOW_NORMAL_PRIORITY_CLASS
            else:
                clase_prioridad = psutil.IDLE_PRIORITY_CLASS
            
            try:
                proc.nice(clase_prioridad)
                
                self.mapa_prioridades_cpu[pid] = {
                    'nombre': nombre,
                    'prioridad': prioridad,
                    'clase': clase_prioridad,
                    'tiempo_real': tiempo_real,
                    'timestamp': __import__('datetime').datetime.now()
                }
                
                if tiempo_real:
                    self.procesos_tiempo_real.add(pid)
                
                return True
            
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                return False
        
        except Exception as e:
            self.logger.debug(f"Error ajustando prioridad CPU: {e}")
            return False
    
    def optimizar_prioridades_procesamiento(self) -> None:
        """Optimiza prioridades de procesamiento de todos los procesos."""
        try:
            ajustes = 0
            
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'nice']):
                try:
                    nombre = proc.info['name']
                    cpu_pct = proc.info['cpu_percent']
                    
                    # Determinar prioridad óptima
                    if nombre in ['explorer.exe', 'dwm.exe']:
                        prioridad = 8  # Alta para UI crítica
                    elif nombre in ['svchost.exe', 'services.exe']:
                        prioridad = 7  # Alta para servicios
                    elif cpu_pct > 50:
                        prioridad = 3  # Baja para consumidores excesivos
                    elif cpu_pct > 20:
                        prioridad = 5  # Normal
                    else:
                        prioridad = 6  # Ligeramente alta para responsividad
                    
                    if self.ajustar_prioridad_cpu_proceso(proc, prioridad):
                        ajustes += 1
                
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            if ajustes > 0:
                self.registrar_evento(
                    "PRIORIDADES_CPU_OPTIMIZADAS",
                    f"Ajustados {ajustes} procesos",
                    "INFO"
                )
        
        except Exception as e:
            self.logger.warning(f"Error optimizando prioridades CPU: {e}")
    
    def gestionar_politicas_scheduling(self) -> None:
        """Gestiona políticas de scheduling avanzadas."""
        try:
            stats = self.obtener_carga_nucleos_detallada()
            
            if not stats:
                return

            # Si hay desbalance, aplicar políticas de rebalanceo
            if stats['desbalance'] > 30:
                self.aplicar_politica_balanceo_carga()
            
            # Si hay alta contención, reducir quantum
            if stats['contextos'] > 10000:
                self.aplicar_politica_reducir_contention()
        
        except Exception as e:
            self.logger.debug(f"Error gestionando políticas: {e}")
    
    def aplicar_politica_balanceo_carga(self) -> None:
        """Aplica política de balanceo de carga entre núcleos."""
        try:
            # Identificar núcleos sobrecargados
            nucleos_sobrecargados = [
                i for i, carga in enumerate(self.carga_nucleos) if carga > 80
            ]
            
            nucleos_libres = [
                i for i, carga in enumerate(self.carga_nucleos) if carga < 40
            ]
            
            if not nucleos_libres:
                return
            
            # Mover procesos desde núcleos sobrecargados
            for nucleo_sobrecargado in nucleos_sobrecargados:
                for proc in psutil.process_iter(['pid', 'cpu_num']):
                    try:
                        if proc.info['cpu_num'] == nucleo_sobrecargado:
                            nucleo_destino = min(nucleos_libres, 
                                                key=lambda i: self.carga_nucleos[i])
                            proc.cpu_affinity([nucleo_destino])
                            break  # Mover solo un proceso a la vez
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
        
        except Exception as e:
            self.logger.debug(f"Error aplicando balanceo: {e}")
    
    def aplicar_politica_reducir_contention(self) -> None:
        """Reduce contención de context switches."""
        try:
            # Aumentar afinidad de procesos pesados a núcleos específicos
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                try:
                    if proc.info['cpu_percent'] > 30:
                        # Fijar a un núcleo específico
                        nucleos_disponibles = list(range(self.cpu_total))
                        nucleo_asignado = proc.info['pid'] % self.cpu_total
                        proc.cpu_affinity([nucleos_disponibles[nucleo_asignado]])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        
        except Exception as e:
            self.logger.debug(f"Error reduciendo contención: {e}")
    
    def detectar_anomalias_cpu(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        """Detecta anomalías y situaciones anómalas en CPU."""
        anomalias: Dict[str, Any] = {
            'picos_detallados': [],
            'desbalance_critico': False,
            'contention_context_switches': False,
            'throttling': False
        }
        
        if not stats:
            return anomalias
        
        # Detectar picos
        if stats['maxima'] > 90:
            anomalias['picos_detallados'].append({
                'tipo': 'pico_alto',
                'valor': stats['maxima'],
                'nucleo_critico': stats['cargas_por_nucleo'].index(max(stats['cargas_por_nucleo']))
            })
            self.picos_detectados += 1
        
        # Detectar desbalance crítico
        if stats['desbalance'] > 40 and stats['promedio'] > 50:
            anomalias['desbalance_critico'] = True
            self.registrar_evento(
                "DESBALANCE_CPU_CRITICO",
                f"Desbalance: {stats['desbalance']:.1f}%, "
                f"Min: {stats['minima']:.1f}%, Max: {stats['maxima']:.1f}%",
                "WARNING",
                prioridad=8
            )
        
        # Detectar context switch contention
        if stats['contextos'] > 5000 and stats['promedio'] > 70:
            anomalias['contention_context_switches'] = True
            self.registrar_evento(
                "CONTENTION_CONTEXT_SWITCHES",
                f"Context switches: {stats['contextos']}",
                "WARNING"
            )
        
        return anomalias
    
    def entrenar_modelo_predictivo(self) -> None:
        """Entrena o actualiza el modelo predictivo de forma incremental."""
        current_data_size = len(self.historial_carga)
        if current_data_size < 100 or current_data_size <= self._last_train_size:
            return

        try:
            data = list(self.historial_carga)
            if self.modelo_predictivo and self._last_train_size > 0:
                # Re-entrenamiento incremental (append de nuevos datos)
                new_data = data[self._last_train_size:]
                self.modelo_predictivo = self.modelo_predictivo.append(new_data, refit=True)
            else:
                # Entrenamiento inicial
                self.modelo_predictivo = ARIMA(data, order=(5,1,0)).fit()
            
            self._last_train_size = current_data_size
            self.logger.info("Modelo predictivo de CPU actualizado.")

        except Exception as e:
            self.logger.error(f"Error al entrenar modelo predictivo de CPU: {e}")
            self.modelo_predictivo = None

    def predecir_carga_futura(self) -> Dict[str, Any]:
        """Predice la carga futura de CPU usando el modelo ARIMA."""
        if not self.modelo_predictivo:
            return {'prediccion_disponible': False}
        
        try:
            predicciones = self.modelo_predictivo.forecast(steps=10)
            return {
                'prediccion_disponible': True,
                'predicciones_proximos_10': predicciones.tolist(),
                'tendencia': 'subiendo' if predicciones[-1] > self.historial_carga[-1] else 'bajando',
                'carga_esperada_max': max(predicciones),
                'tiempo_hasta_pico': np.argmax(predicciones) if any(predicciones) else 0
            }
        except Exception as e:
            self.logger.error(f"Error en predicción: {e}")
            return {'prediccion_disponible': False}

    def distribuir_carga_inteligente(self) -> None:
        """Distribuye procesos inteligentemente entre núcleos."""
        if not self.balanceo_inteligente:
            return
        
        try:
            stats = self.obtener_carga_nucleos_detallada()
            if not stats:
                return
            anomalias = self.detectar_anomalias_cpu(stats)
            
            if stats['desbalance'] < 15:
                return
            
            # Obtener núcleos ordenados por carga
            nucleos_ordenados = sorted(
                range(self.cpu_total),
                key=lambda i: self.carga_nucleos[i]
            )
            
            # Redistribuir procesos
            procesos_movidos = 0
            for idx, proc in enumerate(psutil.process_iter(['pid', 'name', 'cpu_num'])):
                try:
                    if proc.info['cpu_num'] is not None:
                        # Asignar al núcleo menos cargado
                        nucleo_ideal = nucleos_ordenados[idx % self.cpu_total]
                        
                        if proc.info['cpu_num'] != nucleo_ideal:
                            proc.cpu_affinity([nucleo_ideal])
                            procesos_movidos += 1
                
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            if procesos_movidos > 0:
                self.balanceos_realizados += 1
                self.registrar_evento(
                    "REBALANCEO_CPU",
                    f"Procesos movidos: {procesos_movidos}, Desbalance: {stats['desbalance']:.1f}%",
                    "INFO"
                )
        
        except Exception as e:
            self.registrar_evento("ERROR_BALANCEO", str(e), "ERROR")
    
    def optimizar_afinidad_dinamica(self) -> None:
        """Optimiza afinidad dinámica de procesos según patrones."""
        if not self.afinidad_dinamica:
            return
        
        try:
            stats = self.obtener_carga_nucleos_detallada()
            if not stats:
                return
            
            # Estrategia 1: Procesos críticos en núcleos menos cargados
            procesos_criticos = ['explorer.exe', 'dwm.exe', 'svchost.exe']
            
            nucleos_optimales = sorted(
                range(self.cpu_total),
                key=lambda i: self.carga_nucleos[i]
            )[:2]
            
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] in procesos_criticos:
                        proc.cpu_affinity(nucleos_optimales)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # Estrategia 2: Aislar cargas pesadas
            if stats['maxima'] > 80:
                nucleo_sobrecargado = self.carga_nucleos.index(max(self.carga_nucleos))
                
                # Mover procesos pesados DESDE el núcleo sobrecargado
                for proc in psutil.process_iter(['pid', 'name', 'cpu_num']):
                    try:
                        if (proc.info['cpu_num'] == nucleo_sobrecargado and
                            proc.memory_percent() > 5):
                            nucleos_alternativos = [
                                i for i in range(self.cpu_total) 
                                if i != nucleo_sobrecargado
                            ]
                            nucleo_nuevo = min(
                                nucleos_alternativos,
                                key=lambda i: self.carga_nucleos[i]
                            )
                            proc.cpu_affinity([nucleo_nuevo])
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
        
        except Exception as e:
            self.logger.warning(f"Error optimizando afinidad: {e}")
    
    def ajustar_prioridades_segun_carga(self) -> None:
        """Ajusta prioridades según estado actual de CPU."""
        try:
            stats = self.obtener_carga_nucleos_detallada()
            if not stats:
                return

            if stats['promedio'] > 85:
                # Reducir prioridades de procesos no críticos
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if proc.info['name'] not in [
                            'explorer.exe', 'dwm.exe', 'svchost.exe',
                            'services.exe', 'lsass.exe'
                        ]:
                            proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
        
        except Exception as e:
            self.logger.debug(f"Error ajustando prioridades: {e}")
    
    def obtener_estadisticas(self) -> Dict[str, Any]:
        """Retorna estadísticas completas."""
        stats = self.obtener_carga_nucleos_detallada()
        prediccion = self.predecir_carga_futura()
        anomalias = self.detectar_anomalias_cpu(stats)
        
        return {
            'nucleos': {
                'total': self.cpu_total,
                'fisicos': self.cpu_fisico
            },
            'carga': stats,
            'anomalias': anomalias,
            'prediccion': prediccion,
            'prioridades': {
                'procesos_gestionados': len(self.mapa_prioridades_cpu),
                'procesos_tiempo_real': len(self.procesos_tiempo_real)
            },
            'estadisticas_operacion': {
                'picos_detectados': self.picos_detectados,
                'balanceos_realizados': self.balanceos_realizados,
                'promedio_historial': float(np.mean(list(self.historial_carga))) 
                                      if self.historial_carga else 0
            }
        }
    
    def setup_tasks(self) -> None:
        """Configura y añade las tareas de optimización de CPU al scheduler."""
        scheduler.add_task(Task("obtener_carga_cpu", self.obtener_carga_nucleos_detallada, timedelta(seconds=2)))
        scheduler.add_task(Task("distribuir_carga_cpu", self.distribuir_carga_inteligente, timedelta(seconds=10)))
        scheduler.add_task(Task("optimizar_afinidad_cpu", self.optimizar_afinidad_dinamica, timedelta(seconds=15)))
        scheduler.add_task(Task("ajustar_prioridades_cpu", self.ajustar_prioridades_segun_carga, timedelta(seconds=20)))
        scheduler.add_task(Task("optimizar_afinidad_hilos", self.optimizar_afinidad_hilos, timedelta(seconds=30)))
        scheduler.add_task(Task("entrenar_modelo_predictivo", self.entrenar_modelo_predictivo, timedelta(minutes=5)))

        # Suscripción a eventos de modo juego
        event_bus.subscribe("GameModeStarted", self._on_game_mode_started)
        event_bus.subscribe("GameModeStopped", self._on_game_mode_stopped)

    def _on_game_mode_started(self, event: Any) -> None:
        """Reduce la prioridad de procesos no críticos."""
        self.registrar_evento("GAME_MODE_CPU", "Reduciendo prioridad de procesos de fondo...", "INFO")
        self._manage_background_processes(lower_priority=True)

    def _on_game_mode_stopped(self, event: Any) -> None:
        """Restaura la prioridad de los procesos."""
        self.registrar_evento("GAME_MODE_CPU", "Restaurando prioridad de procesos...", "INFO")
        self._manage_background_processes(lower_priority=False)

    def _manage_background_processes(self, lower_priority: bool) -> None:
        """Reduce o restaura la prioridad de procesos no críticos."""
        procesos_no_criticos = self.config.cpu.non_critical_processes
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] in procesos_no_criticos:
                    if lower_priority:
                        proc.nice(psutil.IDLE_PRIORITY_CLASS)
                    else:
                        proc.nice(psutil.NORMAL_PRIORITY_CLASS)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    def optimizar_afinidad_hilos(self) -> None:
        """Optimiza la afinidad de los hilos de procesos de alta carga."""
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
            try:
                if proc.info['cpu_percent'] > 50:
                    threads = proc.threads()
                    if len(threads) > 1:
                        # Asignar hilos a núcleos menos cargados
                        nucleos_ordenados = sorted(
                            range(self.cpu_total),
                            key=lambda i: self.carga_nucleos[i]
                        )
                        for i, thread in enumerate(threads):
                            nucleo = nucleos_ordenados[i % self.cpu_total]
                            p = psutil.Process(thread.id)
                            p.cpu_affinity([nucleo])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
