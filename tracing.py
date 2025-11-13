# tracing.py
"""
Sistema de tracing distribuido para debugging.
"""
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
import threading
import time
import uuid
from contextlib import contextmanager
from abc import ABC, abstractmethod


@dataclass
class Span:
    """Representa un span de tracing."""
    
    trace_id: str
    span_id: str
    parent_id: Optional[str]
    operation: str
    start_time: float
    end_time: Optional[float] = None
    tags: Dict[str, Any] = field(default_factory=dict)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    
    def finish(self) -> None:
        """Finaliza el span."""
        self.end_time = time.time()
    
    def log(self, message: str, **fields) -> None:
        """Añade un log al span."""
        self.logs.append({
            'timestamp': time.time(),
            'message': message,
            **fields
        })
    
    def set_tag(self, key: str, value: Any) -> None:
        """Establece una etiqueta."""
        self.tags[key] = value
    
    def duration(self) -> float:
        """Duración del span en segundos."""
        if self.end_time is None:
            return time.time() - self.start_time
        return self.end_time - self.start_time


class OTExporter(ABC):
    """Interfaz para exportadores compatibles con OpenTelemetry."""
    @abstractmethod
    def export(self, spans: List[Span]):
        pass

class ConsoleExporter(OTExporter):
    """Exportador simple que imprime los spans a la consola."""
    def export(self, spans: List[Span]):
        for span in spans:
            print(f"TraceID: {span.trace_id}, SpanID: {span.span_id}, "
                  f"Operation: {span.operation}, Duration: {span.duration():.4f}s")

class Tracer:
    """Tracer avanzado con exportadores y contexto mejorado."""
    
    def __init__(self, exporters: Optional[List[OTExporter]] = None) -> None:
        self._spans_buffer: List[Span] = []
        self._local = threading.local()
        self._lock = threading.Lock()
        self._exporters = exporters or [ConsoleExporter()]
    
    def start_span(
        self,
        operation: str,
        tags: Optional[Dict[str, Any]] = None
    ) -> Span:
        """Inicia un nuevo span."""
        # Obtener trace_id del contexto actual
        trace_id = getattr(self._local, 'trace_id', str(uuid.uuid4()))
        parent_id = getattr(self._local, 'span_id', None)
        
        span = Span(
            trace_id=trace_id,
            span_id=str(uuid.uuid4()),
            parent_id=parent_id,
            operation=operation,
            start_time=time.time(),
            tags=tags or {}
        )
        
        self._local.trace_id = trace_id
        self._local.span_id = span.span_id
        
        return span
    
    def _export_spans(self, spans: List[Span]):
        """Envía los spans a todos los exportadores configurados."""
        for exporter in self._exporters:
            try:
                exporter.export(spans)
            except Exception as e:
                # En un sistema real, aquí habría un logger interno del tracer
                print(f"Error en exportador de trace: {e}")

    @contextmanager
    def trace(self, operation: str, **tags):
        """Context manager para tracing que auto-finaliza y exporta el span."""
        span = self.start_span(operation, tags)
        try:
            yield span
        except Exception as e:
            span.set_tag('error', True)
            span.log('exception', message=str(e))
            raise
        finally:
            span.finish()
            # Al finalizar el span raíz, se podría exportar el trace completo.
            # Esta lógica simple exporta cada span al finalizar.
            self._export_spans([span])


# Singleton global
_tracer = Tracer()


def get_tracer() -> Tracer:
    """Obtiene el tracer global."""
    return _tracer
