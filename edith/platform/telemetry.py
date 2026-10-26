"""Per-sensor fault isolation, nonblocking psutil reads and a cached sampler."""
from __future__ import annotations
import json
import os
import platform
from pathlib import Path
import shutil
import threading
import time
import psutil

def safe(call,default=None):
    try:return call()
    except Exception:return default

def record(obj):
    return obj._asdict() if hasattr(obj,'_asdict') else obj

class TelemetryCollector:
    def __init__(self,system=None,read_command=None):
        self.system=system or platform.system();self.read_command=read_command
        self._last_net=None;self._last_time=None;self._gpu=None;self._gpu_at=-100.;self._temp=None;self._temp_at=-100.
        self._nvml=None
    def gpu(self):
        now=time.monotonic()
        if now-self._gpu_at<15:return self._gpu
        self._gpu_at=now
        try:
            import pynvml
            if self._nvml is None:pynvml.nvmlInit();self._nvml=pynvml
            h=pynvml.nvmlDeviceGetHandleByIndex(0)
            self._gpu={'name':pynvml.nvmlDeviceGetName(h),'percent':float(pynvml.nvmlDeviceGetUtilizationRates(h).gpu),'source':'NVML'}
            return self._gpu
        except Exception:pass
        try:
            if self.read_command and shutil.which('nvidia-smi'):
                line=self.read_command(['nvidia-smi','--query-gpu=name,utilization.gpu','--format=csv,noheader,nounits']).splitlines()[0]
                name,pct=line.rsplit(',',1);self._gpu={'name':name.strip(),'percent':float(pct),'source':'nvidia-smi'}
            elif self.system=='Darwin' and self.read_command:
                data=json.loads(self.read_command(['system_profiler','SPDisplaysDataType','-json'],timeout=5))
                gpu=data.get('SPDisplaysDataType',[{}])[0];self._gpu={'name':gpu.get('sppci_model'),'percent':None,'source':'system_profiler'}
            elif self.system=='Windows' and self.read_command:
                name=self.read_command(['powershell','-NoProfile','-Command','(Get-CimInstance Win32_VideoController).Name'])
                self._gpu={'name':name,'percent':None,'source':'WMI'}
            elif self.system=='Linux' and self.read_command and shutil.which('lspci'):
                lines=self.read_command(['lspci']).splitlines();name=next((x for x in lines if any(s in x.lower() for s in ['vga','3d controller','display controller'])),None)
                self._gpu={'name':name,'percent':None,'source':'lspci'} if name else None
            elif self.system=='Linux':
                cards=list(Path('/sys/class/drm').glob('card[0-9]/device/vendor'))
                self._gpu={'name':'PCI vendor '+cards[0].read_text().strip(),'percent':None,'source':'sysfs'} if cards else None
        except Exception:self._gpu=None
        return self._gpu
    def temperature(self):
        now=time.monotonic()
        if now-self._temp_at<5:return self._temp
        self._temp_at=now;self._temp=None
        try:
            values=psutil.sensors_temperatures()
            entries=[item for group in values.values() for item in group if item.current is not None]
            if entries:self._temp={'celsius':max(x.current for x in entries),'source':'psutil'}
        except Exception:pass
        if self._temp is None and self.system=='Windows':
            try:
                import wmi
                try:
                    rows=wmi.WMI(namespace='root/LibreHardwareMonitor').Sensor(SensorType='Temperature')
                    temps=[float(s.Value) for s in rows if s.Value is not None]
                    if temps:self._temp={'celsius':max(temps),'source':'LibreHardwareMonitor'}
                except Exception:
                    rows=wmi.WMI(namespace='root/wmi').MSAcpi_ThermalZoneTemperature()
                    if rows:self._temp={'celsius':rows[0].CurrentTemperature/10-273.15,'source':'WMI'}
            except Exception:pass
        return self._temp
    def sample(self):
        now=time.monotonic();net=safe(lambda:psutil.net_io_counters());throughput=None
        if net is not None and self._last_net is not None and now>self._last_time:
            throughput={'sent_bps':max(0,(net.bytes_sent-self._last_net.bytes_sent)/(now-self._last_time)),
                        'received_bps':max(0,(net.bytes_recv-self._last_net.bytes_recv)/(now-self._last_time))}
        self._last_net,self._last_time=net,now
        boot=safe(lambda:psutil.boot_time());battery=safe(lambda:psutil.sensors_battery())
        disk_root=Path.home().anchor or '/'
        return {'timestamp':time.time(),'cpu_percent':safe(lambda:psutil.cpu_percent(interval=None)),
            'cpu_per_core':safe(lambda:psutil.cpu_percent(interval=None,percpu=True)),
            'cpu_frequency':record(safe(lambda:psutil.cpu_freq())),'load_average':safe(lambda:psutil.getloadavg()),
            'memory':record(safe(lambda:psutil.virtual_memory())),'swap':record(safe(lambda:psutil.swap_memory())),
            'disk':record(safe(lambda:psutil.disk_usage(disk_root))),'disk_io':record(safe(lambda:psutil.disk_io_counters())),
            'network':record(net),'throughput':throughput,'battery':record(battery),
            'uptime_seconds':max(0,time.time()-boot) if boot else None,
            'process_count':safe(lambda:len(psutil.pids())),'gpu':self.gpu(),'temperature':self.temperature(),
            'os':self.system}

class TelemetryService:
    def __init__(self,controller):
        self.controller=controller;self._lock=threading.Lock();self._snapshot={};self._stop=threading.Event()
        self._thread=threading.Thread(target=self._run,daemon=True,name='edith-platform-telemetry')
    def start(self):self._thread.start()
    def _run(self):
        while not self._stop.is_set():
            # Internal sensor sampling is not an external tool call. Explicit
            # controller.telemetry() requests still receive normal audit receipts.
            from .base import result
            try:value=result(data=self.controller._op_telemetry())
            except Exception as exc:value=result(False,error=type(exc).__name__)
            with self._lock:self._snapshot=value
            self._stop.wait(1)
    def snapshot(self):
        with self._lock:return dict(self._snapshot)
    def stop(self):self._stop.set()
