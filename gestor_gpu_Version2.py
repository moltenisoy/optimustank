# gestor_gpu.py
"""
Gestor avanzado de GPU con soporte NVIDIA, AMD e Intel, optimización dinámica,
overclocking seguro, undervolting y gestión térmica avanzada.
"""
from base_gestor_Version2 import BaseGestor
from reliability_utils import circuit_breaker
import subprocess
from typing import Optional, Dict, List
import re
import threading
from collections import deque
from datetime import timedelta
from platform_threading import PlatformAdapterFactory

class GestorGPU(BaseGestor):
    def __init__(self):
        super().__init__("GestorGPU")
        
        self.adapter = PlatformAdapterFactory.create_adapter()
        self.dependencies_available = self._check_dependencies()
        if not self.dependencies_available:
            self.logger.warning("GPU dependencies not found. Disabling GestorGPU.")
            self.activo = False
            return  # Salir si no hay dependencias
        
        self.umbrales = {
            'uso': self.config.gpu.uso_umbral,
            'temperatura': self.config.gpu.temperatura_alerta,
            'temperatura_critica': self.config.gpu.temperatura_critica,
            'memoria': 95,
            'power_limit': 100
        }
        
        self.boost_dinamico = self.config.gpu.boost_dinamico
        self.power_limit_tuning = self.config.gpu.power_limit_tuning
        self.undervolting_habilitado = self.config.gpu.undervolting
        
        self.historial_metricas = {}
        self.optimizaciones_aplicadas = 0
        self.throttlings_detectados = 0
        self.perfiles_oc = {}
        
        # Determinar tipo de GPU
        self.tipo_gpu = self.adapter.get_gpu_type()
        
        self.logger.info(f"GestorGPU: Adapter seleccionado={self.adapter.__class__.__name__}, GPU tipo={self.tipo_gpu}")

    @circuit_breaker(failure_threshold=3, timeout=30.0)
    def obtener_metricas_nvidia_detalladas(self) -> Optional[Dict]:
        """Obtiene métricas detalladas de GPU NVIDIA usando la librería pynvml."""
        try:
            from pynvml import nvmlInit, nvmlDeviceGetCount, nvmlDeviceGetHandleByIndex, nvmlDeviceGetUtilizationRates, nvmlDeviceGetTemperature, nvmlDeviceGetMemoryInfo, nvmlDeviceGetPowerUsage
            
            nvmlInit()
            metrics = {}
            device_count = nvmlDeviceGetCount()
            
            for i in range(device_count):
                handle = nvmlDeviceGetHandleByIndex(i)
                util = nvmlDeviceGetUtilizationRates(handle)
                temp = nvmlDeviceGetTemperature(handle, 0) # 0 for GPU core
                mem_info = nvmlDeviceGetMemoryInfo(handle)
                power = nvmlDeviceGetPowerUsage(handle) / 1000.0 # Convert mW to W
                
                metrics[f'gpu_{i}'] = {
                    'uso_gpu_pct': util.gpu,
                    'temperatura_c': temp,
                    'memoria_usada_mb': mem_info.used / (1024**2),
                    'memoria_total_mb': mem_info.total / (1024**2),
                    'potencia_w': power,
                }
            return metrics
        except Exception as e:
            self.logger.error(f"Error obteniendo métricas de NVIDIA con pynvml: {e}")
            raise

    def aplicar_undervolt_nvidia(self, offset_mv: int = -100):
        """Aplica undervolting a GPU NVIDIA."""
        # Esta funcionalidad es compleja y a menudo no está expuesta directamente.
        # Se mantiene el enfoque original con nvidia-settings como fallback.
        if not self.undervolting_habilitado:
            return
        
        try:
            subprocess.run(
                ["nvidia-settings", "-a", f"[gpu:0]/GPUGraphicsClockOffset[3]={offset_mv}"],
                capture_output=True,
                timeout=5
            )
            
            self.registrar_evento(
                "UNDERVOLT_APLICADO",
                f"Offset: {offset_mv}mV",
                "INFO"
            )
        
        except Exception as e:
            self.logger.debug(f"Error aplicando undervolt: {e}")
    
    def aplicar_overclock_seguro(self, gpu_id: str, offset_mhz: int = 100):
        """Aplica overclock seguro a GPU."""
        try:
            self.adapter.apply_overclock(gpu_id, offset_mhz)
            
            self.perfiles_oc[gpu_id] = {
                'offset_gpu': offset_mhz,
                'timestamp': __import__('datetime').datetime.now()
            }
            
            self.registrar_evento(
                "OVERCLOCK_APLICADO",
                f"{gpu_id}: +{offset_mhz}MHz",
                "INFO"
            )
        
        except Exception as e:
            self.logger.debug(f"Error aplicando OC: {e}")
    
    def gestionar_curva_ventiladores(self, temperatura: float):
        """Gestiona curva de ventiladores según temperatura."""
        try:
            if temperatura < 50:
                velocidad = 30
            elif temperatura < 60:
                velocidad = 40
            elif temperatura < 70:
                velocidad = 60
            elif temperatura < 80:
                velocidad = 80
            else:
                velocidad = 100
            
            if self.tipo_gpu == "NVIDIA":
                subprocess.run(
                    ["nvidia-settings", "-a", f"[gpu:0]/GPUFanControlState=1",
                     "-a", f"[fan:0]/GPUTargetFanSpeed={velocidad}"],
                    capture_output=True,
                    timeout=5
                )
        
        except Exception as e:
            self.logger.debug(f"Error ajustando ventiladores: {e}")
    
    def optimizar_power_limit_dinamico(self, uso_gpu: float, temperatura: float):
        """Optimiza power limit dinámicamente."""
        if not self.power_limit_tuning:
            return
        
        try:
            if temperatura > 80:
                power_limit = 200
            elif uso_gpu < 30:
                power_limit = 180
            else:
                power_limit = 220
            
            if self.tipo_gpu == "NVIDIA":
                subprocess.run(
                    ["nvidia-smi", "-pl", str(power_limit)],
                    capture_output=True,
                    timeout=5
                )
        
        except Exception as e:
            self.logger.debug(f"Error ajustando power limit: {e}")
    
    def detectar_throttling(self, metricas: Dict) -> bool:
        """Detecta si hay throttling térmico o de potencia."""
        try:
            for gpu_id, info in metricas.items():
                temperatura = info.get('temperatura_c', 0)
                power_uso = info.get('potencia', {}).get('uso_pct', 0)
                
                if temperatura > self.umbrales['temperatura_critica']:
                    return True
                
                if power_uso > 95:
                    return True
            
            return False
        
        except Exception as e:
            self.logger.debug(f"Error detectando throttling: {e}")
            return False
    
    def optimizar_memoria_gpu(self):
        """Optimiza uso de memoria de GPU."""
        try:
            if self.tipo_gpu == "NVIDIA":
                subprocess.run(
                    ["nvidia-smi", "--compute-mode=EXCLUSIVE_PROCESS"],
                    capture_output=True,
                    timeout=5
                )
                
                self.registrar_evento(
                    "MEMORIA_GPU_OPTIMIZADA",
                    "Modo compute exclusivo activado",
                    "INFO"
                )
        
        except Exception as e:
            self.logger.debug(f"Error optimizando memoria GPU: {e}")
    
    def optimizar_gpu_dinamico(self):
        """Optimiza GPU con boost dinámico y power management."""
        metricas = self.adapter.get_gpu_metrics()
        
        if not metricas:
            return
        
        try:
            for gpu_id, gpu_info in metricas.items():
                uso_gpu = gpu_info.get('uso_gpu_pct', 0)
                temperatura = gpu_info.get('temperatura_c', 0)
                memoria_pct = gpu_info.get('uso_memoria_pct', gpu_info.get('memoria', {}).get('uso_pct', 0))
                
                self.metricas.registrar(f'{gpu_id}_uso', uso_gpu, tags={'temp': temperatura})
                self.metricas.registrar(f'{gpu_id}_memoria', memoria_pct)
                self.metricas.registrar(f'{gpu_id}_temperatura', temperatura)
                
                if gpu_id not in self.historial_metricas:
                    self.historial_metricas[gpu_id] = deque(maxlen=100)
                self.historial_metricas[gpu_id].append({
                    'uso': uso_gpu,
                    'temperatura': temperatura,
                    'memoria': memoria_pct
                })
                
                if temperatura > self.umbrales['temperatura_critica']:
                    self.throttlings_detectados += 1
                    self.registrar_evento(
                        "GPU_TEMPERATURA_CRITICA",
                        f"{gpu_id}: {temperatura:.1f}°C - Throttling probable",
                        "ERROR",
                        prioridad=10
                    )
                    self._aplicar_cooling_agresivo()
                
                elif temperatura > self.umbrales['temperatura']:
                    self.registrar_evento(
                        "GPU_TEMPERATURA_ALERTA",
                        f"{gpu_id}: {temperatura:.1f}°C",
                        "WARNING",
                        prioridad=8
                    )
                
                self.gestionar_curva_ventiladores(temperatura)
                self.optimizar_power_limit_dinamico(uso_gpu, temperatura)
                
                if self.boost_dinamico and uso_gpu < 40 and temperatura < 60:
                    self._activar_boost_gpu()
                    self.optimizaciones_aplicadas += 1
                
                if self.detectar_throttling(metricas):
                    self.aplicar_undervolt_nvidia(-120)
        
        except Exception as e:
            self.registrar_evento("ERROR_OPTIMIZACION_GPU", str(e), "WARNING")
    
    def _activar_boost_gpu(self):
        """Activa boost de GPU si está disponible."""
        try:
            if self.tipo_gpu == "NVIDIA":
                subprocess.run(["nvidia-smi", "-pm", "1"], capture_output=True, timeout=5)
                subprocess.run(["nvidia-smi", "-lgc", "0,2100"], capture_output=True, timeout=5)
        except:
            pass
    
    def _aplicar_cooling_agresivo(self):
        """Aplica enfriamiento agresivo bajo estrés termico."""
        try:
            if self.tipo_gpu == "NVIDIA":
                subprocess.run(
                    ["nvidia-settings", "-a", "[gpu:0]/GPUFanControlState=1", 
                     "-a", "[fan:0]/GPUTargetFanSpeed=100"],
                    capture_output=True,
                    timeout=5
                )
            elif self.tipo_gpu == "AMD":
                subprocess.run(
                    ["rocm-smi", "--setfan", "100"],
                    capture_output=True,
                    timeout=5
                )
        except:
            pass
    
    def obtener_estadisticas(self) -> Dict:
        """Retorna estadísticas de GPU."""
        metricas = None
        if self.tipo_gpu == "NVIDIA":
            metricas = self.obtener_metricas_nvidia_detalladas()
        elif self.tipo_gpu == "AMD":
            # Suponiendo que existe un método similar para AMD
            # metricas = self.obtener_metricas_amd_detalladas()
            pass
        
        return {
            'tipo_gpu': self.tipo_gpu,
            'metricas': metricas or {},
            'umbrales': self.umbrales,
            'perfiles_oc': self.perfiles_oc,
            'estadisticas': {
                'optimizaciones_aplicadas': self.optimizaciones_aplicadas,
                'throttlings_detectados': self.throttlings_detectados,
                'boost_dinamico': self.boost_dinamico,
                'undervolting': self.undervolting_habilitado
            }
        }
    
    def _check_dependencies(self) -> bool:
        """Verifica si las librerías necesarias para la GPU están disponibles."""
        try:
            import pynvml
            return True
        except ImportError:
            import shutil
            return shutil.which("nvidia-smi") is not None or shutil.which("rocm-smi") is not None

    def limpiar_cache_shaders(self):
        """Limpia la caché de shaders de la GPU."""
        self.registrar_evento("LIMPIEZA_CACHE_SHADERS", "Iniciando limpieza de caché de shaders...", "INFO")
        # Rutas comunes de caché de shaders
        rutas_cache = {
            "NVIDIA": [
                os.path.expandvars(r"%LOCALAPPDATA%\NVIDIA\GLCache"),
                os.path.expandvars(r"%PROGRAMDATA%\NVIDIA Corporation\NV_Cache"),
            ],
            "AMD": [
                os.path.expandvars(r"%LOCALAPPDATA%\AMD\DxCache"),
            ],
            "Intel": [
                os.path.expandvars(r"%LOCALAPPDATA%\Intel\ShaderCache"),
            ]
        }
        
        rutas_a_limpiar = rutas_cache.get(self.tipo_gpu, [])
        for ruta in rutas_a_limpiar:
            try:
                if os.path.exists(ruta):
                    shutil.rmtree(ruta)
                    self.registrar_evento("CACHE_SHADERS_LIMPIADO", f"Caché de shaders limpiado en: {ruta}", "INFO")
            except Exception as e:
                self.logger.warning(f"Error limpiando caché de shaders en {ruta}: {e}")

    def setup_tasks(self):
        """Configura y añade las tareas de optimización de GPU al scheduler."""
        if not self.activo:
            return
        
        from base_gestor_Version2 import Task # Importación local
        self.scheduler.add_task(Task("optimizar_gpu_dinamico", self.optimizar_gpu_dinamico, timedelta(seconds=10)))
        self.scheduler.add_task(Task("optimizar_memoria_gpu", self.optimizar_memoria_gpu, timedelta(seconds=60)))
        self.scheduler.add_task(Task("limpiar_cache_shaders", self.limpiar_cache_shaders, timedelta(days=7)))
