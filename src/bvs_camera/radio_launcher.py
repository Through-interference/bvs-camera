#!/usr/bin/env python3
"""Prepare a dedicated compatible radio and launch one WFB-ng FDMA endpoint."""
import argparse,json,os,re,signal,subprocess,sys
from pathlib import Path
from .paths import DEFAULT_CONFIG,module_command,child_env
from .config import validate

def is_usb_interface(interface):
    return any(part.startswith('usb') for part in Path('/sys/class/net',interface,'device').resolve().parts)

def inspect_interface(interface):
    if (interface=='wlan0' and not is_usb_interface(interface)) or interface.startswith('REPLACE_'):
        raise ValueError('Select a dedicated external radio, never management wlan0')
    if not re.fullmatch('[A-Za-z0-9_.-]+',interface):raise ValueError('Invalid interface')
    addresses=json.loads(subprocess.check_output(['ip','-j','address','show','dev',interface],text=True))
    if any(a.get('scope')=='global' for dev in addresses for a in dev.get('addr_info',[])):
        raise ValueError('Interface has a network address; SSH/management interfaces must not be reconfigured')
    driver=Path('/sys/class/net',interface,'device/driver').resolve().name
    if not any(s in driver for s in ('8812au','88XXau','88xxau','8812eu','88x2eu')):
        raise ValueError('Unverified WFB driver: '+driver)
    info=subprocess.check_output(['iw','dev',interface,'info'],text=True)
    m=re.search(r'^\s*type (\S+)',info,re.M)
    if not m:raise ValueError('Cannot identify interface type')
    return m[1]

def inspect_physical_interfaces(interfaces,sysfs_root='/sys/class/net'):
    seen=set()
    for interface in interfaces:
        inspect_interface(interface)
        try:phy=Path(sysfs_root,interface,'phy80211').resolve(strict=True)
        except OSError as exc:raise ValueError('Cannot identify physical radio: '+interface) from exc
        if phy in seen:raise ValueError('FDMA requires independent physical radios: '+interface)
        seen.add(phy)
    return seen

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--role',choices=('air',),default='air')
    ap.add_argument('--drone',default='drone1');ap.add_argument('--config',default=str(DEFAULT_CONFIG))
    ap.add_argument('--interface',required=True);ap.add_argument('--binary-dir',required=True);ap.add_argument('--keys',required=True)
    args=ap.parse_args();cfg=validate(json.loads(Path(args.config).read_text()))
    d=next((d for d in cfg['drones'] if d['id']==args.drone),None)
    if d is None:ap.error('Unknown drone')
    previous=inspect_interface(args.interface)
    if os.geteuid()!=0:ap.error('Radio setup requires root')
    key=Path(args.keys)/'drone.key';binary=Path(args.binary_dir)
    if not key.is_file():ap.error('Matching drone.key is missing')
    for name in ('wfb_tx','wfb_rx'):
        if not (binary/name).is_file():ap.error('Missing '+name)
    children=[]
    signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        subprocess.run(['ip','link','set',args.interface,'down'],check=True)
        subprocess.run(['iw','dev',args.interface,'set','type','monitor'],check=True)
        subprocess.run(['ip','link','set',args.interface,'up'],check=True)
        subprocess.run(['iw','dev',args.interface,'set','freq',str(d['frequency_mhz']),'HT20'],check=True)
        children.append(subprocess.Popen([str(binary/'wfb_tx'),'-R','4194304','-s','4194304','-K',str(key),'-i',str(d['link_id']),'-p','0','-u','5600','-C','9001','-B','20','-G','long','-M','0','-S','0','-L','0','-k','8','-n','12','-T','5',args.interface]))
        children.append(subprocess.Popen([str(binary/'wfb_rx'),'-K',str(key),'-i',str(d['link_id']),'-p','1','-c','127.0.0.1','-u','5801','-T','200',args.interface]))
        children.append(subprocess.Popen(module_command('feedback','--udp-listen','5801','--air-api','http://127.0.0.1:8090'),env=child_env()))
        import time
        while all(p.poll() is None for p in children):time.sleep(.3)
        raise RuntimeError('Air radio endpoint stopped')
    except KeyboardInterrupt:pass
    finally:
        for p in children:
            if p.poll() is None:p.terminate()
        for p in children:
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        subprocess.run(['ip','link','set',args.interface,'down'])
        subprocess.run(['iw','dev',args.interface,'set','type',previous])
        subprocess.run(['ip','link','set',args.interface,'up'])
if __name__=='__main__':main()
