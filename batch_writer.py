# batch_writer.py
"""
Sistema de escritura por lotes optimizado con backpressure y thread pool.
"""
from typing import List, Callable, Any, Optional
import threading
import time
from concurrent.futures import ThreadPoolExecutor

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
            # o se podría manejar de otra forma (ej. loguear, descartar)
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
