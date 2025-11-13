# dependency_container.py
"""
Contenedor de inyección de dependencias para gestión centralizada.
"""
from typing import Dict, Any, Type, Callable, Optional
import threading
from functools import wraps


class ServiceContainer:
    """Contenedor singleton para inyección de dependencias."""
    
    _instance: Optional['ServiceContainer'] = None
    _lock: threading.Lock = threading.Lock()
    
    def __new__(cls) -> 'ServiceContainer':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        if self._initialized:
            return
        
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Callable] = {}
        self._singletons: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._initialized = True
    
    def register_singleton(self, name: str, instance: Any) -> None:
        """Registra una instancia singleton."""
        with self._lock:
            self._singletons[name] = instance
    
    def register_factory(self, name: str, factory: Callable) -> None:
        """Registra una factory para crear instancias."""
        with self._lock:
            self._factories[name] = factory
    
    def get(self, name: str) -> Any:
        """Obtiene un servicio del contenedor."""
        with self._lock:
            # Primero buscar en singletons
            if name in self._singletons:
                return self._singletons[name]
            
            # Luego en factories
            if name in self._factories:
                instance = self._factories[name]()
                # Cache la instancia si es singleton
                self._singletons[name] = instance
                return instance
            
            raise KeyError(f"Service '{name}' not registered")
    
    def inject(self, *dependencies: str) -> Callable:
        """Decorador para inyección automática de dependencias."""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                injected = {dep: self.get(dep) for dep in dependencies}
                return func(*args, **injected, **kwargs)
            return wrapper
        return decorator
