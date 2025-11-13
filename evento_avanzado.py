# evento_avanzado.py
from datetime import datetime
from typing import Dict, List, Optional, Any
import hashlib

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
