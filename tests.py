# tests.py
from test_framework import TestRunner
from gestor_memoria_Version2 import GestorMemoria
from memory_utils import LRUCache
from base_gestor_Version2 import EventBus, AppConfig
from core_events import EventoAvanzado
from dependency_container import ServiceContainer
import logging
import threading
import time
from reliability_utils import CircuitState

def initialize_services_for_testing():
    """Initializes a lightweight version of services for testing."""
    container = ServiceContainer()
    
    # Mock/lightweight config
    config = AppConfig()
    container.register_singleton('config', config)
    
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    container.register_singleton('event_bus', EventBus())
    # Mock scheduler and metrics if complex dependencies arise
    # For now, let's see if this is enough.
    from base_gestor_Version2 import Scheduler, MetricasColector
    container.register_singleton('scheduler', Scheduler())
    container.register_singleton('metrics', MetricasColector())

# Initialize services before defining tests that might need them
initialize_services_for_testing()

runner = TestRunner()

@runner.test
def test_memory_manager_initialization():
    """Test inicialización del gestor de memoria."""
    gestor = GestorMemoria()
    assert gestor.nombre == "GestorMemoria"
    assert gestor.activo is True

@runner.test
def test_cache_hit():
    """Test de hit en caché."""
    cache = LRUCache(max_size=10)
    cache.set("key1", "value1")
    result = cache.get("key1")
    assert result == "value1"

@runner.test
def test_event_bus_publish_async():
    """Test de publicación asíncrona en event bus."""
    container = ServiceContainer()
    bus = container.get('event_bus')
    received = []
    event_processed = threading.Event()

    def callback(event):
        time.sleep(0.1) # Simular trabajo
        received.append(event)
        event_processed.set()
    
    bus.subscribe("test_async_event", callback)
    event = EventoAvanzado("test_async_event", "Test async message")
    bus.publish(event)
    
    assert len(received) == 0 # Debería ser asíncrono
    event_processed.wait(timeout=1) # Esperar a que el callback termine
    assert len(received) == 1
    assert received[0].tipo == "test_async_event"

@runner.test
def test_thread_safe_queue():
    """Test para la cola thread-safe."""
    from reliability_utils import ThreadSafeQueue
    q = ThreadSafeQueue()
    q.put(1)
    q.put(2)
    assert q.get() == 1
    assert len(q) == 1

@runner.test
def test_circuit_breaker_backoff():
    """Test de backoff exponencial en circuit breaker."""
    from reliability_utils import CircuitBreaker
    breaker = CircuitBreaker(failure_threshold=2, timeout=0.1, timeout_factor=2)
    
    def failing_func():
        raise ValueError("Fallo")

    # Abrir el circuito
    for _ in range(2):
        try:
            breaker.call(failing_func)
        except ValueError:
            pass
    
    assert breaker.state == CircuitState.OPEN
    assert breaker._current_timeout == 0.2 # Backoff aplicado

def run_system_tests():
    """Ejecuta tests del sistema y muestra un reporte detallado."""
    report = runner.run_all()
    
    print("\\n" + "="*60)
    print("TEST RESULTS")
    print("="*60)
    print(f"Total: {report['total']}")
    print(f"Passed: {report['passed']} ({report['success_rate']:.1f}%)")
    print(f"Failed: {report['failed']}")
    print(f"Errors: {report['errors']}")
    print("="*60)
    
    for result in report['results']:
        status_icon = "✓" if result['status'] == "PASSED" else "✗"
        print(f"{status_icon} {result['name']} ({result['duration']:.3f}s)")
        if result['error']:
            print(f"  Error: {result['error']}")
    
    # Exit with a non-zero code if there are failures or errors
    if report['failed'] > 0 or report['errors'] > 0:
        exit(1)

if __name__ == "__main__":
    run_system_tests()
