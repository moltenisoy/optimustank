# gestor_energia.py
"""
Gestor avanzado de energía con optimización adaptable según tipo de equipo
(portátil vs escritorio), perfiles dinámicos y gestión térmica inteligente.
"""
from base_gestor import BaseGestor
import psutil
import platform
import subprocess
from typing import Dict, Optional
from collections import deque
import os
import clr
import sys

# Add the directory of the DLL to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    clr.AddReference("LibreHardwareMonitorLib")
    from LibreHardwareMonitor.Hardware import Computer
except Exception as e:
    print(f"Error loading LibreHardwareMonitorLib.dll: {e}")
    Computer = None

class HardwareMonitor:
    def __init__(self):
        if not Computer:
            self.computer = None
            return
        self.computer = Computer()
        self.computer.IsCpuEnabled = True
        self.computer.Open()

    def get_cpu_temperature(self) -> Optional[float]:
        if not self.computer:
            return None
        
        for hardware in self.computer.Hardware:
            hardware.Update()
            if hardware.HardwareType == 1:  # CPU
                for sensor in hardware.Sensors:
                    if sensor.SensorType == 1 and "temperature" in sensor.Name.lower():
                        if sensor.Value is not None:
                            return float(sensor.Value)
        return None

    def close(self):
        if self.computer:
            self.computer.Close()

from datetime import timedelta

from platform_threading import PlatformAdapterFactory

class GestorEnergia(BaseGestor):
    def __init__(self):
        super().__init__("GestorEnergia")
        
        self.adapter = PlatformAdapterFactory.create_adapter()
        self.tipo_equipo = self._detectar_tipo_equipo()
        self.en_bateria = self._detectar_estado_bateria()
        self.perfil_actual = 'balanced'
        
        self.historial_bateria = deque(maxlen=200)
        self.historial_consumo = deque(maxlen=200)
        self.optimizaciones_aplicadas = 0
        self.hardware_monitor = HardwareMonitor()
        
        # Perfiles de energía
        self.perfiles = {
            'ahorro_maximo': {
                'cpu_max': 50,
                'brillo_pantalla': 30,
                'timeout_pantalla': 120,
                'timeout_disco': 300
            },
            'ahorro': {
                'cpu_max': 70,
                'brillo_pantalla': 50,
                'timeout_pantalla': 300,
                'timeout_disco': 600
            },
            'balanced': {
                'cpu_max': 85,
                'brillo_pantalla': 70,
                'timeout_pantalla': 600,
                'timeout_disco': 900
            },
            'rendimiento': {
                'cpu_max': 100,
                'brillo_pantalla': 100,
                'timeout_pantalla': 0,
                'timeout_disco': 0
            },
            'rendimiento_maximo': {
                'cpu_max': 100,
                'brillo_pantalla': 100,
                'timeout_pantalla': 0,
                'timeout_disco': 0,
                'turbo_boost': True
            }
        }
        
        self.logger.info(f"GestorEnergia: Tipo={self.tipo_equipo}, Batería={self.en_bateria}")
    
    def _detectar_tipo_equipo(self) -> str:
        """Detecta si el equipo es portátil o escritorio."""
        try:
            if platform.system() == "Windows":
                bateria = psutil.sensors_battery()
                return 'portatil' if bateria else 'escritorio'
            else:
                if os.path.exists('/sys/class/power_supply/BAT0'):
                    return 'portatil'
                return 'escritorio'
        except:
            return 'desconocido'
    
    def _detectar_estado_bateria(self) -> bool:
        """Detecta si el equipo está en batería."""
        try:
            bateria = psutil.sensors_battery()
            if bateria:
                return not bateria.power_plugged
            return False
        except:
            return False
    
    def obtener_estadisticas_energia(self) -> Dict:
        """Obtiene estadísticas de energía del sistema."""
        try:
            stats = {
                'tipo_equipo': self.tipo_equipo,
                'perfil_actual': self.perfil_actual,
                'en_bateria': self.en_bateria
            }
            
            bateria = psutil.sensors_battery()
            if bateria:
                stats['bateria'] = {
                    'porcentaje': bateria.percent,
                    'tiempo_restante_min': bateria.secsleft / 60 if bateria.secsleft != -1 else None,
                    'conectado': bateria.power_plugged
                }
                self.historial_bateria.append(bateria.percent)
            
            temps = psutil.sensors_temperatures()
            if temps:
                stats['temperaturas'] = {}
                for nombre, entradas in temps.items():
                    stats['temperaturas'][nombre] = [
                        {'label': e.label, 'actual': e.current, 'critica': e.critical}
                        for e in entradas
                    ]
            
            return stats
        
        except Exception as e:
            self.logger.error(f"Error obteniendo estadísticas energía: {e}")
            return {}
    
    def seleccionar_perfil_optimo(self) -> str:
        """Selecciona perfil óptimo según estado del sistema."""
        try:
            temp_cpu = self.hardware_monitor.get_cpu_temperature()
            if temp_cpu is not None:
                if temp_cpu > self.config.get('thermal_throttling.aggressive_threshold', 85):
                    return 'ahorro_maximo'
                elif temp_cpu > self.config.get('thermal_throttling.soft_threshold', 75):
                    return 'ahorro'

            bateria = psutil.sensors_battery()
            cpu_pct = psutil.cpu_percent(interval=0.5)

            if self.tipo_equipo == 'portatil' and self.en_bateria:
                if bateria and bateria.percent < 20:
                    return 'ahorro_maximo'
                elif bateria and bateria.percent < 50:
                    return 'ahorro'
                else:
                    return 'balanced'
            else:
                if cpu_pct > 80:
                    return 'rendimiento_maximo'
                elif cpu_pct > 60:
                    return 'rendimiento'
                else:
                    return 'balanced'

        except Exception as e:
            self.logger.debug(f"Error seleccionando perfil: {e}")
            return 'balanced'
    
    def aplicar_perfil_energia(self, perfil: str):
        """Aplica perfil de energía al sistema."""
        if perfil not in self.perfiles:
            return
        
        try:
            config = self.perfiles[perfil]
            self.adapter.apply_power_profile(perfil, config)
            
            self.perfil_actual = perfil
            self.optimizaciones_aplicadas += 1
            
            self.registrar_evento(
                "PERFIL_ENERGIA_APLICADO",
                f"Perfil: {perfil}",
                "INFO"
            )
        
        except Exception as e:
            self.registrar_evento("ERROR_PERFIL_ENERGIA", str(e), "WARNING")
    
    def optimizar_consumo_adaptativo(self):
        """Optimización adaptativa del consumo según contexto."""
        try:
            self.en_bateria = self._detectar_estado_bateria()
            perfil_optimo = self.seleccionar_perfil_optimo()
            
            if perfil_optimo != self.perfil_actual:
                self.aplicar_perfil_energia(perfil_optimo)
                self.registrar_evento(
                    "PERFIL_CAMBIADO_AUTO",
                    f"{self.perfil_actual} → {perfil_optimo}",
                    "INFO"
                )
        
        except Exception as e:
            self.logger.debug(f"Error optimización adaptativa: {e}")
    
    def gestionar_termica_cpu(self):
        """Gestión térmica inteligente de CPU."""
        try:
            temp_max = self.hardware_monitor.get_cpu_temperature()

            if temp_max is None:
                return

            if temp_max > self.config.get('thermal_throttling.aggressive_threshold', 85):
                self.registrar_evento(
                    "TEMPERATURA_CRITICA",
                    f"CPU: {temp_max:.1f}°C - Reduciendo rendimiento",
                    "ERROR",
                    prioridad=9
                )
                self.aplicar_perfil_energia('ahorro_maximo')

            elif temp_max > self.config.get('thermal_throttling.soft_threshold', 75):
                self.registrar_evento(
                    "TEMPERATURA_ALTA",
                    f"CPU: {temp_max:.1f}°C",
                    "WARNING",
                    prioridad=7
                )
                self.aplicar_perfil_energia('ahorro')

        except Exception as e:
            self.logger.debug(f"Error gestión térmica: {e}")

    def detener(self):
        """Detiene el gestor y cierra el monitor de hardware."""
        super().detener()
        self.hardware_monitor.close()
    
    def optimizar_usb_selectivo(self):
        """Optimiza suspensión selectiva de USB."""
        try:
            if platform.system() == "Windows":
                subprocess.run(
                    ['powercfg', '/setacvalueindex', 'SCHEME_CURRENT', 
                     'SUB_USB', 'USBSELECTIVESUSPEND', '1'],
                    capture_output=True, timeout=5
                )
        except Exception as e:
            self.logger.debug(f"Error optimizando USB: {e}")
    
    def obtener_estadisticas(self) -> Dict:
        """Retorna estadísticas completas."""
        return {
            'energia': self.obtener_estadisticas_energia(),
            'tipo_equipo': self.tipo_equipo,
            'perfil_actual': self.perfil_actual,
            'optimizaciones_aplicadas': self.optimizaciones_aplicadas,
            'perfiles_disponibles': list(self.perfiles.keys())
        }
    
    def setup_tasks(self):
        """Configura y añade las tareas de gestión de energía al scheduler."""
        scheduler.add_task(Task("obtener_estadisticas_energia", self.obtener_estadisticas_energia, timedelta(seconds=10)))
        scheduler.add_task(Task("optimizar_consumo_adaptativo", self.optimizar_consumo_adaptativo, timedelta(seconds=20)))
        scheduler.add_task(Task("gestionar_termica_cpu", self.gestionar_termica_cpu, timedelta(seconds=5)))
        scheduler.add_task(Task("optimizar_usb_selectivo", self.optimizar_usb_selectivo, timedelta(minutes=1)))