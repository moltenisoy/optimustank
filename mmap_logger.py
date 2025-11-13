# mmap_logger.py
"""
Logger con memory-mapped files para alta performance, integrado con el framework de logging.
"""
import mmap
import os
from pathlib import Path
from typing import Optional
import threading
from datetime import datetime
import logging

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
        # Esta es una aproximación. Para un sistema robusto, se necesitaría un
        # mecanismo más sofisticado para tracking de la posición.
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
            
            # El flush puede ser costoso. Se podría hacer menos frecuente.
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
