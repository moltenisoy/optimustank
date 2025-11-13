# gestor_kernel.py
"""
Gestor avanzado de kernel con optimizaciones extremas y tuning profesional.
Incluye ajustes de scheduler, I/O scheduler, network stack y memory management.
"""
from base_gestor import BaseGestor
import ctypes
import psutil
import os
import subprocess
from typing import Dict, List
import platform
import threading
import struct
import logging.handlers

from datetime import timedelta

class GestorKernel(BaseGestor):
    def __init__(self):
        super().__init__("GestorKernel")
        
        self.modo_agresivo = self.config.get('kernel.aggressive_mode', False)
        self.nivel_agresividad = self.config.get('kernel.aggressive_level', 5)
        self.auto_tuning = self.config.get('kernel.auto_tuning', True)
        self.cache_optimization = self.config.get('kernel.cache_optimization', True)
        self.pagefile_tuning = self.config.get('kernel.pagefile_tuning', True)
        
        self.parametros_kernel = {}
        self.optimizaciones_aplicadas = []
        self.recuperaciones_realizadas = 0
        self._original_settings = {}
        
        self.logger.info(f"GestorKernel: Nivel agresividad={self.nivel_agresividad}, "
                        f"Modo agresivo={'ON' if self.modo_agresivo else 'OFF'}")
    
    def _save_original_setting(self, key, value):
        """Guarda el valor original de un parámetro antes de modificarlo."""
        if key not in self._original_settings:
            self._original_settings[key] = value

    def rollback_changes(self):
        """Revierte los cambios a su estado original."""
        self.logger.info("Revirtiendo cambios del kernel a su estado original...")
        for key, value in self._original_settings.items():
            try:
                # Lógica para revertir. Depende de la plataforma.
                if platform.system() == "Linux":
                    subprocess.run(
                        f"echo {value} | sudo tee /proc/sys/{key.replace('.', '/')}",
                        shell=True, timeout=5, check=True
                    )
                # Implementar para Windows si es necesario
                self.logger.info(f"Parámetro '{key}' revertido a '{value}'.")
            except Exception as e:
                self.logger.error(f"No se pudo revertir el parámetro '{key}': {e}")
        self.optimizaciones_aplicadas.clear()

    def obtener_parametros_kernel_actuales(self) -> Dict:
        """Obtiene parámetros actuales del kernel."""
        parametros = {'timestamp': __import__('datetime').datetime.now().isoformat()}
        
        try:
            if platform.system() == "Windows":
                parametros['sistema_operativo'] = platform.platform()
                parametros['version_kernel'] = platform.release()
                
                try:
                    import winreg
                    
                    rutas_registro = [
                        (winreg.HKEY_LOCAL_MACHINE, 
                         r'SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management'),
                        (winreg.HKEY_LOCAL_MACHINE,
                         r'SYSTEM\CurrentControlSet\Services\Tcpip\Parameters'),
                    ]
                    
                    for base, path in rutas_registro:
                        try:
                            key = winreg.OpenKey(base, path)
                            idx = 0
                            while True:
                                try:
                                    valor, datos, tipo = winreg.EnumValue(key, idx)
                                    parametros[valor] = datos
                                    idx += 1
                                except OSError:
                                    break
                            winreg.CloseKey(key)
                        except:
                            pass
                
                except:
                    pass
            
            else:
                try:
                    output = subprocess.check_output(['sysctl', '-a'], 
                                                    universal_newlines=True,
                                                    timeout=10)
                    for linea in output.split('\n'):
                        if '=' in linea:
                            clave, valor = linea.split('=', 1)
                            parametros[clave.strip()] = valor.strip()
                except:
                    pass
            
            self.parametros_kernel = parametros
            return parametros
        
        except Exception as e:
            self.logger.error(f"Error obteniendo parámetros: {e}")
            return {}
    
    def optimizar_scheduler_kernel(self):
        """Optimiza scheduler del kernel."""
        try:
            if platform.system() == "Linux":
                ajustes = [
                    ('kernel.sched_migration_cost_ns', '5000000'),
                    ('kernel.sched_latency_ns', '10000000'),
                    ('kernel.sched_min_granularity_ns', '2000000'),
                    ('kernel.sched_wakeup_granularity_ns', '3000000'),
                    ('kernel.sched_child_runs_first', '1')
                ]
                
                for param, valor in ajustes:
                    try:
                        subprocess.run(
                            f"echo {valor} | sudo tee /proc/sys/{param.replace('.', '/')}",
                            shell=True, timeout=5
                        )
                    except:
                        pass
                
                self.registrar_evento(
                    "SCHEDULER_OPTIMIZADO",
                    f"Ajustados {len(ajustes)} parámetros",
                    "INFO"
                )
        
        except Exception as e:
            self.logger.debug(f"Error optimizando scheduler: {e}")
    
    def optimizar_io_scheduler(self):
        """Optimiza I/O scheduler."""
        try:
            if platform.system() == "Linux":
                for disco in ['sda', 'nvme0n1']:
                    ruta = f'/sys/block/{disco}/queue/scheduler'
                    if os.path.exists(ruta):
                        subprocess.run(
                            f"echo mq-deadline | sudo tee {ruta}",
                            shell=True, timeout=5
                        )
                
                self.registrar_evento(
                    "IO_SCHEDULER_OPTIMIZADO",
                    "Scheduler cambiado a mq-deadline",
                    "INFO"
                )
        
        except Exception as e:
            self.logger.debug(f"Error optimizando I/O scheduler: {e}")
    
    def optimizar_cache_sistema(self):
        """Optimiza caché del filesystem y memoria."""
        try:
            if not self.cache_optimization:
                return
            
            if platform.system() == "Windows":
                try:
                    min_cache = 4 * 1024 * 1024
                    max_cache = 256 * 1024 * 1024
                    
                    ctypes.windll.kernel32.SetSystemFileCacheSize(min_cache, max_cache, 0)
                    self.registrar_evento(
                        "CACHE_WINDOWS_OPTIMIZADO",
                        f"Min: {min_cache/(1024**2):.0f}MB, Max: {max_cache/(1024**2):.0f}MB",
                        "INFO"
                    )
                    self.optimizaciones_aplicadas.append("cache_sistema")
                except Exception as e:
                    self.logger.warning(f"Error optimizando caché: {e}")
            
            else:
                try:
                    os.system("echo 1 > /proc/sys/vm/drop_caches 2>/dev/null")
                    os.system("sync")
                    self.registrar_evento("CACHE_LINUX_OPTIMIZADO", "Caché limpiado", "INFO")
                except:
                    pass
        
        except Exception as e:
            self.registrar_evento("ERROR_CACHE", str(e), "WARNING")
    
    def limpiar_memoria_virtual(self):
        """Limpia memoria virtual y optimiza paging."""
        try:
            mem_antes = psutil.virtual_memory().used
            
            if platform.system() == "Windows":
                try:
                    proceso = ctypes.windll.kernel32.GetCurrentProcess()
                    ctypes.windll.kernel32.SetProcessWorkingSetSize(proceso, -1, -1)
                    
                    subprocess.run(
                        "rundll32.exe advapi32.dll,ProcessIdleTasks",
                        shell=True, timeout=5, capture_output=True
                    )
                    
                    mem_despues = psutil.virtual_memory().used
                    liberada = mem_antes - mem_despues
                    
                    if liberada > 0:
                        self.registrar_evento(
                            "MEMORIA_VIRTUAL_OPTIMIZADA",
                            f"Liberados: {liberada/(1024**2):.2f}MB",
                            "INFO"
                        )
                        self.optimizaciones_aplicadas.append("memoria_virtual")
                
                except Exception as e:
                    self.logger.warning(f"Error limpiando memoria virtual: {e}")
            
            else:
                try:
                    os.system("sync && echo 3 > /proc/sys/vm/drop_caches 2>/dev/null")
                    self.registrar_evento("MEMORIA_VIRTUAL_LINUX_OPTIMIZADA", 
                                        "Caché y swap optimizados", "INFO")
                except:
                    pass
        
        except Exception as e:
            self.registrar_evento("ERROR_MEMORIA_VIRTUAL", str(e), "WARNING")
    
    def activar_modo_agresivo(self):
        """Activa optimizaciones agresivas extremas del kernel."""
        if not self.modo_agresivo or self.nivel_agresividad < 1:
            return
        
        try:
            if platform.system() == "Windows":
                optimizaciones = []
                
                if self.nivel_agresividad >= 1:
                    optimizaciones.extend([
                        "netsh int tcp set global autotuninglevel=normal",
                        "netsh int tcp set global ecn=enabled",
                        "netsh int tcp set global timestamps=enabled",
                    ])
                
                if self.nivel_agresividad >= 2:
                    optimizaciones.extend([
                        "netsh int tcp set global autotuninglevel=experimental",
                        "netsh int tcp set global congestionprovider=ctcp",
                        "netsh int tcp set global dca=enabled",
                    ])
                
                if self.nivel_agresividad >= 3:
                    optimizaciones.extend([
                        "netsh int tcp set global rss=enabled",
                        "netsh int ip set global taskoffload=enabled",
                    ])
                
                if self.nivel_agresividad >= 4:
                    optimizaciones.extend([
                        "bcdedit /set nx AlwaysOn",
                        "bcdedit /set useplatformclock true",
                    ])
                
                if self.nivel_agresividad >= 5:
                    optimizaciones.extend([
                        "powercfg /change disk-timeout-ac 0",
                        "powercfg /change monitor-timeout-ac 0",
                        "powercfg /change standby-timeout-ac 0",
                    ])
                
                for cmd in optimizaciones:
                    try:
                        subprocess.run(cmd, shell=True, timeout=5, capture_output=True)
                        self.optimizaciones_aplicadas.append(cmd.split()[0])
                    except Exception as e:
                        self.logger.debug(f"Error aplicando {cmd}: {e}")
                
                self.registrar_evento(
                    "MODO_AGRESIVO_ACTIVADO",
                    f"Nivel {self.nivel_agresividad}/5 - {len(optimizaciones)} optimizaciones",
                    "INFO",
                    prioridad=6
                )
            
            else:
                optimizaciones = []
                
                ajustes_sysctl = {
                    1: {
                        'vm.swappiness': '10',
                        'vm.dirty_ratio': '20',
                    },
                    2: {
                        'vm.swappiness': '5',
                        'vm.dirty_ratio': '15',
                        'vm.dirty_background_ratio': '5',
                    },
                    3: {
                        'vm.swappiness': '1',
                        'vm.dirty_ratio': '10',
                        'vm.dirty_background_ratio': '2',
                        'net.ipv4.tcp_tw_reuse': '1',
                    },
                    4: {
                        'vm.swappiness': '0',
                        'kernel.sched_migration_cost_ns': '5000000',
                        'net.ipv4.tcp_fin_timeout': '10',
                    },
                    5: {
                        'kernel.sched_latency_ns': '5000000',
                        'kernel.sched_min_granularity_ns': '1000000',
                        'net.core.somaxconn': '65535',
                    }
                }
                
                for nivel in range(1, self.nivel_agresividad + 1):
                    for param, valor in ajustes_sysctl.get(nivel, {}).items():
                        try:
                            subprocess.run(
                                f"echo {valor} | sudo tee /proc/sys/{param.replace('.', '/')}",
                                shell=True, timeout=5
                            )
                            optimizaciones.append(param)
                        except:
                            pass
                
                if optimizaciones:
                    self.registrar_evento(
                        "MODO_AGRESIVO_LINUX",
                        f"Aplicadas {len(optimizaciones)} optimizaciones sysctl",
                        "INFO"
                    )
        
        except Exception as e:
            self.registrar_evento("ERROR_MODO_AGRESIVO", str(e), "WARNING")
    
    def optimizar_pagefile(self):
        """Optimiza archivo de paginación."""
        if not self.pagefile_tuning:
            return
        
        try:
            if platform.system() == "Windows":
                mem_total = psutil.virtual_memory().total
                tamano_recomendado = int(mem_total * 1.5 / (1024**3))
                
                try:
                    import winreg
                    key = winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        r'SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management',
                        0, winreg.KEY_WRITE
                    )
                    
                    winreg.SetValueEx(key, 'PagingFiles', 0, winreg.REG_MULTI_SZ,
                                     [f'C:\\pagefile.sys {tamano_recomendado} {tamano_recomendado}'])
                    
                    winreg.CloseKey(key)
                    
                    self.registrar_evento(
                        "PAGEFILE_OPTIMIZADO",
                        f"Tamaño: {tamano_recomendado}GB",
                        "INFO"
                    )
                    self.optimizaciones_aplicadas.append("pagefile")
                
                except:
                    pass
        
        except Exception as e:
            self.logger.warning(f"Error optimizando pagefile: {e}")
    
    def optimizar_red_kernel(self):
        """Optimiza parámetros de red a nivel kernel."""
        try:
            if platform.system() == "Linux":
                ajustes = [
                    ('net.core.netdev_max_backlog', '5000'),
                    ('net.core.rmem_max', '16777216'),
                    ('net.core.wmem_max', '16777216'),
                    ('net.ipv4.tcp_rmem', '4096 87380 16777216'),
                    ('net.ipv4.tcp_wmem', '4096 65536 16777216'),
                    ('net.ipv4.tcp_congestion_control', 'bbr')
                ]
                
                for param, valor in ajustes:
                    try:
                        subprocess.run(
                            f"echo {valor} | sudo tee /proc/sys/{param.replace('.', '/')}",
                            shell=True, timeout=5
                        )
                    except:
                        pass
                
                self.registrar_evento(
                    "RED_KERNEL_OPTIMIZADA",
                    f"Ajustados {len(ajustes)} parámetros",
                    "INFO"
                )
        
        except Exception as e:
            self.logger.debug(f"Error optimizando red kernel: {e}")
    
    def recuperacion_bajo_estres(self):
        """Recuperación automática bajo estrés extremo."""
        try:
            mem = psutil.virtual_memory()
            cpu_pct = psutil.cpu_percent(interval=0.5)
            
            if mem.percent > 92 or cpu_pct > 97:
                self.recuperaciones_realizadas += 1
                
                self.registrar_evento(
                    "RECUPERACION_BAJO_ESTRES",
                    f"CPU: {cpu_pct:.1f}%, MEM: {mem.percent:.1f}%",
                    "WARNING",
                    prioridad=9
                )
                
                self.limpiar_memoria_virtual()
                self.optimizar_cache_sistema()
                
                if mem.percent > 95:
                    nivel_anterior = self.nivel_agresividad
                    self.nivel_agresividad = 5
                    self.modo_agresivo = True
                    self.activar_modo_agresivo()
                    self.nivel_agresividad = nivel_anterior
        
        except Exception as e:
            self.logger.error(f"Error en recuperación: {e}")
    
    def auto_tune_dinamico(self):
        """Ajuste automático dinámico basado en carga del sistema."""
        if not self.auto_tuning:
            return
        
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            
            carga_total = (cpu * 0.6 + mem.percent * 0.4)
            
            if carga_total > 85:
                nuevo_nivel = min(5, self.nivel_agresividad + 1)
                if nuevo_nivel != self.nivel_agresividad:
                    self.nivel_agresividad = nuevo_nivel
                    self.modo_agresivo = True
                    self.registrar_evento(
                        "AUTO_TUNE_AUMENTADO",
                        f"Nivel: {self.nivel_agresividad}",
                        "INFO"
                    )
            
            elif carga_total < 40:
                nuevo_nivel = max(1, self.nivel_agresividad - 1)
                if nuevo_nivel != self.nivel_agresividad:
                    self.nivel_agresividad = nuevo_nivel
                    self.registrar_evento(
                        "AUTO_TUNE_REDUCIDO",
                        f"Nivel: {self.nivel_agresividad}",
                        "INFO"
                    )
        
        except Exception as e:
            self.logger.debug(f"Error en auto-tune: {e}")
    
    def obtener_estadisticas(self) -> Dict:
        """Retorna estadísticas del kernel."""
        return {
            'parametros_kernel': self.obtener_parametros_kernel_actuales(),
            'configuracion': {
                'modo_agresivo': self.modo_agresivo,
                'nivel_agresividad': self.nivel_agresividad,
                'auto_tuning': self.auto_tuning,
                'cache_optimization': self.cache_optimization
            },
            'estadisticas': {
                'optimizaciones_aplicadas': len(self.optimizaciones_aplicadas),
                'recuperaciones': self.recuperaciones_realizadas,
                'optimizaciones_lista': list(set(self.optimizaciones_aplicadas))
            }
        }
    
    def optimizar_registro_windows(self):
        """Aplica optimizaciones seguras al Registro de Windows."""
        if platform.system() != "Windows":
            return
        
        try:
            import winreg
            optimizaciones = {
                r'SYSTEM\CurrentControlSet\Control\FileSystem': [
                    ("NtfsDisableLastAccessUpdate", 1, winreg.REG_DWORD),
                ],
                r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile': [
                    ("SystemResponsiveness", 0, winreg.REG_DWORD),
                ],
            }

            for path, settings in optimizaciones.items():
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_WRITE)
                    for name, value, type in settings:
                        winreg.SetValueEx(key, name, 0, type, value)
                    winreg.CloseKey(key)
                except Exception as e:
                    self.logger.warning(f"Error optimizando registro en {path}: {e}")
            
            self.registrar_evento("REGISTRO_OPTIMIZADO", "Optimizaciones seguras aplicadas al registro.", "INFO")
        except Exception as e:
            self.logger.error(f"Error al optimizar el registro: {e}")

    def setup_tasks(self):
        """Configura y añade las tareas de optimización del kernel al scheduler."""
        scheduler.add_task(Task("optimizar_registro_windows", self.optimizar_registro_windows, timedelta(days=7)))
        scheduler.add_task(Task("obtener_parametros_kernel", self.obtener_parametros_kernel_actuales, timedelta(minutes=5)))
        scheduler.add_task(Task("optimizar_cache_sistema", self.optimizar_cache_sistema, timedelta(minutes=1)))
        scheduler.add_task(Task("limpiar_memoria_virtual", self.limpiar_memoria_virtual, timedelta(minutes=2)))
        scheduler.add_task(Task("activar_modo_agresivo", self.activar_modo_agresivo, timedelta(minutes=5)))
        scheduler.add_task(Task("optimizar_pagefile", self.optimizar_pagefile, timedelta(minutes=10)))
        scheduler.add_task(Task("optimizar_scheduler_kernel", self.optimizar_scheduler_kernel, timedelta(minutes=10)))
        scheduler.add_task(Task("optimizar_io_scheduler", self.optimizar_io_scheduler, timedelta(minutes=10)))
        scheduler.add_task(Task("optimizar_red_kernel", self.optimizar_red_kernel, timedelta(minutes=15)))
        scheduler.add_task(Task("recuperacion_bajo_estres", self.recuperacion_bajo_estres, timedelta(seconds=30)))
        scheduler.add_task(Task("auto_tune_dinamico", self.auto_tune_dinamico, timedelta(seconds=30)))