# circuit_breaker.py
"""
Implementación del patrón Circuit Breaker para estabilidad.
"""
from typing import Callable, Any, Optional
from functools import wraps
import threading
import time
from enum import Enum


class CircuitState(Enum):
    """Estados del circuit breaker."""
    CLOSED = "closed"      # Normal
    OPEN = "open"          # Fallando, rechaza peticiones
    HALF_OPEN = "half_open"  # Probando recuperación


class CircuitBreaker:
    """Circuit breaker avanzado con backoff exponencial y lógica de fallo custom."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: float = 10.0,
        timeout_factor: float = 2.0,
        max_timeout: float = 300.0,
        failure_exception: type = Exception
    ) -> None:
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.base_timeout = timeout
        self.timeout_factor = timeout_factor
        self.max_timeout = max_timeout
        self.failure_exception = failure_exception
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._current_timeout = timeout
        self._last_failure_time: Optional[float] = None
        self._lock = threading.Lock()
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Ejecuta una función protegida por el circuit breaker."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                if (time.monotonic() - self._last_failure_time) > self._current_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                else:
                    raise self.failure_exception(f"Circuit breaker is OPEN. Timeout: {self._current_timeout:.2f}s")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        
        except self.failure_exception as e:
            self._on_failure()
            raise e
    
    def _on_success(self) -> None:
        """Maneja el éxito de una llamada."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self.reset()
            else:
                self._failure_count = 0
    
    def _on_failure(self) -> None:
        """Maneja el fallo de una llamada."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            
            if self._state == CircuitState.HALF_OPEN:
                self._open()
            elif self._failure_count >= self.failure_threshold:
                self._open()
    
    def _open(self):
        """Abre el circuito y aplica backoff."""
        self._state = CircuitState.OPEN
        self._current_timeout = min(self.max_timeout, self._current_timeout * self.timeout_factor)
    
    def reset(self) -> None:
        """Resetea el circuit breaker."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
    
    @property
    def state(self) -> CircuitState:
        """Estado actual del circuit breaker."""
        with self._lock:
            return self._state


def circuit_breaker(
    failure_threshold: int = 5,
    timeout: float = 60.0
) -> Callable:
    """Decorador de circuit breaker."""
    breaker = CircuitBreaker(failure_threshold=failure_threshold, timeout=timeout)
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)
        
        wrapper.circuit_breaker = breaker
        return wrapper
    
    return decorator
