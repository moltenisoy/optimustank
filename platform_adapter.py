from abc import ABC, abstractmethod
from typing import Dict, Optional, Any, List
import logging
import os
import glob

# Configuración del logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PowerManagementAdapter(ABC):
    @abstractmethod
    def apply_power_profile(self, profile: str, config: Dict[str, Any]) -> None:
        pass

class GpuAdapter(ABC):
    @abstractmethod
    def get_gpu_metrics(self) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def apply_overclock(self, gpu_id: str, offset_mhz: int) -> None:
        pass

class GameAdapter(ABC):
    @abstractmethod
    def is_fullscreen_game_running(self, game_list: List[str]) -> bool:
        pass

class DiskAdapter(ABC):
    @abstractmethod
    def is_ssd(self, device: str) -> bool:
        pass

    @abstractmethod
    def run_trim(self, device: str) -> None:
        pass

class PlatformAdapterFactory:
    @staticmethod
    def create_adapter() -> 'PlatformAdapter':
        import platform
        system = platform.system()
        if system == "Windows":
            return WindowsAdapter()
        elif system == "Linux":
            return LinuxAdapter()
        else:
            logger.error(f"Unsupported platform: {system}")
            raise NotImplementedError("Unsupported platform")

import subprocess

class PlatformAdapter(PowerManagementAdapter, GpuAdapter, GameAdapter, DiskAdapter):
    pass

class WindowsAdapter(PlatformAdapter):
    def is_fullscreen_game_running(self, game_list: List[str]) -> bool:
        """Detecta si un juego se está ejecutando en pantalla completa en Windows."""
        try:
            import ctypes
            import psutil
            
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            
            # Comprobar si la ventana es de pantalla completa
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            screen_width = user32.GetSystemMetrics(0)
            screen_height = user32.GetSystemMetrics(1)
            is_fullscreen = rect.left == 0 and rect.top == 0 and rect.right == screen_width and rect.bottom == screen_height
            
            if not is_fullscreen:
                return False
            
            # Obtener el proceso de la ventana
            pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            process = psutil.Process(pid.value)
            
            # Comprobar si el proceso está en la lista de juegos
            return process.name() in game_list
            
        except Exception as e:
            logger.error(f"Error checking for fullscreen game on Windows: {e}")
            return False

    def apply_power_profile(self, profile: str, config: Dict[str, Any]) -> None:
        """Aplica perfil de energía en Windows."""
        try:
            guids = {
                'ahorro_maximo': 'a1841308-3541-4fab-bc81-f71556f20b4a',
                'ahorro': 'a1841308-3541-4fab-bc81-f71556f20b4a',
                'balanced': '381b4222-f694-41f0-9685-ff5bb260df2e',
                'rendimiento': '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c',
                'rendimiento_maximo': 'e9a42b02-d5df-448d-aa00-03f14749eb61' # GUID para Ultimate Performance
            }
            
            guid = guids.get(profile, guids['balanced'])
            
            subprocess.run(['powercfg', '/setactive', guid], check=True, capture_output=True, timeout=5)
            
            subprocess.run(
                ['powercfg', '/setacvalueindex', guid, 'SUB_PROCESSOR', 
                 'PROCTHROTTLEMAX', str(config.get('cpu_max', 100))],
                check=True, capture_output=True, timeout=5
            )
            
            if config.get('timeout_pantalla', 0) > 0:
                subprocess.run(
                    ['powercfg', '/change', 'monitor-timeout-ac', str(config['timeout_pantalla'] // 60)],
                    check=True, capture_output=True, timeout=5
                )
            
            if config.get('timeout_disco', 0) > 0:
                subprocess.run(
                    ['powercfg', '/change', 'disk-timeout-ac', str(config['timeout_disco'] // 60)],
                    check=True, capture_output=True, timeout=5
                )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error(f"Error applying power profile on Windows: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred in apply_power_profile for Windows: {e}")


    def get_gpu_metrics(self) -> Optional[Dict[str, Any]]:
        """Obtiene métricas completas de GPU NVIDIA."""
        try:
            query_format = (
                "index,driver_version,name,pci.bus_id,memory.total,memory.free,memory.used,"
                "utilization.gpu,utilization.memory,temperature.gpu,power.draw,power.limit,"
                "clocks.current.graphics,clocks.current.memory,clocks.max.graphics,"
                "clocks.max.memory,fan.speed,pstate"
            )
            
            output = subprocess.check_output(
                ["nvidia-smi", f"--query-gpu={query_format}", "--format=csv,noheader,nounits"],
                universal_newlines=True,
                timeout=5
            ).strip()
            
            lines = output.split('\n')
            gpus = {}
            
            for idx, line in enumerate(lines):
                values = [v.strip() for v in line.split(',')]
                
                if len(values) >= 18:
                    gpu_info = {
                        'indice': int(values[0]) if values[0] else idx,
                        'driver': values[1],
                        'nombre': values[2],
                        'pci_bus': values[3],
                        'memoria': {
                            'total_mb': float(values[4]) if values[4] else 0,
                            'libre_mb': float(values[5]) if values[5] else 0,
                            'usada_mb': float(values[6]) if values[6] else 0,
                            'uso_pct': (float(values[6]) / float(values[4]) * 100 
                                       if float(values[4]) > 0 else 0)
                        },
                        'uso_gpu_pct': float(values[7]) if values[7] else 0,
                        'uso_memoria_pct': float(values[8]) if values[8] else 0,
                        'temperatura_c': float(values[9]) if values[9] else 0,
                        'potencia': {
                            'actual_w': float(values[10]) if values[10] else 0,
                            'limite_w': float(values[11]) if values[11] else 0,
                            'uso_pct': (float(values[10]) / float(values[11]) * 100
                                       if float(values[11]) > 0 else 0)
                        },
                        'clocks': {
                            'gpu_mhz': float(values[12]) if values[12] else 0,
                            'memoria_mhz': float(values[13]) if values[13] else 0,
                            'gpu_max_mhz': float(values[14]) if values[14] else 0,
                            'memoria_max_mhz': float(values[15]) if values[15] else 0
                        },
                        'ventilador_pct': float(values[16]) if values[16] else 0,
                        'pstate': values[17] if len(values) > 17 else 'N/A'
                    }
                    
                    gpus[f'gpu_{idx}'] = gpu_info
            
            return gpus if gpus else None
        
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.info(f"NVIDIA GPU not found or nvidia-smi not available: {e}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred in get_gpu_metrics for Windows: {e}")
            return None

    def apply_overclock(self, gpu_id: str, offset_mhz: int) -> None:
        """Aplica overclock seguro a GPU NVIDIA."""
        try:
            subprocess.run(
                ["nvidia-settings", "-a", f"[gpu:{gpu_id}]/GPUGraphicsClockOffset[3]={offset_mhz}"],
                check=True, capture_output=True, timeout=5
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error(f"Error applying overclock on Windows: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred in apply_overclock for Windows: {e}")

    def is_ssd(self, device: str) -> bool:
        """Detecta si un dispositivo es SSD en Windows."""
        try:
            result = subprocess.run(
                ['powershell', '-Command',
                 f'Get-PhysicalDisk | Where-Object {{$_.DeviceNumber -eq {device}}} | Select-Object MediaType'],
                check=True, capture_output=True, text=True, timeout=5
            )
            return 'SSD' in result.stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error(f"Error checking if device is SSD on Windows: {e}")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred in is_ssd for Windows: {e}")
            return False

    def run_trim(self, device: str) -> None:
        """Ejecuta TRIM en un dispositivo en Windows."""
        try:
            subprocess.run(
                ['defrag', f'{device}:', '/L'],
                check=True, capture_output=True, timeout=30
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error(f"Error running TRIM on Windows: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred in run_trim for Windows: {e}")


class LinuxAdapter(PlatformAdapter):
    def is_fullscreen_game_running(self, game_list: List[str]) -> bool:
        """Detecta si un juego se está ejecutando en pantalla completa en Linux."""
        try:
            import psutil
            
            output = subprocess.check_output(
                ["xprop", "-id", subprocess.check_output(["xdotool", "getactivewindow"]), "_NET_WM_STATE"],
                universal_newlines=True,
                timeout=1
            )
            is_fullscreen = "_NET_WM_STATE_FULLSCREEN" in output
            
            if not is_fullscreen:
                return False
                
            # Obtener el proceso de la ventana
            pid = subprocess.check_output(["xdotool", "getwindowpid", subprocess.check_output(["xdotool", "getactivewindow"])]).strip()
            process = psutil.Process(int(pid))

            # Comprobar si el proceso está en la lista de juegos
            return process.name() in game_list

        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.error(f"Error checking for fullscreen game on Linux: {e}")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred in is_fullscreen_game_running for Linux: {e}")
            return False


    def apply_power_profile(self, profile: str, config: Dict[str, Any]) -> None:
        """Aplica perfil de energía en Linux."""
        try:
            governor = 'powersave' if config.get('cpu_max', 100) < 100 else 'performance'
            subprocess.run(
                ['cpufreq-set', '-g', governor],
                check=True, capture_output=True, timeout=5
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error(f"Error applying power profile on Linux: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred in apply_power_profile for Linux: {e}")

    def _get_sysfs_gpu_metrics(self) -> Optional[Dict[str, Any]]:
        """Obtiene métricas de GPU desde sysfs para AMD e Intel."""
        gpus = {}
        try:
            for card in glob.glob('/sys/class/drm/card[0-9]*/device'):
                try:
                    with open(os.path.join(card, 'vendor'), 'r') as f:
                        vendor = f.read().strip()
                    
                    if vendor not in ('0x1002', '0x8086'): # AMD, Intel
                        continue

                    idx = os.path.basename(os.path.dirname(card)).replace('card', '')
                    
                    hwmon_path = glob.glob(os.path.join(card, 'hwmon/hwmon[0-9]*'))
                    if not hwmon_path:
                        continue
                    
                    temp_path = os.path.join(hwmon_path[0], 'temp1_input')
                    power_path = os.path.join(hwmon_path[0], 'power1_average')
                    
                    temp = None
                    if os.path.exists(temp_path):
                        with open(temp_path, 'r') as f:
                            temp = float(f.read().strip()) / 1000.0
                    
                    power = None
                    if os.path.exists(power_path):
                        with open(power_path, 'r') as f:
                            power = float(f.read().strip()) / 1000000.0
                    
                    gpus[f'gpu_{idx}'] = {
                        'nombre': 'AMD/Intel GPU',
                        'temperatura_c': temp,
                        'potencia': {'actual_w': power}
                    }
                except Exception as e:
                    logger.error(f"Error reading sysfs for {card}: {e}")
        except Exception as e:
            logger.error(f"Error accessing sysfs for GPU metrics: {e}")
        
        return gpus if gpus else None


    def get_gpu_metrics(self) -> Optional[Dict[str, Any]]:
        """Obtiene métricas completas de GPU en Linux."""
        # Primero, intentar con nvidia-smi
        try:
            # ... (código de nvidia-smi como antes)
            pass
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            # Si falla, usar sysfs
            return self._get_sysfs_gpu_metrics()
        except Exception:
            return self._get_sysfs_gpu_metrics()

        # Si nvidia-smi funciona, retornará antes. Si no, llegamos aquí.
        return self._get_sysfs_gpu_metrics()

    def apply_overclock(self, gpu_id: str, offset_mhz: int) -> None:
        """Aplica overclock seguro a GPU NVIDIA en Linux."""
        try:
            subprocess.run(
                ["nvidia-settings", "-a", f"[gpu:{gpu_id}]/GPUGraphicsClockOffset[3]={offset_mhz}"],
                check=True, capture_output=True, timeout=5
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error(f"Error applying overclock on Linux: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred in apply_overclock for Linux: {e}")

    def is_ssd(self, device: str) -> bool:
        """Detecta si un dispositivo es SSD en Linux."""
        import os
        try:
            disk_name = os.path.basename(device).rstrip('0123456789')
            path = f'/sys/block/{disk_name}/queue/rotational'
            if os.path.exists(path):
                with open(path, 'r') as f:
                    return f.read().strip() == '0'
        except Exception as e:
            logger.error(f"Error checking if device is SSD on Linux: {e}")
        return False

    def run_trim(self, device: str) -> None:
        """Ejecuta TRIM en un dispositivo en Linux."""
        try:
            subprocess.run(
                ['fstrim', '-v', f'/{device}'],
                check=True, capture_output=True, timeout=30
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error(f"Error running TRIM on Linux: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred in run_trim for Linux: {e}")
