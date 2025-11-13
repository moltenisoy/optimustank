# logging_profiling.py
"""
Utilidades de logging y profiling de alto rendimiento para OPTIMUSTANK.
Consolida: batch_writer.py, mmap_logger.py, profiling.py
"""
from typing import List, Callable, Any, Optional, Dict
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import mmap
import os
from pathlib import Path
from datetime import datetime
import logging
import cProfile
import pstats
import io
from functools import wraps


# ============================================================================
# BATCH WRITER (de batch_writer.py)
# ============================================================================

class BatchWriter:
    """
    Escritor por lotes optimizado que usa un ThreadPoolExecutor para operaciones de flush
    y un semáforo para aplicar backpressure, evitando la sobrecarga.
    """
    
    def __init__(
        self,
        batch_size: int = 100,
        flush_interval: float = 5.0,
        on_flush: Optional[Callable[[List[Any]], None]] = None,
        max_concurrent_flushes: int = 5
    ) -> None:
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._on_flush = on_flush
        
        self._buffer: List[Any] = []
        self._lock = threading.Lock()
        
        self._running = True
        self._last_flush_time = time.monotonic()
        
        # Usar ThreadPoolExecutor para manejar los flushes
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent_flushes, thread_name_prefix='BatchWriter')
        # Semáforo para backpressure
        self._flush_semaphore = threading.Semaphore(max_concurrent_flushes)
        
        # Thread para el flush automático
        self._timer = threading.Timer(self._flush_interval, self._auto_flush)
        self._timer.daemon = True
        self._timer.start()
    
    def write(self, item: Any) -> None:
        """Añade un item al buffer y realiza flush si es necesario."""
        with self._lock:
            if not self._running:
                raise RuntimeError("Cannot write to a closed BatchWriter.")
            self._buffer.append(item)
            if len(self._buffer) >= self._batch_size:
                self._schedule_flush()
    
    def _schedule_flush(self) -> None:
        """Organiza un flush si hay datos en el buffer."""
        if not self._buffer or not self._on_flush:
            return
        
        batch = self._buffer[:]
        self._buffer.clear()
        self._last_flush_time = time.monotonic()
        
        if self._flush_semaphore.acquire(blocking=False):
            self._executor.submit(self._execute_flush, batch)
        else:
            # Backpressure: si no hay workers disponibles, el flush se retrasa
            pass

    def _execute_flush(self, batch: List[Any]) -> None:
        """Ejecuta el callback on_flush y libera el semáforo."""
        try:
            if self._on_flush:
                self._on_flush(batch)
        finally:
            self._flush_semaphore.release()

    def _auto_flush(self) -> None:
        """Función periódica que agenda un flush si ha pasado el intervalo."""
        with self._lock:
            if not self._running:
                return
            
            elapsed = time.monotonic() - self._last_flush_time
            if elapsed >= self._flush_interval and self._buffer:
                self._schedule_flush()
        
        # Re-programar el timer
        if self._running:
            self._timer = threading.Timer(self._flush_interval, self._auto_flush)
            self._timer.daemon = True
            self._timer.start()

    def flush(self) -> None:
        """Realiza un flush manual de los datos pendientes."""
        with self._lock:
            self._schedule_flush()
    
    def close(self) -> None:
        """Cierra el writer, asegurando que todos los datos pendientes se escriban."""
        with self._lock:
            self._running = False
        
        self._timer.cancel()
        self.flush()
        self._executor.shutdown(wait=True)


# ============================================================================
# MMAP LOGGER (de mmap_logger.py)
# ============================================================================

class MMapLogHandler(logging.Handler):
    """Handler de logging que escribe en un memory-mapped file para máxima performance."""
    
    def __init__(
        self,
        filename: str,
        max_size: int = 100 * 1024 * 1024,  # 100MB
        buffer_size: int = 8192
    ) -> None:
        super().__init__()
        self.filename = Path(filename)
        self.max_size = max_size
        self.buffer_size = buffer_size
        
        self.filename.parent.mkdir(parents=True, exist_ok=True)
        
        self._open_mmap()
        self._position = self._find_initial_position()

    def _open_mmap(self):
        """Abre o crea el memory-mapped file."""
        if not self.filename.exists() or os.path.getsize(self.filename) < self.max_size:
            with open(self.filename, 'wb') as f:
                f.write(b'\x00' * self.max_size)
        
        self._fd = os.open(self.filename, os.O_RDWR)
        self._mmap = mmap.mmap(self._fd, self.max_size)

    def _find_initial_position(self) -> int:
        """Encuentra la primera posición no nula para continuar escribiendo."""
        pos = self._mmap.find(b'\x00')
        return pos if pos != -1 else self.max_size
    
    def emit(self, record: logging.LogRecord) -> None:
        """Emite un record de log."""
        try:
            msg = self.format(record)
            data = msg.encode('utf-8') + b'\\n'
            self.write(data)
        except Exception:
            self.handleError(record)

    def write(self, data: bytes) -> None:
        """Escribe datos al mmap de forma thread-safe."""
        with self.lock:
            if self._position + len(data) > self.max_size:
                self._rotate()
            
            self._mmap[self._position:self._position + len(data)] = data
            self._position += len(data)
            
            if self._position % self.buffer_size < len(data):
                self._mmap.flush()
    
    def _rotate(self) -> None:
        """Rota el archivo de log."""
        self.close()
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = self.filename.with_suffix(f'.{timestamp}.log')
        self.filename.rename(backup)
        
        self._open_mmap()
        self._position = 0
    
    def close(self) -> None:
        """Cierra el handler y los recursos asociados."""
        if self._mmap and not self._mmap.closed:
            self._mmap.flush()
            self._mmap.close()
        if self._fd is not None:
            os.close(self._fd)
        super().close()


# ============================================================================
# PERFORMANCE PROFILER (de profiling.py)
# ============================================================================

class PerformanceProfiler:
    """Profiler de bajo overhead con sampling."""
    
    def __init__(self, sample_rate: float = 0.01) -> None:
        self.sample_rate = sample_rate
        self._profiles: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
    
    def profile(self, func: Callable) -> Callable:
        """Decorador para profiling selectivo."""
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Sampling: solo profilea sample_rate % de las llamadas
            if threading.current_thread().ident % 100 < self.sample_rate * 100:
                return self._profile_call(func, args, kwargs)
            else:
                return func(*args, **kwargs)
        
        return wrapper
    
    def _profile_call(self, func: Callable, args: tuple, kwargs: dict) -> Any:
        """Perfila una llamada individual."""
        profiler = cProfile.Profile()
        profiler.enable()
        
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            duration = time.perf_counter() - start
            profiler.disable()
            
            # Almacenar estadísticas
            func_name = f"{func.__module__}.{func.__qualname__}"
            
            with self._lock:
                if func_name not in self._profiles:
                    self._profiles[func_name] = {
                        'count': 0,
                        'total_time': 0.0,
                        'profiles': []
                    }
                
                stats = self._profiles[func_name]
                stats['count'] += 1
                stats['total_time'] += duration
                
                # Guardar solo las últimas N profiles
                if len(stats['profiles']) < 10:
                    s = io.StringIO()
                    ps = pstats.Stats(profiler, stream=s)
                    ps.sort_stats('cumulative')
                    stats['profiles'].append({
                        'duration': duration,
                        'stats': ps
                    })
    
    def get_stats(self, func_name: Optional[str] = None) -> Dict[str, Any]:
        """Obtiene estadísticas de profiling."""
        with self._lock:
            if func_name:
                return self._profiles.get(func_name, {})
            return self._profiles.copy()
    
    def reset(self) -> None:
        """Resetea todas las estadísticas."""
        with self._lock:
            self._profiles.clear()


# Singleton global
_profiler = PerformanceProfiler(sample_rate=0.01)


def profile(func: Callable) -> Callable:
    """Decorador de profiling global."""
    return _profiler.profile(func)
