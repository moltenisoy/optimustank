# rate_limiter.py
"""
Rate limiter para prevenir sobrecarga.
"""
from typing import Optional, Callable
import threading
import time
from collections import deque
from functools import wraps


class TokenBucket:
    """Implementación de Token Bucket para rate limiting con espera eficiente."""
    
    def __init__(self, rate: float, capacity: int) -> None:
        """
        Args:
            rate: Tokens por segundo
            capacity: Capacidad máxima del bucket
        """
        self.rate = rate
        self.capacity = capacity
        self._tokens = float(capacity)
        self._last_update = time.monotonic()
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
    
    def consume(self, tokens: int = 1) -> bool:
        """Intenta consumir tokens, no bloqueante."""
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False
    
    def _refill(self) -> None:
        """Rellena tokens basado en el tiempo transcurrido. Debe llamarse bajo lock."""
        now = time.monotonic()
        elapsed = now - self._last_update
        if elapsed > 0:
            new_tokens = elapsed * self.rate
            self._tokens = min(self.capacity, self._tokens + new_tokens)
            self._last_update = now
        # Notificar a los que esperan si hay tokens
        if self._tokens >= 1:
            self._condition.notify_all()
    
    def wait(self, tokens: int = 1) -> None:
        """Espera (bloquea) hasta que haya suficientes tokens disponibles."""
        with self._lock:
            while self._tokens < tokens:
                self._refill()
                # Calcular tiempo de espera para el próximo token
                required = tokens - self._tokens
                wait_time = required / self.rate
                self._condition.wait(timeout=wait_time)
            self._tokens -= tokens


class RateLimiter:
    """Rate limiter con múltiples estrategias."""
    
    def __init__(
        self,
        max_calls: int,
        time_window: float,
        strategy: str = "token_bucket"
    ) -> None:
        self.max_calls = max_calls
        self.time_window = time_window
        self.strategy = strategy
        
        if strategy == "token_bucket":
            self._limiter = TokenBucket(
                rate=max_calls / time_window,
                capacity=max_calls
            )
        else:  # sliding_window
            self._calls = deque(maxlen=max_calls)
            self._lock = threading.Lock()
    
    def allow(self) -> bool:
        """Verifica si se permite una llamada."""
        if self.strategy == "token_bucket":
            return self._limiter.consume()
        else:
            return self._sliding_window_allow()
    
    def _sliding_window_allow(self) -> bool:
        """Implementación de sliding window."""
        with self._lock:
            now = time.monotonic()
            
            # Limpiar llamadas antiguas
            while self._calls and (now - self._calls[0]) > self.time_window:
                self._calls.popleft()
            
            # Verificar límite
            if len(self._calls) < self.max_calls:
                self._calls.append(now)
                return True
            
            return False
    
    def wait(self) -> None:
        """Espera hasta que se permita una llamada."""
        while not self.allow():
            time.sleep(0.01)


def rate_limit(max_calls: int, time_window: float) -> Callable:
    """Decorador de rate limiting."""
    limiter = RateLimiter(max_calls, time_window)
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            limiter.wait()
            return func(*args, **kwargs)
        
        return wrapper
    
    return decorator
