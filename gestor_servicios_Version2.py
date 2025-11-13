# gestor_servicios.py
"""
Gestor inteligente de servicios con recuperación automática, análisis avanzado,
watchdog de servicios críticos y detección de anomalías.
"""
from base_gestor import BaseGestor
from typing import Dict, List, Optional
import platform
import psutil
import subprocess
from collections import deque, defaultdict
import time

try:
    import wmi
    HAS_WMI = True
except ImportError:
    HAS_WMI = False

from datetime import timedelta

class GestorServicios(BaseGestor):
    def __init__(self):
        super().__init__("GestorServicios")
        
        if HAS_WMI and platform.system() == "Windows":
            self.conn = wmi.WMI()
        else:
            self.conn = None
        
        self.servicios_criticos = self.config.get('servicios.monitores_criticos', 
                                                  ["RpcSs", "DcomLaunch", "WinRM"])
        self.auto_recuperacion = self.config.get('servicios.auto_recuperacion', True)
        self.max_intentos_reinicio = self.config.get('servicios.reinicio_max_intentos', 3)
        
        self.historial_servicios = defaultdict(lambda: deque(maxlen=200))
        self.intentos_reinicio = defaultdict(int)
        self.recuperaciones_exitosas = 0
        self.servicios_problematicos = {}
        self.tiempos_respuesta = {}
        self.dependencias_mapa = {}
        
        self.logger.info(f"GestorServicios: {len(self.servicios_criticos)} servicios críticos")
    
    @cached(ttl=30) # Cachear por 30 segundos para reducir la carga de WMI
    def obtener_estado_servicios_detallado(self) -> Dict:
        """Obtiene estado detallado de todos los servicios, con cache."""
        if not self.conn:
            return self._obtener_servicios_linux()
        
        try:
            estados = {}
            for s in self.conn.Win32_Service():
                estado_info = {
                    'nombre': s.Name,
                    'display_name': s.DisplayName,
                    'estado': s.State,
                    'inicio': s.StartMode,
                    'proceso_id': s.ProcessId if s.ProcessId else 0,
                    'ruta_ejecutable': s.PathName,
                    'descripcion': s.Description if s.Description else "",
                    'dependencias': list(s.ServiceDependencies) if s.ServiceDependencies else [],
                    'es_critico': s.Name in self.servicios_criticos,
                    'cuenta': s.StartName if s.StartName else "LocalSystem"
                }
                
                self.historial_servicios[s.Name].append({
                    'timestamp': __import__('datetime').datetime.now(),
                    'estado': s.State
                })
                
                if estado_info['dependencias']:
                    self.dependencias_mapa[s.Name] = estado_info['dependencias']
                
                estados[s.Name] = estado_info
            
            return estados
        
        except Exception as e:
            self.registrar_evento("ERROR_LECTURA_SERVICIOS", str(e), "WARNING")
            return {}
    
    def _obtener_servicios_linux(self) -> Dict:
        """Obtiene servicios en Linux usando systemctl."""
        estados = {}
        
        try:
            output = subprocess.check_output(
                ["systemctl", "list-units", "--type=service", "--all"],
                universal_newlines=True,
                timeout=10
            )
            
            for linea in output.split('\n')[1:]:
                partes = linea.split()
                if len(partes) >= 3:
                    nombre = partes[0].replace('.service', '')
                    estado = partes[2]
                    
                    estados[nombre] = {
                        'nombre': nombre,
                        'estado': 'Running' if estado == 'active' else 'Stopped',
                        'inicio': 'Auto',
                        'es_critico': nombre in self.servicios_criticos
                    }
        
        except Exception as e:
            self.logger.debug(f"Error obteniendo servicios Linux: {e}")
        
        return estados
    
    def analizar_dependencias_servicio(self, nombre: str) -> Dict:
        """Analiza dependencias de un servicio."""
        try:
            dependencias = self.dependencias_mapa.get(nombre, [])
            dependientes = [k for k, v in self.dependencias_mapa.items() if nombre in v]
            
            return {
                'servicio': nombre,
                'depende_de': dependencias,
                'dependientes': dependientes,
                'cadena_critica': any(dep in self.servicios_criticos for dep in dependencias)
            }
        
        except Exception as e:
            self.logger.debug(f"Error analizando dependencias: {e}")
            return {}
    
    def verificar_servicios_criticos(self):
        """Verifica que los servicios críticos estén activos."""
        if not self.conn:
            return
        
        try:
            for nombre_critico in self.servicios_criticos:
                try:
                    servicios = self.conn.Win32_Service(Name=nombre_critico)
                    
                    if not servicios:
                        self.registrar_evento(
                            "SERVICIO_NO_ENCONTRADO",
                            f"Servicio crítico {nombre_critico} no existe",
                            "WARNING",
                            prioridad=7
                        )
                        continue
                    
                    servicio = servicios[0]
                    
                    if servicio.State != "Running":
                        self.registrar_evento(
                            "SERVICIO_DETENIDO",
                            f"Servicio crítico {nombre_critico} está {servicio.State}",
                            "ERROR",
                            prioridad=9
                        )
                        
                        if self.auto_recuperacion:
                            self._reiniciar_servicio(nombre_critico)
                
                except Exception as e:
                    self.logger.warning(f"Error verificando {nombre_critico}: {e}")
        
        except Exception as e:
            self.registrar_evento("ERROR_VERIFICACION", str(e), "ERROR")
    
    def _reiniciar_servicio(self, nombre: str) -> bool:
        """Reinicia un servicio específico con reintentos y manejo de errores robusto."""
        self.intentos_reinicio[nombre] += 1
        if self.intentos_reinicio[nombre] > self.max_intentos_reinicio:
            self.registrar_evento("REINICIO_FALLIDO_MAX_INTENTOS", f"{nombre} excedió el máximo de reintentos.", "ERROR", prioridad=10)
            return False

        try:
            if not self.conn:
                # Lógica para Linux
                subprocess.run(["sudo", "systemctl", "restart", f"{nombre}.service"], check=True, timeout=30)
                self.logger.info(f"Servicio {nombre} reiniciado vía systemctl.")
                return True

            servicios = self.conn.Win32_Service(Name=nombre)
            if not servicios:
                self.logger.error(f"Intento de reiniciar servicio inexistente: {nombre}")
                return False
            
            s = servicios[0]
            start_time = time.monotonic()

            if s.State == "Running":
                s.StopService()
                # Esperar a que el servicio se detenga
                time.sleep(3) # Un poco más de tiempo
            
            s.StartService()
            # Esperar a que el servicio inicie
            time.sleep(3)

            # Verificar el estado final
            s.refresh() # Actualizar el estado del objeto
            if s.State == "Running":
                duration = time.monotonic() - start_time
                self.tiempos_respuesta[nombre] = duration
                self.registrar_evento("SERVICIO_REINICIADO", f"{nombre} reiniciado exitosamente en {duration:.2f}s.", "INFO")
                self.recuperaciones_exitosas += 1
                self.intentos_reinicio[nombre] = 0
                return True
            else:
                raise RuntimeError(f"El servicio {nombre} no pudo iniciar, estado final: {s.State}")

        except Exception as e:
            self.registrar_evento("ERROR_REINICIO_SERVICIO", f"Fallo al reiniciar {nombre} (intento {self.intentos_reinicio[nombre]}): {e}", "ERROR")
            return False
    
    def optimizar_servicios_inicio(self):
        """Optimiza servicios de inicio automático."""
        try:
            if not self.conn:
                return
            
            servicios_deshabilitados = 0
            
            servicios_no_esenciales = [
                'WSearch', 'SysMain', 'DiagTrack', 'dmwappushservice',
                'RetailDemo', 'MapsBroker', 'WMPNetworkSvc'
            ]
            
            for nombre in servicios_no_esenciales:
                try:
                    servicios = self.conn.Win32_Service(Name=nombre)
                    if servicios:
                        s = servicios[0]
                        if s.StartMode == 'Auto':
                            s.ChangeStartMode('Manual')
                            servicios_deshabilitados += 1
                except:
                    pass
            
            if servicios_deshabilitados > 0:
                self.registrar_evento(
                    "SERVICIOS_INICIO_OPTIMIZADOS",
                    f"Deshabilitados {servicios_deshabilitados} servicios no esenciales",
                    "INFO"
                )
        
        except Exception as e:
            self.logger.debug(f"Error optimizando servicios inicio: {e}")
    
    def limpiar_procesos_huerfanos(self):
        """Elimina procesos muertos, zombies y huérfanos."""
        procesos_limpiados = 0
        
        try:
            for proc in psutil.process_iter(['pid', 'name', 'status', 'ppid']):
                try:
                    if proc.status() in [psutil.STATUS_DEAD, psutil.STATUS_ZOMBIE]:
                        try:
                            proc.kill()
                            procesos_limpiados += 1
                            self.logger.debug(f"Proceso muerto eliminado: {proc.name()} (PID:{proc.pid})")
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    
                    elif proc.ppid() <= 1:
                        if proc.name() not in ['svchost.exe', 'lsass.exe', 'services.exe']:
                            try:
                                proc.terminate()
                                procesos_limpiados += 1
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            if procesos_limpiados > 0:
                self.registrar_evento(
                    "PROCESOS_LIMPIADOS",
                    f"Procesos muertos/zombies eliminados: {procesos_limpiados}",
                    "INFO"
                )
        
        except Exception as e:
            self.logger.warning(f"Error limpiando procesos: {e}")
    
    def detectar_servicios_problematicos(self) -> List[Dict]:
        """Detecta servicios con comportamiento problemático."""
        problematicos = []
        
        try:
            for nombre, historial in self.historial_servicios.items():
                if len(historial) < 10:
                    continue
                
                cambios = 0
                for i in range(1, len(list(historial))):
                    if list(historial)[i]['estado'] != list(historial)[i-1]['estado']:
                        cambios += 1
                
                if cambios > 3:
                    problematicos.append({
                        'servicio': nombre,
                        'cambios_estado': cambios,
                        'inestabilidad': 'alta'
                    })
                    
                    if nombre not in self.servicios_problematicos:
                        self.registrar_evento(
                            "SERVICIO_INESTABLE",
                            f"{nombre} - {cambios} cambios de estado",
                            "WARNING",
                            prioridad=7
                        )
                    
                    self.servicios_problematicos[nombre] = cambios
        
        except Exception as e:
            self.logger.debug(f"Error detectando servicios problemáticos: {e}")
        
        return problematicos
    
    def monitorear_consumo_servicios(self) -> List[Dict]:
        """Monitorea consumo de recursos de servicios."""
        servicios_alto_consumo = []
        
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    if proc.info['cpu_percent'] > 50 or proc.info['memory_percent'] > 20:
                        servicios_alto_consumo.append({
                            'nombre': proc.info['name'],
                            'pid': proc.info['pid'],
                            'cpu_pct': proc.info['cpu_percent'],
                            'memoria_pct': proc.info['memory_percent']
                        })
                except:
                    pass
            
            if servicios_alto_consumo:
                self.registrar_evento(
                    "SERVICIOS_ALTO_CONSUMO",
                    f"Detectados {len(servicios_alto_consumo)} servicios con alto consumo",
                    "INFO"
                )
            
            return servicios_alto_consumo
        
        except Exception as e:
            self.logger.debug(f"Error monitoreando consumo: {e}")
            return []
    
    def crear_watchdog_servicios(self):
        """Crea watchdog para servicios críticos."""
        try:
            for servicio in self.servicios_criticos:
                dependencias = self.analizar_dependencias_servicio(servicio)
                
                for dep in dependencias.get('depende_de', []):
                    try:
                        servicios = self.conn.Win32_Service(Name=dep)
                        if servicios and servicios[0].State != "Running":
                            self.registrar_evento(
                                "DEPENDENCIA_CAIDA",
                                f"{servicio} depende de {dep} que está caído",
                                "WARNING",
                                prioridad=8
                            )
                            
                            if self.auto_recuperacion:
                                self._reiniciar_servicio(dep)
                    except:
                        pass
        
        except Exception as e:
            self.logger.debug(f"Error en watchdog: {e}")
    
    def obtener_estadisticas(self) -> Dict:
        """Retorna estadísticas detalladas."""
        servicios = self.obtener_estado_servicios_detallado()
        problematicos = self.detectar_servicios_problematicos()
        alto_consumo = self.monitorear_consumo_servicios()
        
        servicios_activos = sum(1 for s in servicios.values() if s.get('estado') == 'Running')
        servicios_criticos_activos = sum(1 for s in servicios.values() 
                                        if s.get('es_critico') and s.get('estado') == 'Running')
        
        return {
            'servicios_totales': len(servicios),
            'servicios_activos': servicios_activos,
            'servicios_criticos': len(self.servicios_criticos),
            'servicios_criticos_activos': servicios_criticos_activos,
            'problematicos': problematicos,
            'alto_consumo': alto_consumo,
            'estadisticas': {
                'recuperaciones_exitosas': self.recuperaciones_exitosas,
                'auto_recuperacion': self.auto_recuperacion,
                'tiempos_respuesta': self.tiempos_respuesta,
                'servicios': servicios
            }
        }
    
    def setup_tasks(self):
        """Configura y añade las tareas de gestión de servicios al scheduler."""
        scheduler.add_task(Task("obtener_estado_servicios", self.obtener_estado_servicios_detallado, timedelta(seconds=60)))
        scheduler.add_task(Task("verificar_servicios_criticos", self.verificar_servicios_criticos, timedelta(seconds=30)))
        scheduler.add_task(Task("crear_watchdog_servicios", self.crear_watchdog_servicios, timedelta(minutes=1)))
        scheduler.add_task(Task("limpiar_procesos_huerfanos", self.limpiar_procesos_huerfanos, timedelta(minutes=2)))
        scheduler.add_task(Task("detectar_servicios_problematicos", self.detectar_servicios_problematicos, timedelta(minutes=5)))
        scheduler.add_task(Task("monitorear_consumo_servicios", self.monitorear_consumo_servicios, timedelta(minutes=5)))
        scheduler.add_task(Task("optimizar_servicios_inicio", self.optimizar_servicios_inicio, timedelta(minutes=10)))

        # Suscripción a eventos de modo juego
        event_bus.subscribe("GameModeStarted", self._on_game_mode_started)
        event_bus.subscribe("GameModeStopped", self._on_game_mode_stopped)

    def _on_game_mode_started(self, event):
        """Desactiva servicios no esenciales al iniciar el modo juego."""
        self.registrar_evento("GAME_MODE_SERVICIOS", "Desactivando servicios no esenciales...", "INFO")
        servicios_a_desactivar = self.config.get('servicios.game_mode_disable', ['WSearch', 'SysMain', 'DiagTrack'])
        for servicio in servicios_a_desactivar:
            self._cambiar_estado_servicio(servicio, 'StopService')

    def _on_game_mode_stopped(self, event):
        """Reactiva servicios al detener el modo juego."""
        self.registrar_evento("GAME_MODE_SERVICIOS", "Reactivando servicios...", "INFO")
        servicios_a_reactivar = self.config.get('servicios.game_mode_disable', ['WSearch', 'SysMain', 'DiagTrack'])
        for servicio in servicios_a_reactivar:
            self._cambiar_estado_servicio(servicio, 'StartService')

    def _cambiar_estado_servicio(self, nombre: str, accion: str):
        """Inicia o detiene un servicio."""
        if not self.conn:
            return
        try:
            servicios = self.conn.Win32_Service(Name=nombre)
            if servicios:
                s = servicios[0]
                getattr(s, accion)()
        except Exception as e:
            self.logger.warning(f"Error cambiando estado de {nombre}: {e}")