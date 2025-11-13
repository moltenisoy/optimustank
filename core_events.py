# core_events.py
"""
Sistema unificado de eventos, event sourcing y tracing para OPTIMUSTANK.
Consolida: evento_avanzado.py, event_sourcing.py, tracing.py
"""
from datetime import datetime
from typing import Dict, List, Optional, Any, Type
from dataclasses import dataclass, field
import json
import threading
from pathlib import Path
import hashlib
import time
import uuid
from contextlib import contextmanager
from abc import ABC, abstractmethod


# ============================================================================
# EVENTOS AVANZADOS (de evento_avanzado.py)
# ============================================================================

class EventoAvanzado:
    """Evento con prioridad, contexto y seguimiento."""
    
    def __init__(self, tipo: str, mensaje: str, nivel: str = "INFO", 
                 modulo: str = "", contexto: Optional[Dict] = None, prioridad: int = 5) -> None:
        self.timestamp: datetime = datetime.now()
        self.tipo: str = tipo
        self.mensaje: str = mensaje
        self.nivel: str = nivel
        self.modulo: str = modulo
        self.contexto: Dict = contexto or {}
        self.prioridad: int = prioridad
        self.id: str = hashlib.md5(f"{self.timestamp}{tipo}{mensaje}".encode()).hexdigest()[:12]
        self.procesado: bool = False
        self.respuestas: List = []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat(),
            'tipo': self.tipo,
            'mensaje': self.mensaje,
            'nivel': self.nivel,
            'modulo': self.modulo,
            'contexto': self.contexto,
            'prioridad': self.prioridad,
            'procesado': self.procesado
        }


# ============================================================================
# EVENT SOURCING (de event_sourcing.py)
# ============================================================================

@dataclass
class DomainEvent:
    """Evento de dominio inmutable."""
    event_id: str
    event_type: str
    aggregate_id: str
    timestamp: datetime
    payload: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    version: int = 1


class EventStore:
    """Almacén de eventos optimizado con indexación en memoria."""
    
    def __init__(self, storage_path: str = "events.jsonl") -> None:
        self.storage_path = Path(storage_path)
        self._lock = threading.Lock()
        self._index: Dict[str, List[int]] = {}  # aggregate_id -> [file_positions]
        
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.storage_path.exists():
            self.storage_path.touch()
        
        self._build_index()

    def _build_index(self):
        """Construye el índice en memoria a partir del archivo de eventos."""
        with self.storage_path.open('r') as f:
            position = 0
            for line in f:
                try:
                    data = json.loads(line)
                    agg_id = data.get('aggregate_id')
                    if agg_id:
                        if agg_id not in self._index:
                            self._index[agg_id] = []
                        self._index[agg_id].append(position)
                except json.JSONDecodeError:
                    pass
                position = f.tell()

    def append(self, event: DomainEvent) -> None:
        """Añade un evento al almacén y actualiza el índice."""
        event_data = {
            'event_id': event.event_id,
            'event_type': event.event_type,
            'aggregate_id': event.aggregate_id,
            'timestamp': event.timestamp.isoformat(),
            'payload': event.payload,
            'metadata': event.metadata,
            'version': event.version
        }
        json_line = json.dumps(event_data) + '\n'
        
        with self._lock:
            with self.storage_path.open('a') as f:
                position = f.tell()
                f.write(json_line)
            
            # Actualizar índice
            if event.aggregate_id not in self._index:
                self._index[event.aggregate_id] = []
            self._index[event.aggregate_id].append(position)
    
    def get_events_for_aggregate(self, aggregate_id: str) -> List[DomainEvent]:
        """Obtiene eventos para un agregado usando el índice."""
        events = []
        with self._lock:
            positions = self._index.get(aggregate_id, [])
            if not positions:
                return []
            
            with self.storage_path.open('r') as f:
                for pos in positions:
                    f.seek(pos)
                    line = f.readline()
                    try:
                        data = json.loads(line)
                        events.append(DomainEvent(
                            event_id=data['event_id'],
                            event_type=data['event_type'],
                            aggregate_id=data['aggregate_id'],
                            timestamp=datetime.fromisoformat(data['timestamp']),
                            payload=data['payload'],
                            metadata=data.get('metadata', {}),
                            version=data.get('version', 1)
                        ))
                    except (json.JSONDecodeError, KeyError):
                        pass
        
        events.sort(key=lambda e: e.timestamp)
        return events


# ============================================================================
# TRACING DISTRIBUIDO (de tracing.py)
# ============================================================================

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
            self._export_spans([span])


# Singleton global
_tracer = Tracer()


def get_tracer() -> Tracer:
    """Obtiene el tracer global."""
    return _tracer
