# test_framework.py
"""
Framework de testing minimalista integrado.
"""
from typing import Callable, List, Dict, Any, Optional
import time
import traceback
from dataclasses import dataclass
from enum import Enum


class TestStatus(Enum):
    """Estados de test."""
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


@dataclass
class TestResult:
    """Resultado de un test."""
    name: str
    status: TestStatus
    duration: float
    error: Optional[str] = None
    traceback: Optional[str] = None


class TestRunner:
    """Runner de tests integrado."""
    
    def __init__(self) -> None:
        self._tests: List[Callable] = []
        self._results: List[TestResult] = []
    
    def test(self, func: Callable) -> Callable:
        """Decorador para registrar tests."""
        self._tests.append(func)
        return func
    
    def run_all(self) -> Dict[str, Any]:
        """Ejecuta todos los tests."""
        self._results.clear()
        
        for test_func in self._tests:
            result = self._run_test(test_func)
            self._results.append(result)
        
        return self._generate_report()
    
    def _run_test(self, test_func: Callable) -> TestResult:
        """Ejecuta un test individual."""
        start = time.perf_counter()
        
        try:
            test_func()
            status = TestStatus.PASSED
            error = None
            tb = None
        
        except AssertionError as e:
            status = TestStatus.FAILED
            error = str(e)
            tb = traceback.format_exc()
        
        except Exception as e:
            status = TestStatus.ERROR
            error = str(e)
            tb = traceback.format_exc()
        
        duration = time.perf_counter() - start
        
        return TestResult(
            name=test_func.__name__,
            status=status,
            duration=duration,
            error=error,
            traceback=tb
        )
    
    def _generate_report(self) -> Dict[str, Any]:
        """Genera reporte de tests."""
        passed = sum(1 for r in self._results if r.status == TestStatus.PASSED)
        failed = sum(1 for r in self._results if r.status == TestStatus.FAILED)
        errors = sum(1 for r in self._results if r.status == TestStatus.ERROR)
        
        return {
            'total': len(self._results),
            'passed': passed,
            'failed': failed,
            'errors': errors,
            'success_rate': passed / len(self._results) * 100 if self._results else 0,
            'results': [
                {
                    'name': r.name,
                    'status': r.status.value,
                    'duration': r.duration,
                    'error': r.error
                }
                for r in self._results
            ]
        }
