# reliability_utils.py
"""
Utilidades de confiabilidad y concurrencia para OPTIMUSTANK.
Consolida: circuit_breaker.py, rate_limiter.py, lockfree.py
"""
from typing import Callable, Any, Optional, List
from functools import wraps
import threading
import time
from enum import Enum
from collections import deque


# ============================================================================
# CIRCUIT BREAKER (de circuit_breaker.py)
# ============================================================================

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


# ============================================================================
# RATE LIMITER (de rate_limiter.py)
# ============================================================================

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


# ============================================================================
# ESTRUCTURAS THREAD-SAFE (de lockfree.py)
# ============================================================================

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
