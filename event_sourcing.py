# event_sourcing.py
"""
Event sourcing para auditabilidad completa del sistema.
"""
from typing import Any, List, Dict, Optional, Type
from dataclasses import dataclass, field
from datetime import datetime
import json
import threading
from pathlib import Path


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
