"""Mock OS mutations; run only disposable files/processes for real execution."""
import ast
import contextvars
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch,Mock
from edith.platform import get_controller
from edith.platform.base import SystemController
from edith.platform.permissions import PermissionBroker,CURRENT,ExecutionContext
from edith.platform.processes import run_streamed,shell_argv,REGISTRY
from edith.platform.telemetry import TelemetryCollector,TelemetryService

class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.audit=Mock()
    def controller(self,os='Linux',approve=True):
        return get_controller(os,permissions=PermissionBroker(confirmer=lambda *a:approve),audit=self.audit)
    def test_factory_uses_runtime_platform_and_unknown_falls_back(self):
        for name,cls in [('Windows','WindowsController'),('Darwin','MacOSController'),('Linux','LinuxController'),('Other','GenericController')]:
            with self.subTest(name=name),patch('edith.platform.platform.system',return_value=name):
                self.assertEqual(type(get_controller(audit=self.audit)).__name__,cls)
    def test_every_operation_returns_structured_failure_instead_of_raising(self):
        for system in ['Windows','Darwin','Linux','Other']:
            controller=self.controller(system)
            for op in controller.OPERATIONS:
                with self.subTest(system=system,op=op),patch.object(controller,'_op_'+op,side_effect=NotImplementedError('no device'),create=True):
                    r=controller.invoke(op)
                    self.assertEqual(set(r),{'ok','data','error','unsupported'})
                    self.assertFalse(r['ok']);self.assertTrue(r['unsupported'])
    def test_missing_optional_library_is_unsupported(self):
        c=self.controller()
        with patch.object(c,'_op_volume',side_effect=ImportError('missing')):
            self.assertTrue(c.volume(25)['unsupported'])
    def test_native_command_failure_is_not_success(self):
        c=self.controller('Darwin')
        with patch('edith.platform.base.run_streamed',return_value={'exit_code':1,'cancelled':False,'timed_out':False}):
            self.assertFalse(c.volume(50)['ok'])
    def test_no_confirmation_bypass_and_tier_three_cannot_autoapprove(self):
        c=self.controller(approve=False)
        c.permissions.settings={'auto_approve':True,'tiers':{'power':0,'shell':0}}
        with patch.object(c,'_op_power') as power,patch.object(c,'_op_shell') as shell:
            self.assertFalse(c.invoke('power',{'action':'shutdown','confirmed':True})['ok'])
            self.assertFalse(c.shell('echo test')['ok'])
            power.assert_not_called();shell.assert_not_called()
        self.assertEqual(c.permissions.tier('power',{}),3)
        self.assertEqual(c.permissions.tier('shell',{}),2)
    def test_unknown_operation_and_bad_arguments_do_not_crash(self):
        c=self.controller()
        self.assertTrue(c.invoke('no_such_capability')['unsupported'])
        self.assertFalse(c.invoke('telemetry',17)['ok'])
    def test_expired_execution_cannot_write(self):
        c=self.controller()
        token=CURRENT.set(ExecutionContext('test',c.permissions.generation))
        try:
            c.permissions.cancel_all()
            with patch.object(c,'_op_file_write') as write:
                self.assertFalse(c.file_operations('file_write',path='dummy',text='no')['ok'])
                write.assert_not_called()
        finally:CURRENT.reset(token)
    def test_file_create_is_exclusive_and_denied_overwrite_preserves_contents(self):
        c=self.controller(approve=False)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'sample.txt'
            self.assertTrue(c.file_operations('file_create',path=str(p),text='first')['ok'])
            self.assertFalse(c.file_operations('file_create',path=str(p),text='second')['ok'])
            self.assertFalse(c.file_operations('file_write',path=str(p),text='third')['ok'])
            self.assertEqual(p.read_text(),'first')
    def test_os_theme_probes(self):
        winreg=NS(HKEY_CURRENT_USER=1,OpenKey=Mock(),QueryValueEx=Mock(return_value=(0,0)))
        winreg.OpenKey.return_value.__enter__=Mock(return_value=object());winreg.OpenKey.return_value.__exit__=Mock(return_value=False)
        with patch.dict(sys.modules,winreg=winreg):
            self.assertEqual(self.controller('Windows').theme()['data']['theme'],'dark')
        mac=self.controller('Darwin')
        with patch.object(mac,'_read_command',return_value='Dark'):
            self.assertEqual(mac.theme()['data']['theme'],'dark')
        with patch.object(mac,'_read_command',side_effect=OSError('key absent')):
            self.assertEqual(mac.theme()['data']['theme'],'light')
        linux=self.controller()
        with patch('shutil.which',return_value='/usr/bin/gsettings'),patch.object(linux,'_read_command',return_value="'prefer-dark'"):
            self.assertEqual(linux.theme()['data']['theme'],'dark')
    def test_os_power_commands_are_mocked_and_validated(self):
        for system in ['Windows','Darwin','Linux']:
            c=self.controller(system)
            with self.subTest(system=system),patch.object(c,'_command',return_value={'ok':True,'data':{},'error':None,'unsupported':False}) as cmd,patch('shutil.which',return_value='/usr/bin/systemctl'):
                self.assertTrue(c.power('restart')['ok']);cmd.assert_called_once()
                self.assertFalse(c.power('invented')['ok'])
    def test_wayland_windows_explicitly_unsupported(self):
        with patch.dict(os.environ,WAYLAND_DISPLAY='wayland-0'):
            self.assertTrue(self.controller().window_list()['unsupported'])
    def test_linux_missing_control_tools_explicitly_unsupported(self):
        with patch('shutil.which',return_value=None):
            self.assertTrue(self.controller().volume(20)['unsupported'])
            self.assertTrue(self.controller().brightness(20)['unsupported'])
    def test_shell_selection(self):
        with patch('shutil.which',side_effect=lambda x:'/bin/'+x):
            self.assertIn('pwsh',shell_argv('echo hi','Windows')[0])
            self.assertEqual(shell_argv('echo hi','Darwin')[0],'/bin/zsh')
            self.assertEqual(shell_argv('echo hi','Linux')[0],'/bin/bash')

class StreamTests(unittest.TestCase):
    def test_stdout_streams_before_exit_without_waiting_for_a_full_buffer(self):
        started=time.monotonic();seen=[]
        r=run_streamed([sys.executable,'-u','-c','import time,sys;print("first",flush=True);time.sleep(.6);print("last");print("error",file=sys.stderr)'],on_output=lambda stream,text:seen.append((stream,text,time.monotonic()-started)))
        self.assertEqual(r['exit_code'],0)
        self.assertIn('last',r['stdout']);self.assertIn('error',r['stderr'])
        self.assertLess(next(t for stream,text,t in seen if 'first' in text),.55)
    def test_timeout_reaps_process_and_retains_output(self):
        r=run_streamed([sys.executable,'-u','-c','import time;print("started");time.sleep(10)'],timeout=.15)
        self.assertTrue(r['timed_out']);self.assertIn('started',r['stdout'])
        self.assertNotIn(r['pid'],REGISTRY.snapshot())
    def test_cancellation_invalidates_running_command(self):
        broker=PermissionBroker();token=CURRENT.set(ExecutionContext('test',broker.generation))
        timer=threading.Timer(.15,broker.cancel_all);timer.start()
        try:
            r=run_streamed([sys.executable,'-c','import time;time.sleep(10)'],broker=broker)
            self.assertTrue(r['cancelled']);self.assertNotIn(r['pid'],REGISTRY.snapshot())
        finally:CURRENT.reset(token);timer.cancel()

class TelemetryTests(unittest.TestCase):
    def test_failures_are_isolated_and_never_fabricated(self):
        import psutil
        t=TelemetryCollector('Other')
        with patch.object(psutil,'virtual_memory',side_effect=OSError()),patch.object(psutil,'net_io_counters',side_effect=OSError()),patch.object(t,'gpu',return_value=None),patch.object(t,'temperature',return_value=None):
            data=t.sample()
        self.assertIsNone(data['memory']);self.assertIsNone(data['throughput']);self.assertIsNone(data['gpu'])
        self.assertIn('cpu_per_core',data);self.assertIn('disk_io',data)
    def test_absent_psutil_methods_on_macos_are_individually_na(self):
        collector=TelemetryCollector('Darwin')
        fake=NS(cpu_percent=lambda **kw: [3.] if kw.get('percpu') else 3.)
        with patch('edith.platform.telemetry.psutil',fake),patch.object(collector,'gpu',return_value=None),patch.object(collector,'temperature',return_value=None):
            data=collector.sample()
        self.assertEqual(data['cpu_percent'],3.)
        self.assertIsNone(data['cpu_frequency'])
        self.assertIsNone(data['battery'])
        self.assertIsNone(data['memory'])

    def test_cached_snapshot_does_not_wait_for_slow_sensor(self):
        release=threading.Event()
        c=NS(_op_telemetry=lambda:release.wait(2))
        service=TelemetryService(c);service.start()
        try:
            start=time.monotonic();self.assertEqual(service.snapshot(),{})
            self.assertLess(time.monotonic()-start,.05)
        finally:release.set();service.stop()
    def test_qt_metric_update_has_no_hardware_calls(self):
        tree=ast.parse((Path(__file__).resolve().parents[1]/'ui.py').read_text(encoding='utf-8'))
        method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_update_metrics')
        calls=[ast.unparse(n.func) for n in ast.walk(method) if isinstance(n,ast.Call)]
        self.assertFalse(any(x.startswith(('psutil.','subprocess.')) for x in calls))
