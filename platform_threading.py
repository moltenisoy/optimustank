# platform_threading.py
"""
Adaptadores de plataforma y gestión de threads dinámicos para OPTIMUSTANK.
Consolida: platform_adapter.py, dynamic_thread_pool.py
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional, Any, List, Callable
import logging
import os
import glob
import subprocess
import threading
import time
import queue
import psutil
from concurrent.futures import ThreadPoolExecutor, Future
from collections import deque

# Configuración del logging
logger = logging.getLogger(__name__)


# ============================================================================
# DYNAMIC THREAD POOL (de dynamic_thread_pool.py)
# ============================================================================

class DynamicThreadPool:
    """Pool de threads con escalado automático inteligente basado en carga y recursos."""
    
    def __init__(
        self,
        min_workers: int = 2,
        max_workers: int = 32,
        idle_timeout: int = 60,
        queue_size_scale_trigger: int = 50,
        check_interval: float = 2.0
    ) -> None:
        self._min_workers = min_workers
        self._max_workers = max_workers
        self._idle_timeout = idle_timeout
        self._queue_size_scale_trigger = queue_size_scale_trigger
        self._check_interval = check_interval
        
        self._executor = ThreadPoolExecutor(max_workers=self._max_workers, thread_name_prefix='DynamicPool')
        self._task_queue = self._executor._work_queue
        
        self._lock = threading.Lock()
        self._task_timestamps: deque = deque(maxlen=100)
        
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor, daemon=True)
        self._monitor_thread.start()
    
    def submit(self, fn: Callable, *args, **kwargs) -> Future:
        """Envía una tarea al pool."""
        start_time = time.monotonic()
        
        def task_wrapper():
            result = fn(*args, **kwargs)
            end_time = time.monotonic()
            with self._lock:
                self._task_timestamps.append(end_time - start_time)
            return result
            
        return self._executor.submit(task_wrapper)
    
    def _get_system_load(self) -> Dict[str, float]:
        """Obtiene la carga actual del sistema."""
        return {
            'cpu': psutil.cpu_percent(),
            'memory': psutil.virtual_memory().percent
        }
        
    def _monitor(self) -> None:
        """Monitorea y ajusta el tamaño del pool de forma inteligente."""
        while self._running:
            time.sleep(self._check_interval)
            
            with self._lock:
                queue_len = self._task_queue.qsize()
                avg_task_time = sum(self._task_timestamps) / len(self._task_timestamps) if self._task_timestamps else 0
                system_load = self._get_system_load()
                
                scale_up_signal = (
                    queue_len > self._queue_size_scale_trigger or
                    (avg_task_time > 1.0 and queue_len > self._executor._max_workers * 0.5)
                ) and system_load['cpu'] < 90
                
                scale_down_signal = (
                    queue_len == 0 and
                    system_load['cpu'] < 30
                )
            
            current_workers = self._executor._max_workers
            if scale_up_signal:
                new_size = min(current_workers + 4, self._max_workers)
                if new_size > current_workers:
                    self._resize_pool(new_size)
            
            elif scale_down_signal:
                new_size = max(current_workers - 2, self._min_workers)
                if new_size < current_workers:
                    self._resize_pool(new_size)
    
    def _resize_pool(self, new_size: int) -> None:
        """Redimensiona el pool."""
        old_executor = self._executor
        self._executor = ThreadPoolExecutor(max_workers=new_size)
        self._current_workers = new_size
        
        threading.Thread(
            target=lambda: old_executor.shutdown(wait=True),
            daemon=True
        ).start()
    
    def shutdown(self, wait: bool = True) -> None:
        """Cierra el pool."""
        self._running = False
        self._executor.shutdown(wait=wait)
        self._monitor_thread.join(timeout=5)
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del pool."""
        with self._lock:
            return {
                'current_workers': getattr(self, '_current_workers', self._max_workers),
                'queue_size': self._task_queue.qsize()
            }


# ============================================================================
# PLATFORM ADAPTERS (de platform_adapter.py)
# ============================================================================

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


class PlatformAdapter(PowerManagementAdapter, GpuAdapter, GameAdapter, DiskAdapter):
    pass


class WindowsAdapter(PlatformAdapter):
    def is_fullscreen_game_running(self, game_list: List[str]) -> bool:
        """Detecta si un juego se está ejecutando en pantalla completa en Windows."""
        try:
            import ctypes
            
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            screen_width = user32.GetSystemMetrics(0)
            screen_height = user32.GetSystemMetrics(1)
            is_fullscreen = rect.left == 0 and rect.top == 0 and rect.right == screen_width and rect.bottom == screen_height
            
            if not is_fullscreen:
                return False
            
            pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            process = psutil.Process(pid.value)
            
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
                'rendimiento_maximo': 'e9a42b02-d5df-448d-aa00-03f14749eb61'
            }
            
            guid = guids.get(profile, guids['balanced'])
            subprocess.run(['powercfg', '/setactive', guid], check=True, capture_output=True, timeout=5)
            
            subprocess.run(
                ['powercfg', '/setacvalueindex', guid, 'SUB_PROCESSOR', 
                 'PROCTHROTTLEMAX', str(config.get('cpu_max', 100))],
                check=True, capture_output=True, timeout=5
            )
            
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error(f"Error applying power profile on Windows: {e}")

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
                        'nombre': values[2],
                        'temperatura_c': float(values[9]) if values[9] else 0,
                        'uso_gpu_pct': float(values[7]) if values[7] else 0,
                    }
                    gpus[f'gpu_{idx}'] = gpu_info
            
            return gpus if gpus else None
        
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.info(f"NVIDIA GPU not found or nvidia-smi not available: {e}")
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

    def run_trim(self, device: str) -> None:
        """Ejecuta TRIM en un dispositivo en Windows."""
        try:
            subprocess.run(
                ['defrag', f'{device}:', '/L'],
                check=True, capture_output=True, timeout=30
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error(f"Error running TRIM on Windows: {e}")


class LinuxAdapter(PlatformAdapter):
    def is_fullscreen_game_running(self, game_list: List[str]) -> bool:
        """Detecta si un juego se está ejecutando en pantalla completa en Linux."""
        try:
            output = subprocess.check_output(
                ["xprop", "-id", subprocess.check_output(["xdotool", "getactivewindow"]), "_NET_WM_STATE"],
                universal_newlines=True,
                timeout=1
            )
            is_fullscreen = "_NET_WM_STATE_FULLSCREEN" in output
            
            if not is_fullscreen:
                return False
                
            pid = subprocess.check_output(["xdotool", "getwindowpid", subprocess.check_output(["xdotool", "getactivewindow"])]).strip()
            process = psutil.Process(int(pid))
            return process.name() in game_list

        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.error(f"Error checking for fullscreen game on Linux: {e}")
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

    def get_gpu_metrics(self) -> Optional[Dict[str, Any]]:
        """Obtiene métricas de GPU en Linux (sysfs para AMD/Intel)."""
        gpus = {}
        try:
            for card in glob.glob('/sys/class/drm/card[0-9]*/device'):
                try:
                    with open(os.path.join(card, 'vendor'), 'r') as f:
                        vendor = f.read().strip()
                    
                    if vendor not in ('0x1002', '0x8086'):
                        continue

                    idx = os.path.basename(os.path.dirname(card)).replace('card', '')
                    
                    hwmon_path = glob.glob(os.path.join(card, 'hwmon/hwmon[0-9]*'))
                    if not hwmon_path:
                        continue
                    
                    temp_path = os.path.join(hwmon_path[0], 'temp1_input')
                    
                    temp = None
                    if os.path.exists(temp_path):
                        with open(temp_path, 'r') as f:
                            temp = float(f.read().strip()) / 1000.0
                    
                    gpus[f'gpu_{idx}'] = {
                        'nombre': 'AMD/Intel GPU',
                        'temperatura_c': temp
                    }
                except Exception as e:
                    logger.error(f"Error reading sysfs for {card}: {e}")
        except Exception as e:
            logger.error(f"Error accessing sysfs for GPU metrics: {e}")
        
        return gpus if gpus else None

    def apply_overclock(self, gpu_id: str, offset_mhz: int) -> None:
        """Aplica overclock seguro a GPU NVIDIA en Linux."""
        try:
            subprocess.run(
                ["nvidia-settings", "-a", f"[gpu:{gpu_id}]/GPUGraphicsClockOffset[3]={offset_mhz}"],
                check=True, capture_output=True, timeout=5
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error(f"Error applying overclock on Linux: {e}")

    def is_ssd(self, device: str) -> bool:
        """Detecta si un dispositivo es SSD en Linux."""
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


class PlatformAdapterFactory:
    @staticmethod
    def create_adapter() -> PlatformAdapter:
        import platform
        system = platform.system()
        if system == "Windows":
            return WindowsAdapter()
        elif system == "Linux":
            return LinuxAdapter()
        else:
            logger.error(f"Unsupported platform: {system}")
            raise NotImplementedError("Unsupported platform")
