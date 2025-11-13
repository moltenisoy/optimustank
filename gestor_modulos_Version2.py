# gestor_modulos.py
"""
Orquestador central que sincroniza todos los módulos del sistema en tiempo real.
Gestiona sinergias, comunicación inter-módulos y control centralizado.
ACTUALIZADO con gestor_energia y gestor_disco.
"""
import sys
import platform
import threading
import time
from typing import Dict, List, Optional
from datetime import datetime
import json
from collections import deque

# Importar todos los gestores
from gestor_gui import GUIManager
from gestor_energia import GestorEnergia  # NUEVO
from gestor_kernel import GestorKernel
from gestor_servicios import GestorServicios
from gestor_gpu import GestorGPU
from gestor_redes import GestorRedes
from gestor_cpu import GestorCPU
from gestor_tareas import GestorTareas
from gestor_memoria import GestorMemoria
from gestor_disco import GestorDisco  # NUEVO
from base_gestor import ConfigManager

class SistemaDesinergias:
    """Sistema de sinergia entre módulos para optimización coordinada."""
    
    def __init__(self):
        self.reglas_sinergia = {
            'memoria_critica': self._reaccion_memoria_critica,
            'cpu_saturada': self._reaccion_cpu_saturada,
            'gpu_caliente': self._reaccion_gpu_caliente,
            'red_lenta': self._reaccion_red_lenta,
            'servicio_caido': self._reaccion_servicio_caido,
            'disco_lleno': self._reaccion_disco_lleno,
            'bateria_baja': self._reaccion_bateria_baja
        }
        self.historial_sinergias = deque(maxlen=500)
    
    def _reaccion_memoria_critica(self, gestor_modulos):
        """Reacción coordinada ante memoria crítica."""
        gestor_modulos.memoria.liberar_memoria_agresiva(5)
        gestor_modulos.gpu.optimizar_memoria_gpu()
        gestor_modulos.kernel.limpiar_memoria_virtual()
        gestor_modulos.disco.limpiar_archivos_temporales()
        
        if gestor_modulos.memoria.obtener_uso_memoria_detallado().get('memoria_fisica', {}).get('porcentaje', 0) > 92:
            gestor_modulos.energia.aplicar_perfil_energia('ahorro')
    
    def _reaccion_cpu_saturada(self, gestor_modulos):
        """Reacción coordinada ante CPU saturada."""
        gestor_modulos.cpu.distribuir_carga_inteligente()
        gestor_modulos.cpu.optimizar_prioridades_procesamiento()
        gestor_modulos.kernel.auto_tune_dinamico()
        gestor_modulos.energia.gestionar_termica_cpu()
    
    def _reaccion_gpu_caliente(self, gestor_modulos):
        """Reacción coordinada ante GPU sobrecalentada."""
        gestor_modulos.gpu._aplicar_cooling_agresivo()
        gestor_modulos.kernel.recuperacion_bajo_estres()
        gestor_modulos.energia.aplicar_perfil_energia('balanced')
    
    def _reaccion_red_lenta(self, gestor_modulos):
        """Reacción coordinada ante red lenta."""
        gestor_modulos.redes.optimizar_tcp_ip(agresivo=True)
        gestor_modulos.redes.optimizar_dns()
        gestor_modulos.redes.limpiar_conexiones_huerfanas()
    
    def _reaccion_servicio_caido(self, gestor_modulos):
        """Reacción coordinada ante servicio caído."""
        gestor_modulos.servicios.verificar_servicios_criticos()
        gestor_modulos.servicios.limpiar_procesos_huerfanos()
    
    def _reaccion_disco_lleno(self, gestor_modulos):
        """Reacción coordinada ante disco lleno."""
        gestor_modulos.disco.limpiar_archivos_temporales()
        gestor_modulos.tareas._tarea_limpiar_temp()
        gestor_modulos.tareas._tarea_compactar_registros()
    
    def _reaccion_bateria_baja(self, gestor_modulos):
        """Reacción coordinada ante batería baja."""
        gestor_modulos.energia.aplicar_perfil_energia('ahorro_maximo')
        gestor_modulos.gpu._aplicar_cooling_agresivo()
        gestor_modulos.cpu.ajustar_prioridades_segun_carga()

class GestorModulos:
    """Orquestador central de todos los módulos."""
    
    def __init__(self):
        if not platform.machine().endswith('64'):
            sys.exit("Esta aplicación requiere arquitecturas x64 (64 bits).")
        
        self.config = ConfigManager()
        self.activo = True
        self.paused = False
        self.hilos = []
        self.historial_diagnosticos = deque(maxlen=100)
        
        print("[INIT] Validando arquitectura...")
        print("[INIT] Inicializando módulos...")
        
        # Inicializar módulos
        self.gui = GUIManager()
        self.energia = GestorEnergia()  # NUEVO - Reemplazo de prioridades
        self.kernel = GestorKernel()
        self.servicios = GestorServicios()
        self.gpu = GestorGPU()
        self.redes = GestorRedes()
        self.cpu = GestorCPU()
        self.tareas = GestorTareas()
        self.memoria = GestorMemoria()
        self.disco = GestorDisco()  # NUEVO
        
        # Sistema de sinergias
        self.sinergias = SistemaDesinergias()
        
        # Conectar callbacks
        self._conectar_callbacks()
        
        # Iniciar threads de módulos
        self._iniciar_threads_modulos()
        
        print("[INIT] ✓ Módulos inicializados correctamente")
        self.registrar_evento_sistema(
            "SISTEMA_INICIADO",
            "Sistema de optimización iniciado correctamente",
            "INFO",
            prioridad=10
        )
    
    def _conectar_callbacks(self):
        """Conecta callbacks entre módulos para sincronización."""
        modulos = [
            self.memoria, self.cpu, self.gpu, self.redes,
            self.energia, self.kernel, self.servicios, self.tareas, self.disco
        ]
        
        for modulo in modulos:
            modulo.agregar_callback(self._callback_evento_global)
    
    def _callback_evento_global(self, evento):
        """Callback global que procesa eventos de todos los módulos."""
        try:
            self.gui.agregar_evento_gui(evento.tipo, evento.mensaje, evento.nivel)
            
            # Activar sinergias según evento
            if evento.tipo == "MEMORIA_CRITICA":
                self.sinergias._reaccion_memoria_critica(self)
            elif evento.tipo == "DESBALANCE_CPU_CRITICO":
                self.sinergias._reaccion_cpu_saturada(self)
            elif evento.tipo == "GPU_TEMPERATURA_CRITICA":
                self.sinergias._reaccion_gpu_caliente(self)
            elif evento.tipo == "LATENCIA_CRITICA":
                self.sinergias._reaccion_red_lenta(self)
            elif evento.tipo == "SERVICIO_DETENIDO":
                self.sinergias._reaccion_servicio_caido(self)
            elif evento.tipo == "DISCO_LLENO":
                self.sinergias._reaccion_disco_lleno(self)
            elif evento.tipo == "BATERIA_BAJA":
                self.sinergias._reaccion_bateria_baja(self)
            
            # Notificaciones en GUI
            if evento.nivel == "ERROR":
                self.gui.mostrar_notificacion("❌ Error", evento.mensaje, 5)
            elif evento.nivel == "WARNING":
                self.gui.mostrar_notificacion("⚠️ Advertencia", evento.mensaje, 3)
        
        except Exception as e:
            print(f"[ERROR] Procesando evento: {e}")
    
    def _iniciar_threads_modulos(self):
        """Inicia threads de ejecución para cada módulo."""
        modulos = [
            (self.memoria, "Memoria"),
            (self.cpu, "CPU"),
            (self.gpu, "GPU"),
            (self.redes, "Redes"),
            (self.energia, "Energia"),
            (self.kernel, "Kernel"),
            (self.servicios, "Servicios"),
            (self.tareas, "Tareas"),
            (self.disco, "Disco")
        ]
        
        for modulo, nombre in modulos:
            thread = threading.Thread(target=modulo.run, name=f"Thread-{nombre}", daemon=True)
            thread.start()
            self.hilos.append(thread)
            print(f"[INIT] ✓ Thread {nombre} iniciado")
    
    def obtener_diagnostico_completo(self) -> Dict:
        """Retorna diagnóstico completo de todos los módulos."""
        diagnostico = {
            'timestamp': datetime.now().isoformat(),
            'salud_sistema': {
                'modulos_activos': sum(1 for h in self.hilos if h.is_alive()),
                'total_modulos': len(self.hilos),
                'estado_general': 'saludable' if sum(1 for h in self.hilos if h.is_alive()) == len(self.hilos) else 'degradado'
            },
            'cpu': self.cpu.obtener_estadisticas(),
            'memoria': self.memoria.obtener_estadisticas(),
            'gpu': self.gpu.obtener_estadisticas(),
            'redes': self.redes.obtener_estadisticas(),
            'energia': self.energia.obtener_estadisticas(),
            'disco': self.disco.obtener_estadisticas(),
            'servicios': self.servicios.obtener_estadisticas(),
            'tareas': self.tareas.obtener_estadisticas(),
            'kernel': self.kernel.obtener_estadisticas()
        }
        
        self.historial_diagnosticos.append(diagnostico)
        return diagnostico
    
    def guardar_diagnostico(self, nombre_archivo: str = None):
        """Guarda diagnóstico en archivo JSON."""
        if not nombre_archivo:
            nombre_archivo = f"diagnostico_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        try:
            with open(nombre_archivo, 'w', encoding='utf-8') as f:
                json.dump(self.obtener_diagnostico_completo(), f, indent=2)
            print(f"[✓] Diagnóstico guardado: {nombre_archivo}")
            self.registrar_evento_sistema("DIAGNOSTICO_GUARDADO", nombre_archivo, "INFO")
        except Exception as e:
            print(f"[ERROR] Guardando diagnóstico: {e}")
    
    def optimizar_segun_carga(self):
        """Auto-optimización adaptativa según carga del sistema."""
        diagnostico = self.obtener_diagnostico_completo()
        
        try:
            cpu_stats = diagnostico.get('cpu', {}).get('carga', {})
            cpu_avg = cpu_stats.get('promedio', 0)
            
            mem_stats = diagnostico.get('memoria', {}).get('uso_actual', {})
            if isinstance(mem_stats, dict):
                mem_pct = mem_stats.get('memoria_fisica', {}).get('porcentaje', 0)
            else:
                mem_pct = 0
            
            print(f"\n[AUTO-TUNE] CPU: {cpu_avg:.1f}% | MEM: {mem_pct:.1f}%")
            
            # Modo agresivo automático
            if cpu_avg > 85 or mem_pct > 85:
                print("[AUTO-TUNE] ⚡ Activando modo agresivo...")
                self.config.set('kernel.aggressive_mode', True)
                self.kernel.modo_agresivo = True
                self.kernel.nivel_agresividad = 5
                self.gui.mostrar_notificacion("⚡ Auto-Tune", "Modo agresivo activado", 3)
            
            elif cpu_avg < 50 and mem_pct < 50:
                print("[AUTO-TUNE] ✓ Desactivando modo agresivo...")
                self.config.set('kernel.aggressive_mode', False)
                self.kernel.modo_agresivo = False
                self.kernel.nivel_agresividad = 2
        
        except Exception as e:
            print(f"[ERROR] Auto-tune: {e}")
    
    def pausar_todos(self):
        """Pausa todos los módulos."""
        print("[PAUSA] Pausando todos los módulos...")
        modulos = [
            self.memoria, self.cpu, self.gpu, self.redes,
            self.energia, self.kernel, self.servicios, self.tareas, self.disco
        ]
        
        for modulo in modulos:
            modulo.pausar()
        
        self.paused = True
        print("[PAUSA] ✓ Todos los módulos pausados")
    
    def reanudar_todos(self):
        """Reanuda todos los módulos."""
        print("[REANUDACION] Reanudando todos los módulos...")
        modulos = [
            self.memoria, self.cpu, self.gpu, self.redes,
            self.energia, self.kernel, self.servicios, self.tareas, self.disco
        ]
        
        for modulo in modulos:
            modulo.reanudar()
        
        self.paused = False
        print("[REANUDACION] ✓ Todos los módulos reanudados")
    
    def obtener_estado_salud_sistema(self) -> Dict:
        """Obtiene estado de salud completo del sistema."""
        modulos = [
            (self.memoria, "Memoria"),
            (self.cpu, "CPU"),
            (self.gpu, "GPU"),
            (self.redes, "Redes"),
            (self.energia, "Energia"),
            (self.kernel, "Kernel"),
            (self.servicios, "Servicios"),
            (self.tareas, "Tareas"),
            (self.disco, "Disco")
        ]
        
        salud = {
            'timestamp': datetime.now().isoformat(),
            'modulos': {}
        }
        
        for modulo, nombre in modulos:
            salud['modulos'][nombre] = modulo.obtener_estado_salud()
        
        return salud
    
    def registrar_evento_sistema(self, tipo: str, mensaje: str, 
                                nivel: str = "INFO", prioridad: int = 5):
        """Registra evento en el sistema central."""
        print(f"[{nivel}] {tipo}: {mensaje}")
        self.memoria.registrar_evento(tipo, mensaje, nivel, prioridad)
    
    def run_all(self):
        """Bucle principal de gestión del sistema."""
        print("\n[RUN] Iniciando bucle principal del gestor...")
        
        contador = 0
        while self.activo:
            try:
                contador += 1
                
                if contador % 1 == 0:
                    try:
                        diagnostico = self.obtener_diagnostico_completo()
                        self.gui.actualizar_metricas(diagnostico)
                    except Exception as e:
                        pass
                
                if contador % 10 == 0:
                    self.optimizar_segun_carga()
                
                if contador % 60 == 0:
                    salud = self.obtener_estado_salud_sistema()
                    errores = [m for m in salud['modulos'].values() 
                              if m.get('contador_errores', 0) > 0]
                    if errores:
                        print(f"\n[ALERTA] Módulos con errores: {len(errores)}")
                
                if contador % 300 == 0:
                    self.guardar_diagnostico()
                
                time.sleep(1)
            
            except KeyboardInterrupt:
                print("\n[SHUTDOWN] Interrupción del usuario detectada...")
                break
            except Exception as e:
                print(f"[ERROR] En bucle principal: {e}")
                time.sleep(5)
        
        self.detener_sistema()
    
    def detener_sistema(self):
        """Detiene el sistema de forma ordenada."""
        print("\n[SHUTDOWN] Deteniendo sistema...")
        
        self.activo = False
        
        modulos = [
            self.memoria, self.cpu, self.gpu, self.redes,
            self.energia, self.kernel, self.servicios, self.tareas, self.disco, self.gui
        ]
        
        for modulo in modulos:
            modulo.detener()
        
        print("[SHUTDOWN] Esperando a que terminen threads...")
        for thread in self.hilos:
            thread.join(timeout=5)
        
        print("[SHUTDOWN] ✓ Sistema detenido correctamente")
        
        self.guardar_diagnostico("diagnostico_final.json")

def main():
    """Función principal."""
    try:
        print("=" * 60)
        print("OPTIMIZADOR DE SISTEMA AVANZADO v2.0 - EXPANDIDO")
        print("=" * 60)
        
        gestor = GestorModulos()
        gestor.run_all()
    
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Operación cancelada por el usuario")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR CRÍTICO] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()