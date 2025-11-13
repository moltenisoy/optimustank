# memory_utils.py
"""
Utilidades de gestión de memoria y caché para OPTIMUSTANK.
Consolida: object_pool.py, smart_cache.py, weak_ref_managers.py
"""
from typing import Generic, TypeVar, Callable, Optional, Dict, Any
import threading
from queue import Queue, Empty
from functools import wraps
import time
from collections import OrderedDict
import hashlib
import pickle
import sys
import weakref


# ============================================================================
# OBJECT POOL (de object_pool.py)
# ============================================================================

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
        except:
            # Pool lleno, el objeto será descartado y recolectado por el GC
            pass


# Importación tardía para evitar dependencia circular
class EventoAvanzadoPool:
    """Pool de objetos EventoAvanzado para optimizar la creación de eventos."""
    
    _pool: Optional[ObjectPool] = None
    
    @classmethod
    def initialize(cls) -> None:
        """Inicializa el pool de eventos."""
        if cls._pool is None:
            from core_events import EventoAvanzado
            
            def factory():
                return EventoAvanzado.__new__(EventoAvanzado)
            
            def reset(evento):
                evento.procesado = False
                if hasattr(evento, 'respuestas'):
                    evento.respuestas.clear()
                if hasattr(evento, 'contexto'):
                    evento.contexto.clear()
            
            cls._pool = ObjectPool(
                factory=factory,
                reset=reset,
                reinit=EventoAvanzado.__init__,
                max_size=500,
                prealloc=50
            )
    
    @classmethod
    def create(cls, *args, **kwargs):
        """Obtiene un evento del pool y lo inicializa."""
        if cls._pool is None:
            cls.initialize()
        return cls._pool.acquire(*args, **kwargs)
    
    @classmethod
    def recycle(cls, evento) -> None:
        """Devuelve un evento al pool."""
        if cls._pool:
            cls._pool.release(evento)


# ============================================================================
# SMART CACHE (de smart_cache.py)
# ============================================================================

class CacheEntry(Generic[T]):
    """Entrada de caché con TTL y metadata."""
    
    __slots__ = ('value', 'timestamp', 'hits', 'size', 'ttl')
    
    def __init__(self, value: T, ttl: float) -> None:
        self.value = value
        self.timestamp = time.monotonic()
        self.hits = 0
        self.ttl = ttl
        self.size = self._calculate_size(value)
    
    def _calculate_size(self, obj: Any) -> int:
        """Estima el tamaño del objeto en bytes de forma más eficiente."""
        if isinstance(obj, (str, bytes, int, float, bool, type(None))):
            return sys.getsizeof(obj)
        if isinstance(obj, (list, tuple, set, dict)):
            return sys.getsizeof(obj) + sum(self._calculate_size(i) for i in obj)
        
        # Fallback a pickle para objetos complejos
        try:
            return len(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))
        except (pickle.PicklingError, TypeError):
            return sys.getsizeof(obj)
    
    def is_expired(self) -> bool:
        """Verifica si la entrada ha expirado."""
        if self.ttl <= 0:
            return False
        return (time.monotonic() - self.timestamp) > self.ttl


class LRUCache:
    """Caché LRU con TTL y warming thread-safe."""
    
    def __init__(
        self,
        max_size: int = 1000,
        max_memory_mb: int = 100,
        default_ttl: float = 60.0,
        enable_stats: bool = True
    ) -> None:
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._max_memory = max_memory_mb * 1024 * 1024
        self._default_ttl = default_ttl
        self._enable_stats = enable_stats
        
        self._lock = threading.RLock()
        self._current_memory = 0
        
        # Estadísticas
        self._hits = 0
        self._misses = 0
        self._evictions = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Obtiene un valor del caché."""
        with self._lock:
            entry = self._cache.get(key)
            
            if entry is None:
                if self._enable_stats:
                    self._misses += 1
                return None
            
            if entry.is_expired():
                self._remove(key)
                if self._enable_stats:
                    self._misses += 1
                return None
            
            # Mover al final (más reciente)
            self._cache.move_to_end(key)
            entry.hits += 1
            
            if self._enable_stats:
                self._hits += 1
            
            return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Almacena un valor en el caché."""
        ttl = ttl if ttl is not None else self._default_ttl
        entry = CacheEntry(value, ttl)
        
        with self._lock:
            # Si la clave existe, eliminar la antigua
            if key in self._cache:
                self._remove(key)
            
            # Verificar límites antes de insertar
            while (
                len(self._cache) >= self._max_size or
                self._current_memory + entry.size > self._max_memory
            ):
                if not self._cache:
                    break
                self._evict_lru()
            
            self._cache[key] = entry
            self._current_memory += entry.size
    
    def _remove(self, key: str) -> None:
        """Elimina una entrada del caché."""
        entry = self._cache.pop(key, None)
        if entry:
            self._current_memory -= entry.size
    
    def _evict_lru(self) -> None:
        """Evicta la entrada menos recientemente usada."""
        if not self._cache:
            return
        
        key, _ = self._cache.popitem(last=False)
        self._evictions += 1
    
    def invalidate(self, key: str) -> None:
        """Invalida una entrada específica."""
        with self._lock:
            self._remove(key)
    
    def clear(self) -> None:
        """Limpia todo el caché."""
        with self._lock:
            self._cache.clear()
            self._current_memory = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del caché."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            
            return {
                'size': len(self._cache),
                'max_size': self._max_size,
                'memory_used_mb': self._current_memory / (1024 * 1024),
                'max_memory_mb': self._max_memory / (1024 * 1024),
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': hit_rate,
                'evictions': self._evictions
            }


def cached(
    cache: Optional[LRUCache] = None,
    ttl: Optional[float] = None,
    key_func: Optional[Callable] = None
) -> Callable:
    """Decorador para cachear resultados de funciones."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generar clave del caché
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                key_data = f"{func.__name__}:{args}:{sorted(kwargs.items())}"
                cache_key = hashlib.md5(key_data.encode()).hexdigest()
            
            # Intentar obtener del caché
            _cache = cache or _global_cache
            result = _cache.get(cache_key)
            
            if result is not None:
                return result
            
            # Ejecutar función y cachear
            result = func(*args, **kwargs)
            _cache.set(cache_key, result, ttl)
            
            return result
        
        wrapper.cache = cache or _global_cache
        wrapper.invalidate = lambda: wrapper.cache.clear()
        
        return wrapper
    return decorator


# Caché global
_global_cache = LRUCache(max_size=2000, max_memory_mb=200, default_ttl=30.0)


# ============================================================================
# WEAK REFERENCE MANAGERS (de weak_ref_managers.py)
# ============================================================================

class GestorRegistry:
    """Registro de gestores con weak references."""
    
    _instance: Optional['GestorRegistry'] = None
    
    def __new__(cls) -> 'GestorRegistry':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        if self._initialized:
            return
        
        self._gestores: Dict[str, weakref.ref] = {}
        self._initialized = True
    
    def register(self, nombre: str, gestor: Any) -> None:
        """Registra un gestor con weak reference."""
        self._gestores[nombre] = weakref.ref(gestor)
    
    def get(self, nombre: str) -> Optional[Any]:
        """Obtiene un gestor del registro."""
        ref = self._gestores.get(nombre)
        if ref is None:
            return None
        
        gestor = ref()
        if gestor is None:
            # Gestor fue garbage collected
            del self._gestores[nombre]
            return None
        
        return gestor
    
    def cleanup(self) -> None:
        """Limpia referencias muertas."""
        dead_keys = [
            key for key, ref in self._gestores.items()
            if ref() is None
        ]
        for key in dead_keys:
            del self._gestores[key]
