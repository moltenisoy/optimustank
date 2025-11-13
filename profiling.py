# profiling.py
"""
Sistema de profiling integrado con bajo overhead.
"""
import cProfile
import pstats
import io
from typing import Callable, Any, Optional, Dict
from functools import wraps
import threading
import time


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
