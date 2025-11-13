# dynamic_thread_pool.py
"""
Pool de threads dinámico con auto-scaling y prioridades.
"""
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Any, Optional, Dict, List
import threading
import queue
import time
import psutil
from collections import deque

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
        self._task_timestamps: deque = deque(maxlen=100) # Para calcular tiempo medio de tarea
        
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
                
                # Decisión de escalado más compleja
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
        
        # Permitir que el viejo executor termine sus tareas
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
            pending = self._task_count - self._completed_count
            return {
                'current_workers': self._current_workers,
                'pending_tasks': pending,
                'completed_tasks': self._completed_count,
                'utilization': pending / self._current_workers if self._current_workers > 0 else 0
            }
