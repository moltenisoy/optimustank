# weak_ref_managers.py
"""
Sistema de referencias débiles para gestores.
"""
import weakref
from typing import Dict, Optional, Any


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
