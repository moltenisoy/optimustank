# gestor_redes.py
"""
Gestor avanzado de redes con optimización TCP/IP, predicción, tuning agresivo,
QoS, análisis de paquetes y detección de anomalías.
"""
from base_gestor_Version2 import BaseGestor, Task
from rate_limiter import rate_limit
import subprocess
import psutil
import socket
import platform
from typing import Dict, List, Optional, Tuple
import threading
import re
from collections import deque
import numpy as np
from datetime import timedelta

class GestorRedes(BaseGestor):
    def __init__(self):
        super().__init__("GestorRedes")
        
        self.trafico_umbral = self.config.redes.trafico_umbral
        self.latencia_maxima = self.config.redes.latencia_maxima
        self.latencia_critica = self.config.redes.latencia_critica
        
        self.interfaz_activa = self._detectar_interfaz_activa()
        self.historial_latencia = deque(maxlen=300)
        self.historial_trafico = deque(maxlen=300)
        self.interfaces_monitoreadas = {}
        self.perdida_paquetes_total = 0
        self.optimizaciones_aplicadas = 0
        self.conexiones_activas = {}
        
        self.logger.info(f"GestorRedes inicializado. Interfaz: {self.interfaz_activa}")
    
    def _detectar_interfaz_activa(self) -> Optional[str]:
        """Detecta la interfaz de red activa."""
        try:
            if platform.system() == "Windows":
                output = subprocess.check_output(['ipconfig'], universal_newlines=True)
                interfaces = re.findall(r'Adaptador.*?\n.*?(?=Adaptador|$)', output, re.DOTALL)
                
                for interfaz in interfaces:
                    if 'Dirección IPv4' in interfaz and not '169.254' in interfaz:
                        nombre = re.search(r'Adaptador (.*?):', interfaz)
                        if nombre:
                            return nombre.group(1).strip()
            else:
                resultado = subprocess.check_output(['ip', 'link'], universal_newlines=True)
                interfaces = re.findall(r'^\d+: (\w+):', resultado, re.MULTILINE)
                
                for interfaz in interfaces:
                    if interfaz not in ['lo', 'docker0']:
                        try:
                            socket.gethostbyname(socket.gethostname())
                            return interfaz
                        except:
                            pass
        except Exception as e:
            self.logger.warning(f"Error detectando interfaz: {e}")
        
        return None
    
    def obtener_metricas_interfaces_detalladas(self) -> Dict:
        """Obtiene métricas muy detalladas de todas las interfaces."""
        metricas = {}
        
        try:
            io_counters = psutil.net_io_counters(pernic=True)
            conexiones = psutil.net_connections()
            
            for interfaz, stats in io_counters.items():
                total_bytes = stats.bytes_sent + stats.bytes_recv
                total_packets = stats.packets_sent + stats.packets_recv
                total_errors = stats.errin + stats.errout
                total_drops = stats.dropin + stats.dropout
                
                tasa_error = (total_errors / total_packets * 100) if total_packets > 0 else 0
                
                metricas[interfaz] = {
                    'trafico': {
                        'bytes_enviados': stats.bytes_sent,
                        'bytes_recibidos': stats.bytes_recv,
                        'bytes_totales': total_bytes,
                        'paquetes_enviados': stats.packets_sent,
                        'paquetes_recibidos': stats.packets_recv,
                        'paquetes_totales': total_packets,
                        'tasa_transferencia_mb_s': 0
                    },
                    'errores': {
                        'errores_entrada': stats.errin,
                        'errores_salida': stats.errout,
                        'total_errores': total_errors,
                        'tasa_error_pct': tasa_error
                    },
                    'descartados': {
                        'descartados_entrada': stats.dropin,
                        'descartados_salida': stats.dropout,
                        'total_descartados': total_drops
                    }
                }
                
                self.metricas.registrar(
                    f'trafico_{interfaz}',
                    total_bytes / (1024**2),
                    tags={'paquetes': total_packets, 'errores': total_errors}
                )
            
            conexiones_por_estado = {}
            for conn in conexiones:
                estado = conn.status
                conexiones_por_estado[estado] = conexiones_por_estado.get(estado, 0) + 1
            
            metricas['conexiones_activas'] = conexiones_por_estado
            
            self.interfaces_monitoreadas = metricas
            return metricas
        
        except Exception as e:
            self.registrar_evento("ERROR_METRICAS_RED", str(e), "WARNING")
            return {}
    
    def analizar_conexiones_sospechosas(self) -> List[Dict]:
        """Analiza conexiones para detectar actividad sospechosa."""
        sospechosas = []
        
        try:
            conexiones = psutil.net_connections(kind='inet')
            
            for conn in conexiones:
                try:
                    if conn.status == 'ESTABLISHED' and conn.raddr:
                        puerto_remoto = conn.raddr.port
                        ip_remota = conn.raddr.ip
                        
                        if puerto_remoto in [445, 139, 135, 4444, 5555]:
                            sospechosas.append({
                                'ip_local': conn.laddr.ip if conn.laddr else 'N/A',
                                'puerto_local': conn.laddr.port if conn.laddr else 0,
                                'ip_remota': ip_remota,
                                'puerto_remoto': puerto_remoto,
                                'estado': conn.status,
                                'razon': 'Puerto comúnmente explotado'
                            })
                
                except:
                    pass
            
            if sospechosas:
                self.registrar_evento(
                    "CONEXIONES_SOSPECHOSAS",
                    f"Detectadas {len(sospechosas)} conexiones sospechosas",
                    "WARNING",
                    prioridad=8
                )
            
            return sospechosas
        
        except Exception as e:
            self.logger.debug(f"Error analizando conexiones: {e}")
            return []
    
    @rate_limit(max_calls=5, time_window=1.0)
    def medir_latencia_icmp(self, host: str = "8.8.8.8", count: int = 3, timeout: int = 2) -> Optional[Dict]:
        """Mide latencia ICMP de forma eficiente usando icmplib."""
        try:
            from icmplib import ping
            
            host_info = ping(host, count=count, timeout=timeout)
            
            if not host_info.is_alive:
                self.perdida_paquetes_total += count
                return None
            
            latencia_promedio = host_info.avg_rtt
            self.historial_latencia.append(latencia_promedio)
            self.perdida_paquetes_total += host_info.packet_loss
            
            return {
                'host': host,
                'latencia_min': host_info.min_rtt,
                'latencia_max': host_info.max_rtt,
                'latencia_promedio': latencia_promedio,
                'jitter': host_info.jitter,
                'paquetes_perdidos': int(host_info.packet_loss * count),
                'tasa_perdida_pct': host_info.packet_loss * 100,
                'estado': 'critica' if latencia_promedio > self.latencia_critica else 
                         'alerta' if latencia_promedio > self.latencia_maxima else 'normal'
            }
            
        except ImportError:
            self.logger.warning("icmplib no encontrado. La medición de latencia será menos precisa.")
            return self._medir_latencia_fallback(host, count)
        except Exception as e:
            self.logger.error(f"Error midiendo latencia ICMP a {host} con icmplib: {e}")
            return None
    
    def analizar_tendencia_latencia(self) -> Dict:
        """Analiza tendencia de latencia."""
        if len(self.historial_latencia) < 10:
            return {'analisis_disponible': False}
        
        valores = list(self.historial_latencia)
        x = np.arange(len(valores))
        y = np.array(valores)
        
        coef = np.polyfit(x, y, 1)[0]
        
        return {
            'analisis_disponible': True,
            'tendencia': 'empeorando' if coef > 2 else 'mejorando' if coef < -2 else 'estable',
            'tasa_cambio': float(coef),
            'promedio_actual': float(valores[-1]),
            'promedio_30_ultimos': float(np.mean(valores[-30:])) if len(valores) >= 30 else float(np.mean(valores)),
            'desviacion_estandar': float(np.std(valores))
        }
    
    def optimizar_dns(self):
        """Optimiza y limpia caché DNS."""
        try:
            if platform.system() == "Windows":
                subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=5)
                self.logger.debug("Caché DNS limpiado (Windows)")
            else:
                subprocess.run(["sudo", "systemctl", "restart", "systemd-resolved"], 
                             capture_output=True, timeout=5)
                self.logger.debug("Caché DNS limpiado (Linux)")
            
            self.registrar_evento("DNS_OPTIMIZADO", "Caché DNS vaciado y optimizado", "INFO")
        
        except Exception as e:
            self.registrar_evento("ERROR_DNS", str(e), "WARNING")
    
    def configurar_dns_rapido(self):
        """Configura servidores DNS rápidos (Cloudflare/Google)."""
        try:
            if platform.system() == "Windows":
                subprocess.run(
                    ['netsh', 'interface', 'ip', 'set', 'dns', 
                     f'"{self.interfaz_activa}"', 'static', '1.1.1.1'],
                    capture_output=True, timeout=5
                )
                subprocess.run(
                    ['netsh', 'interface', 'ip', 'add', 'dns', 
                     f'"{self.interfaz_activa}"', '8.8.8.8', 'index=2'],
                    capture_output=True, timeout=5
                )
                
                self.registrar_evento(
                    "DNS_RAPIDO_CONFIGURADO",
                    "DNS cambiado a Cloudflare/Google",
                    "INFO"
                )
        
        except Exception as e:
            self.logger.debug(f"Error configurando DNS: {e}")
    
    def optimizar_tcp_ip(self, agresivo: bool = False):
        """Optimiza parámetros TCP/IP del sistema."""
        try:
            if platform.system() == "Windows":
                optimizaciones = [
                    "netsh int tcp set global autotuninglevel=normal",
                    "netsh int tcp set global ecn=enabled",
                    "netsh int tcp set global congestionprovider=ctcp",
                    "netsh int tcp set global timestampvalidation=disabled",
                    "netsh int tcp set global chimney=enabled",
                    "netsh int tcp set global netdma=enabled",
                    "netsh int tcp set global dca=enabled"
                ]
                
                if agresivo:
                    optimizaciones.extend([
                        "netsh int tcp set global autotuninglevel=experimental",
                        "netsh int tcp set global timestamps=enabled",
                        "netsh int tcp set global rss=enabled",
                        "netsh int tcp set global fastopen=enabled",
                        "netsh int tcp set global hystart=enabled"
                    ])
                
                for cmd in optimizaciones:
                    try:
                        subprocess.run(cmd, shell=True, timeout=5, capture_output=True)
                    except:
                        pass
                
                self.optimizaciones_aplicadas += 1
                self.registrar_evento(
                    "TCP_IP_OPTIMIZADO",
                    f"Parámetros TCP/IP optimizados ({'agresivo' if agresivo else 'normal'})",
                    "INFO"
                )
            
            else:
                ajustes = [
                    ('net.core.rmem_max', '134217728'),
                    ('net.core.wmem_max', '134217728'),
                    ('net.ipv4.tcp_rmem', '4096 87380 67108864'),
                    ('net.ipv4.tcp_wmem', '4096 65536 67108864'),
                    ('net.ipv4.tcp_congestion_control', 'bbr'),
                    ('net.core.default_qdisc', 'fq'),
                    ('net.ipv4.tcp_fastopen', '3')
                ]
                
                for param, valor in ajustes:
                    try:
                        subprocess.run(
                            f"echo {valor} | sudo tee /proc/sys/{param.replace('.', '/')}",
                            shell=True, timeout=5
                        )
                    except:
                        pass
        
        except Exception as e:
            self.registrar_evento("ERROR_TCP_TUNING", str(e), "WARNING")
    
    def optimizar_qos(self):
        """Optimiza Quality of Service (QoS)."""
        try:
            if platform.system() == "Windows":
                subprocess.run(
                    ['netsh', 'int', 'tcp', 'set', 'global', 'pacingprofile=aggressive'],
                    capture_output=True, timeout=5
                )
                
                self.registrar_evento("QOS_OPTIMIZADO", "QoS configurado en agresivo", "INFO")
        
        except Exception as e:
            self.logger.debug(f"Error optimizando QoS: {e}")
    
    def limpiar_conexiones_huerfanas(self):
        """Limpia conexiones TIME_WAIT y huérfanas."""
        try:
            conexiones = psutil.net_connections(kind='tcp')
            limpiadas = 0
            
            for conn in conexiones:
                try:
                    if conn.status in ['TIME_WAIT', 'CLOSE_WAIT']:
                        if conn.pid:
                            proc = psutil.Process(conn.pid)
                            proc.terminate()
                            limpiadas += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            if limpiadas > 0:
                self.registrar_evento(
                    "CONEXIONES_LIMPIADAS",
                    f"Conexiones huérfanas cerradas: {limpiadas}",
                    "INFO"
                )
        
        except Exception as e:
            self.logger.debug(f"Error limpiando conexiones: {e}")
    
    def diagnosticar_red(self) -> Dict:
        """Diagnóstico completo de la red."""
        return {
            'interfaces': self.obtener_metricas_interfaces_detalladas(),
            'latencia': self.medir_latencia_icmp(),
            'tendencia_latencia': self.analizar_tendencia_latencia(),
            'conexiones_sospechosas': self.analizar_conexiones_sospechosas(),
            'umbrales': {
                'trafico': self.trafico_umbral,
                'latencia_maxima': self.latencia_maxima,
                'latencia_critica': self.latencia_critica
            },
            'estadisticas': {
                'perdida_paquetes_total': self.perdida_paquetes_total,
                'optimizaciones_aplicadas': self.optimizaciones_aplicadas
            }
        }
    
    def obtener_estadisticas(self) -> Dict:
        """Retorna estadísticas."""
        return self.diagnosticar_red()
    
    def setup_tasks(self):
        """Configura y añade las tareas de gestión de red al scheduler."""
        self.scheduler.add_task(Task("obtener_metricas_red", self.obtener_metricas_interfaces_detalladas, timedelta(seconds=10)))
        self.scheduler.add_task(Task("medir_latencia", self.medir_latencia_icmp, timedelta(seconds=30)))
        self.scheduler.add_task(Task("analizar_conexiones_sospechosas", self.analizar_conexiones_sospechosas, timedelta(minutes=1)))
        self.scheduler.add_task(Task("optimizar_dns", self.optimizar_dns, timedelta(minutes=2)))
        self.scheduler.add_task(Task("limpiar_conexiones_huerfanas", self.limpiar_conexiones_huerfanas, timedelta(minutes=3)))
        self.scheduler.add_task(Task("optimizar_tcp_ip", self.optimizar_tcp_ip, timedelta(minutes=5)))

        # Suscripción a eventos de modo juego
        self.event_bus.subscribe("GameModeStarted", self._on_game_mode_started)
        self.event_bus.subscribe("GameModeStopped", self._on_game_mode_stopped)

    def _on_game_mode_started(self, event):
        """Aplica QoS para priorizar el tráfico del juego."""
        self.registrar_evento("GAME_MODE_RED", "Priorizando tráfico de red para juegos...", "INFO")
        self.optimizar_qos_juego(prioridad=True)

    def _on_game_mode_stopped(self, event):
        """Restaura la configuración de red normal."""
        self.registrar_evento("GAME_MODE_RED", "Restaurando configuración de red normal...", "INFO")
        self.optimizar_qos_juego(prioridad=False)

    def optimizar_qos_juego(self, prioridad: bool):
        """Aplica o quita políticas de QoS para juegos."""
        if platform.system() != "Windows":
            return
        
        nombre_politica = "OptimizadorJuegoQoS"
        
        if prioridad:
            # Crear política de QoS
            # Esto es un ejemplo y requeriría una implementación más robusta
            # con una lista de ejecutables de juegos.
            subprocess.run(
                f'powershell -Command "New-NetQosPolicy -Name {nombre_politica} -AppPathNameMatchCondition \'*.exe\' -PriorityValue8021Action 5"',
                shell=True, capture_output=True
            )
        else:
            # Eliminar política de QoS
            subprocess.run(
                f'powershell -Command "Remove-NetQosPolicy -Name {nombre_politica}"',
                shell=True, capture_output=True
            )
