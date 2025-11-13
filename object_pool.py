# object_pool.py
"""
Pool de objetos reutilizables para reducir la presión sobre el Garbage Collector.
"""
from typing import Generic, TypeVar, Callable, Optional, Dict, Any
import threading
from queue import Queue, Empty
from evento_avanzado import EventoAvanzado

T = TypeVar('T')

class ObjectPool(Generic[T]):
    """Pool genérico de objetos reutilizables, thread-safe y con re-inicialización."""
    
    def __init__(
        self,
        factory: Callable[[], T],
        reset: Optional[Callable[[T], None]] = None,
        reinit: Optional[Callable[..., None]] = None,
        max_size: int = 100,
        prealloc: int = 10
    ) -> None:
        self._factory = factory
        self._reset = reset or (lambda x: None)
        self._reinit = reinit
        self._max_size = max_size
        self._pool: Queue[T] = Queue(maxsize=max_size)
        self._lock = threading.Lock()
        self._created = 0
        
        for _ in range(prealloc):
            self._pool.put(self._factory())
            self._created += 1
    
    def acquire(self, *args, **kwargs) -> T:
        """Adquiere un objeto del pool y lo re-inicializa."""
        try:
            obj = self._pool.get_nowait()
        except Empty:
            with self._lock:
                if self._created < self._max_size:
                    obj = self._factory()
                    self._created += 1
                else:
                    obj = self._pool.get()
        
        if self._reinit:
            self._reinit(obj, *args, **kwargs)
            
        return obj
    
    def release(self, obj: T) -> None:
        """Devuelve un objeto al pool, reseteando su estado."""
        self._reset(obj)
        try:
            self._pool.put_nowait(obj)
        except Queue.Full:
            # Pool lleno, el objeto será descartado y recolectado por el GC
            pass

# --- Implementación específica para EventoAvanzado ---

class EventoAvanzadoPool:
    """Pool de objetos EventoAvanzado para optimizar la creación de eventos."""
    
    _pool: Optional[ObjectPool['EventoAvanzado']] = None
    
    @classmethod
    def _initialize(cls) -> None:
        """Inicializa el pool de eventos de forma segura."""
        if cls._pool is None:
            def factory() -> EventoAvanzado:
                # Usar __new__ para evitar la inicialización automática de __init__
                return EventoAvanzado.__new__(EventoAvanzado)
            
            def reset(evento: EventoAvanzado) -> None:
                # Limpiar estado para reutilización
                evento.procesado = False
                if hasattr(evento, 'respuestas'):
                    evento.respuestas.clear()
                if hasattr(evento, 'contexto'):
                    evento.contexto.clear()
            
            # El método __init__ de EventoAvanzado servirá como `reinit`
            cls._pool = ObjectPool(
                factory=factory, 
                reset=reset,
                reinit=EventoAvanzado.__init__,
                max_size=500, 
                prealloc=50
            )
    
    @classmethod
    def create(cls, *args, **kwargs) -> EventoAvanzado:
        """Obtiene un evento del pool y lo inicializa con los parámetros dados."""
        if cls._pool is None:
            cls._initialize()
        return cls._pool.acquire(*args, **kwargs)
    
    @classmethod
    def recycle(cls, evento: EventoAvanzado) -> None:
        """Devuelve un evento al pool para su reutilización."""
        if cls._pool:
            cls._pool.release(evento)
