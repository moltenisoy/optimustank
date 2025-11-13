# main.py
"""
Punto de entrada principal para el Optimizador de Sistema Avanzado.
Inicializa el contenedor de dependencias, los gestores y arranca el scheduler.
"""
import time
import logging
from dependency_container import ServiceContainer
from base_gestor_Version2 import ConfigManager, EventBus, Scheduler, MetricasColector
from gestor_cpu_Version2 import GestorCPU
from gestor_memoria_Version2 import GestorMemoria
from gestor_disco import GestorDisco
from gestor_redes_Version2 import GestorRedes
from gestor_gpu_Version2 import GestorGPU
from gestor_servicios_Version2 import GestorServicios
from gestor_tareas_Version2 import GestorTareas
from gestor_kernel_Version2 import GestorKernel
from gestor_energia import GestorEnergia
from gestor_modulos_Version2 import GestorModulos
from gestor_gui_Version2 import GestorGUI
from object_pool import EventoAvanzadoPool

def initialize_services():
    """Inicializa todos los servicios singleton en el contenedor de dependencias."""
    container = ServiceContainer()
    
    # Configuración primero
    config = ConfigManager()
    container.register_singleton('config', config)
    
    # Logging básico
    log_level = config.config.logging.level
    logging.basicConfig(level=getattr(logging, log_level),
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Registrar servicios principales
    container.register_singleton('event_bus', EventBus())
    container.register_singleton('scheduler', Scheduler())
    container.register_singleton('metrics', MetricasColector())
    
    # Inicializar pool de eventos
    EventoAvanzadoPool.initialize()

def main():
    """Función principal de la aplicación."""
    print("Iniciando Optimizador de Sistema Avanzado v2.0...")
    
    # 1. Inicializar servicios base
    initialize_services()
    container = ServiceContainer()
    scheduler = container.get('scheduler')
    
    # 2. Instanciar todos los gestores
    # El constructor de BaseGestor se encargará de inyectar las dependencias
    # y de registrarse en el GestorRegistry
    print("Inicializando gestores...")
    gestores = [
        GestorCPU(),
        GestorMemoria(),
        GestorDisco(),
        GestorRedes(),
        GestorGPU(),
        GestorServicios(),
        GestorTareas(),
        GestorKernel(),
        GestorEnergia(),
        GestorModulos(),
        # GestorGUI() # La GUI podría iniciarse por separado
    ]
    
    # 3. Configurar las tareas de cada gestor
    print("Configurando tareas programadas...")
    for gestor in gestores:
        try:
            gestor.setup_tasks()
            print(f" - Tareas de {gestor.nombre} configuradas.")
        except Exception as e:
            logging.error(f"Error configurando tareas para {gestor.nombre}: {e}")
            
    # 4. Arrancar el scheduler en un thread separado
    print("Arrancando scheduler...")
    scheduler.start()
    
    print("\nSistema de optimización activo. Presione Ctrl+C para detener.")
    
    try:
        # Mantener el programa principal corriendo
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDeteniendo el sistema...")
        scheduler.stop()
        print("Scheduler detenido. Saliendo.")

if __name__ == "__main__":
    main()
