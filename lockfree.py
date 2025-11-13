# lockfree.py
"""
Estructuras de datos thread-safe para alta concurrencia.
"""
import threading
from typing import Optional, Any, List
from collections import deque


class ThreadSafeQueue:
    """
    Cola thread-safe simple basada en collections.deque.
    Las operaciones `append` y `popleft` de deque son atómicas,
    lo que hace esta implementación segura para concurrencia básica
    sin necesidad de bloqueos explícitos para estas operaciones.
    """
    
    def __init__(self, maxsize: int = 0) -> None:
        self._queue = deque(maxlen=maxsize if maxsize > 0 else None)
    
    def put(self, item: Any) -> None:
        """Añade un item a la cola."""
        self._queue.append(item)
    
    def get(self) -> Optional[Any]:
        """Obtiene un item de la cola."""
        try:
            return self._queue.popleft()
        except IndexError:
            return None
    
    def __len__(self) -> int:
        return len(self._queue)
    
    def empty(self) -> bool:
        return len(self._queue) == 0


class AtomicCounter:
    """Contador atómico thread-safe."""
    
    def __init__(self, initial: int = 0) -> None:
        self._value = initial
        self._lock = threading.Lock()
    
    def increment(self, delta: int = 1) -> int:
        """Incrementa y retorna el nuevo valor."""
        with self._lock:
            self._value += delta
            return self._value
    
    def decrement(self, delta: int = 1) -> int:
        """Decrementa y retorna el nuevo valor."""
        return self.increment(-delta)
    
    def get(self) -> int:
        """Obtiene el valor actual."""
        with self._lock:
            return self._value
    
    def set(self, value: int) -> None:
        """Establece un nuevo valor."""
        with self._lock:
            self._value = value
    
    def compare_and_swap(self, expected: int, new: int) -> bool:
        """CAS: establece nuevo valor solo si el actual es el esperado."""
        with self._lock:
            if self._value == expected:
                self._value = new
                return True
            return False


class RWLock:
    """Read-Write Lock para optimizar lecturas concurrentes."""
    
    def __init__(self) -> None:
        self._readers = 0
        self._writers = 0
        self._read_ready = threading.Condition(threading.RLock())
        self._write_ready = threading.Condition(threading.RLock())
    
    def acquire_read(self) -> None:
        """Adquiere lock de lectura."""
        with self._read_ready:
            while self._writers > 0:
                self._read_ready.wait()
            self._readers += 1
    
    def release_read(self) -> None:
        """Libera lock de lectura."""
        with self._read_ready:
            self._readers -= 1
            if self._readers == 0:
                self._write_ready.notify_all()
    
    def acquire_write(self) -> None:
        """Adquiere lock de escritura."""
        with self._write_ready:
            while self._writers > 0 or self._readers > 0:
                self._write_ready.wait()
            self._writers += 1
    
    def release_write(self) -> None:
        """Libera lock de escritura."""
        with self._write_ready:
            self._writers -= 1
            self._read_ready.notify_all()
            self._write_ready.notify_all()
