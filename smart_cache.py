# smart_cache.py
"""
Sistema de caché avanzado con TTL, LRU y warming.
"""
from typing import Any, Callable, Optional, Dict, TypeVar, Generic
from functools import wraps
import threading
import time
from collections import OrderedDict
import hashlib
import pickle
import sys

T = TypeVar('T')


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
            # Si no es serializable, no podemos estimar bien, retornamos un tamaño base
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
        
        # LIFO: eliminar el primero (menos reciente)
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
    """
    Decorador para cachear resultados de funciones.
    
    Args:
        cache: Instancia de LRUCache (usa global si None)
        ttl: Tiempo de vida en segundos
        key_func: Función para generar clave del caché
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generar clave del caché
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Clave por defecto: hash de args y kwargs
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
