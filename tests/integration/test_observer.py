#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from dwc2_diag.descriptors import (DescriptorError, cached_descriptors,
                                   configuration_descriptor, string_descriptor)
from dwc2_diag.identification import identify, load_database
from dwc2_diag.observer import (ObservationError, StateObserver, command_json,
                               kernel_errors, observe, read_snapshot)

DEVICE = bytes.fromhex('1201000200000040ac05a712100301020301')
CONFIG = bytes.fromhex('09022000010105c0010904000002fffe02060705020200020007058102000200')
INSPECTION = {'serial_policy':'redacted', 'device_descriptor':{'raw':DEVICE.hex(),'serial_index':3},
              'device':{'vendor_id':1452,'product_id':4775,'address':3},
              'configurations':[{'status':'ok','raw':CONFIG.hex()}],
              'strings':[{'index':3,'status':'redacted','redacted':True}]}
INFO = {'bus': 1, 'address': 3, 'vendor_id': 1452, 'product_id': 4775, 'class': 0,
        'sysfs_name': '1-1', 'ports': [1], 'path': '/dev/bus/usb/001/003',
        'speed': 'high', 'controller': 'dwc2'}


def state(address=3, pid=4775):
    return {'vendor_id': 1452, 'product_id': pid, 'address': address, 'speed': 'high',
            'active_configuration': 1, 'driver_bindings': [], 'configurations': []}


class IdentificationTests(unittest.TestCase):
    def test_known_unknown_and_shared_modes(self):
        db = load_database()
        self.assertEqual(identify(1452,4775,db)['mode'], 'apple_tv_usb')
        self.assertFalse(identify(1452,4775,db)['model_verified'])
        self.assertEqual(identify(1452,0x1227,db)['mode'], 'dfu')
        self.assertEqual(identify(1452,0x1281,db)['mode'], 'recovery')
        self.assertEqual(identify(1452,0xffff,db)['mode'], 'apple_unknown')
        self.assertEqual(identify(0x1234,0x1227,db)['mode'], 'unknown')
        self.assertTrue(identify(1452,4775,db)['source_urls'])
        self.assertEqual(identify(1452,4775,db)['identity_category'],'application')
        self.assertEqual(identify(1452,4775,db)['state_category'],'ambiguous')
        self.assertEqual(identify(1452,0x1227,db)['state_category'],'dfu')
        self.assertFalse(identify(1452,0x1227,db)['state_verified'])


class ParsingTests(unittest.TestCase):
    def test_observed_recovery_identity_with_alternate_interfaces(self):
        blob=bytes.fromhex((ROOT/'tests/fixtures/apple-recovery-1281-descriptors.hex').read_text())
        parsed=cached_descriptors(blob)
        self.assertEqual(parsed['device_descriptor']['product_id'],0x1281)
        interfaces=parsed['configurations'][0]['interfaces']
        self.assertEqual([(row['number'],row['alternate'],len(row['endpoints'])) for row in interfaces],
                         [(0,0,1),(1,0,0),(1,1,2)])
        self.assertEqual(identify(1452,0x1281,load_database())['mode'],'recovery')
        with self.assertRaises(DescriptorError):cached_descriptors(blob[:-1])

    def test_observed_descriptor_fields(self):
        parsed = cached_descriptors(DEVICE + CONFIG)
        config = parsed['configurations'][0]
        self.assertTrue(config['self_powered'])
        self.assertEqual(config['max_power_ma'], 2)
        self.assertTrue(config['interfaces'][0]['usbmux_compatible'])
        self.assertEqual(config['interfaces'][0]['endpoints'][1]['address'], 0x81)

    def test_every_truncation_is_rejected(self):
        for size in range(len(CONFIG)):
            with self.subTest(size=size), self.assertRaises(DescriptorError):
                configuration_descriptor(CONFIG[:size])
        for size in range(len(DEVICE + CONFIG)):
            with self.subTest(size=size), self.assertRaises(DescriptorError):
                cached_descriptors((DEVICE+CONFIG)[:size])

    def test_malformed_lengths_counts_endpoints_and_strings(self):
        for index, value in [(9,0),(18,1),(20,0x80),(13,3),(4,2)]:
            blob=bytearray(CONFIG);blob[index]=value
            with self.subTest(index=index), self.assertRaises(DescriptorError):
                configuration_descriptor(blob)
        with self.assertRaises(DescriptorError):
            string_descriptor(bytes((3,3,65)))
        self.assertEqual(string_descriptor(bytes((4,3,65,0))), 'A')
        self.assertEqual(string_descriptor(bytes.fromhex('040300d8')), '\ufffd')


class StateTests(unittest.TestCase):
    def test_disconnect_reconnect_address_and_identity_changes(self):
        watcher=StateObserver()
        self.assertEqual(watcher.update({'1-1':state()})[0]['event'], 'connected')
        self.assertEqual(watcher.update({'1-1':state()}), [])
        self.assertEqual(watcher.update({})[0]['event'], 'disconnected')
        event=watcher.update({'1-1':state(address=5)})[0]
        self.assertEqual(event['event'], 'reconnected')
        self.assertFalse(event['same_physical_device_verified'])
        event=watcher.update({'1-1':state(address=6,pid=0x1281)})[0]
        self.assertEqual(event['event'], 'state_changed')
        self.assertIn('product_id', event['changed'])

    def test_configuration_interface_and_driver_changes(self):
        watcher=StateObserver();before=state();watcher.update({'1-1':before})
        after=copy.deepcopy(before);after['active_configuration']=2
        after['driver_bindings']=[{'driver':'example'}];after['configurations']=[{'interfaces':[1]}]
        event=watcher.update({'1-1':after})[0]
        self.assertEqual(event['changed'], ['active_configuration','configurations','driver_bindings'])

    def test_read_errors_do_not_fabricate_disconnect_and_can_recover(self):
        watcher=StateObserver();watcher.update({'1-1':state()})
        errors={'1-1':{'status':'no_device'}}
        self.assertEqual(watcher.update({},errors)[0]['event'], 'device_error')
        self.assertEqual(watcher.update({},errors)[0]['event'], 'device_error')
        self.assertEqual(watcher.update({'1-1':state()})[0]['event'], 'diagnostics_recovered')
        self.assertEqual(watcher.update({}, {'*':{'status':'timeout'}}, False)[0]['event'], 'discovery_error')
        self.assertIn('1-1', watcher.states)
        self.assertEqual(watcher.update({'1-1':state()})[0]['event'], 'discovery_recovered')

    def test_rapid_cycles_and_address_reuse_have_generations_and_durations(self):
        watcher=StateObserver();watcher.update({'1-1':state()},now_ns=10)
        for generation in range(2,22):
            start=generation*100
            disappeared=watcher.update({},now_ns=start)[0]
            appeared=watcher.update({'1-1':state()},now_ns=start+3)[0]
            self.assertEqual(appeared['presence_generation'],generation)
            self.assertEqual(appeared['absence_duration_ns'],3)
            self.assertEqual(appeared['previous_address'],3)
            self.assertEqual(appeared['cause'],'unknown')
            self.assertGreater(disappeared['transition_duration_ns'],0)

    def test_same_error_instances_are_preserved(self):
        watcher=StateObserver();error={'*':{'status':'timeout','system_errno':110,'domain':'observer'}}
        for _ in range(3):
            self.assertEqual(watcher.update({},error,False)[0]['error']['system_errno'],110)


class SnapshotTests(unittest.TestCase):
    def fixture(self, directory):
        root=Path(directory);device=root/'1-1';device.mkdir()
        for name,text in {'devnum':'3','idVendor':'05ac','idProduct':'12a7','bConfigurationValue':'1'}.items():
            (device/name).write_text(text+'\n')
        (device/'descriptors').write_bytes(DEVICE+CONFIG)
        (device/'serial').write_text('UNIQUE_PRIVATE_SERIAL')
        interface=root/'1-1:1.0';interface.mkdir()
        for name,text in {'bInterfaceNumber':'00','bAlternateSetting':'0','bInterfaceClass':'ff',
                          'bInterfaceSubClass':'fe','bInterfaceProtocol':'02'}.items():
            (interface/name).write_text(text+'\n')
        return root

    def test_cached_snapshot_never_reads_serial(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.fixture(directory)
            original=Path.read_text
            def guarded(path,*args,**kwargs):
                self.assertNotEqual(path.name,'serial')
                return original(path,*args,**kwargs)
            with patch.object(Path,'read_text',guarded):
                snapshot=read_snapshot(INFO,root,load_database())
            self.assertEqual(snapshot['serial_policy'],'not_read')
            self.assertNotIn('UNIQUE_PRIVATE_SERIAL',json.dumps(snapshot))
            (root/'1-1/devnum').write_text('4')
            with self.assertRaises(ObservationError) as error:
                read_snapshot(INFO,root,load_database())
            self.assertEqual(error.exception.status,'again')
            (root/'1-1/devnum').unlink()
            with self.assertRaises(ObservationError) as error:
                read_snapshot(INFO,root,load_database())
            self.assertEqual(error.exception.status,'no_device')

    def test_real_polling_loop_uses_sdk_discovery_and_signal_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.fixture(directory);events=[]
            result=subprocess.CompletedProcess([],0,json.dumps({'devices':[INFO]}).encode(),b'')
            with patch('dwc2_diag.observer.subprocess.run',return_value=result) as run:
                totals=observe('/fake/bin',root,0.12,0.05,emit=events.append)
            self.assertGreaterEqual(totals['polls'],2)
            self.assertEqual(totals['connected'],1)
            self.assertEqual(totals['probes_ok'],0)
            self.assertTrue(all(call.args[0][0].endswith('usb-discover') for call in run.call_args_list))
            self.assertEqual(events[-1]['reason'],'duration')
            self.assertEqual([row['sequence'] for row in events],list(range(1,len(events)+1)))
            self.assertEqual(events[-1]['completion_status'],'complete')
            events=[];observe('/fake/bin',root,1,0.1,emit=events.append,stopped=lambda:True)
            self.assertEqual(events[-1]['reason'],'signal')

    def test_probe_recovers_from_timeout_without_device_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.fixture(directory);events=[];attempts=[0]
            def run(command,timeout):
                if str(command[0]).endswith('usb-discover'):
                    return {'devices':[INFO]}
                attempts[0]+=1
                if attempts[0]==1:raise ObservationError('timeout','probe','timeout')
                return INSPECTION
            with patch('dwc2_diag.observer.command_json',side_effect=run):
                totals=observe('/fake/bin',root,1.1,0.05,probe=True,emit=events.append)
            self.assertEqual(totals['probes_failed'],1)
            self.assertEqual(totals['probes_ok'],1)
            self.assertEqual([x['event'] for x in events if x['event'].startswith('descriptor_probe')],
                             ['descriptor_probe_error','descriptor_probe_ok'])

    def test_retry_exhaustion_is_bounded_visible_and_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.fixture(directory);events=[];attempts=[]
            def run(command,timeout):
                if str(command[0]).endswith('usb-discover'):return {'devices':[INFO]}
                attempts.append(command)
                raise ObservationError('protocol','control','failed',71,1)
            with patch('dwc2_diag.observer.command_json',side_effect=run):
                observe('/fake/bin',root,.35,.05,probe=True,emit=events.append,probe_attempts=2,retry_delay=.05)
            self.assertEqual(len(attempts),2)
            self.assertEqual(events[-1]['completion_status'],'incomplete')
            failures=[row for row in events if row['event']=='descriptor_probe_error']
            self.assertEqual([row['attempt'] for row in failures],[1,2])
            self.assertEqual(failures[0]['error']['system_errno'],71)
            self.assertEqual(failures[0]['error']['domain'],'device')
            self.assertEqual(sum(row['event']=='descriptor_probe_exhausted' for row in events),1)

    def test_stale_path_recovery_rediscovery_and_new_initialization(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.fixture(directory);events=[];polls=[0];paths=[]
            def run(command,timeout):
                if str(command[0]).endswith('usb-discover'):
                    polls[0]+=1
                    if polls[0]==2:return {'devices':[]}
                    if polls[0]>2:
                        (root/'1-1/devnum').write_text('4')
                        return {'devices':[{**INFO,'address':4,'path':'/dev/bus/usb/001/004'}]}
                    return {'devices':[INFO]}
                paths.append(command[2])
                if len(paths)==1:raise ObservationError('no_device','open','stale path',19)
                return {**INSPECTION,'device':{**INSPECTION['device'],'address':4}}
            with patch('dwc2_diag.observer.command_json',side_effect=run):
                observe('/fake/bin',root,1,.05,probe=True,emit=events.append,stop_after_reconnect=True)
            self.assertEqual(paths,['/dev/bus/usb/001/003','/dev/bus/usb/001/004'])
            self.assertEqual(events[-1]['reason'],'reconnected')
            self.assertEqual(events[-1]['completion_status'],'complete')

    def test_bounded_observer_can_stop_after_a_recovered_reconnect(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.fixture(directory); events=[]; samples=[0]
            def run(command,timeout):
                samples[0]+=1
                if samples[0]==2:return {'devices':[]}
                if samples[0]>=3:
                    (root/'1-1/devnum').write_text('4')
                    return {'devices':[{**INFO,'address':4,'path':'/dev/bus/usb/001/004'}]}
                return {'devices':[INFO]}
            with patch('dwc2_diag.observer.command_json',side_effect=run):
                totals=observe('/fake/bin',root,1,.05,emit=events.append,stop_after_reconnect=True)
            self.assertEqual(totals['polls'],3)
            self.assertEqual(events[-1]['reason'],'reconnected')

    def test_subprocess_timeout_and_incomplete_output(self):
        with patch('dwc2_diag.observer.subprocess.run',side_effect=subprocess.TimeoutExpired([],1)):
            with self.assertRaises(ObservationError) as error:command_json(['example'],1)
            self.assertEqual(error.exception.status,'timeout')
        payload=json.dumps({'error':{'status':'protocol','operation':'control','errno':71}}).encode()
        with patch('dwc2_diag.observer.subprocess.run',return_value=subprocess.CompletedProcess([],1,payload,b'')):
            with self.assertRaises(ObservationError) as error:command_json(['example'],1)
            self.assertEqual(error.exception.system_errno,71)
        for data in (b'',b'[]',b'{'):
            with patch('dwc2_diag.observer.subprocess.run',return_value=subprocess.CompletedProcess([],0,data,b'')):
                with self.assertRaises(ObservationError):command_json(['example'],1)
        with patch('dwc2_diag.observer.subprocess.run',return_value=subprocess.CompletedProcess([],-9,b'',b'')):
            with self.assertRaises(ObservationError) as error:command_json(['example'],1)
            self.assertEqual(error.exception.returncode,-9)

    def test_cli_reports_incomplete_observation_with_nonzero_exit(self):
        result=subprocess.run([sys.executable,str(ROOT/'tools/usb-observe'),'--bin','/nonexistent',
                               '--duration','.06','--interval','.05'],capture_output=True,text=True,timeout=3)
        self.assertEqual(result.returncode,1)
        rows=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(rows[-1]['completion_status'],'incomplete')
        self.assertEqual(rows[1]['error']['domain'],'observer')

    def test_kernel_failures_do_not_copy_serials_or_raw_text(self):
        records=kernel_errors('[1] usb 1-1: device descriptor read/64, error -71\n'
                              '[2] usb 1-1: SerialNumber: UNIQUE_PRIVATE_SERIAL\n'
                              '[3] usb usb1-port1: unable to enumerate USB device\n')
        self.assertEqual(len(records),2)
        self.assertEqual(records[0]['kernel_errno'],-71)
        self.assertNotIn('UNIQUE_PRIVATE_SERIAL',json.dumps(records))


if __name__=='__main__':
    unittest.main()
