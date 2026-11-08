"""Raspberry Pi camera transmitter, with real WFB encryption/FEC over an IP carrier.

IP mode works through managed Wi-Fi adapters and does not control their PHY MCS.
For direct monitor/injection use radio_launcher plus adaptive_server --mode radio.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import urllib.request
from .paths import PROJECT_ROOT,DEFAULT_CONFIG,module_command,child_env
from .config import validate
from .processes import stop_children


def build_commands(args,drone):
    binary=args.binary_dir.resolve();key=str(args.keys.resolve()/'drone.key');link=str(drone['link_id'])
    if args.mode=='radio':
        return [('radio',module_command('radio_launcher','--role','air','--drone',args.drone,'--config',args.config.resolve(),'--interface',args.interface,'--keys',args.keys.resolve(),'--binary-dir',binary)),
                ('camera',module_command('adaptive_server','--mode','radio','--port','8090','--video-port','5600','--radio-control-port','9001','--wfb-command',binary/'wfb_tx_cmd'))]
    return [
      ('carrier',module_command('udp_link','--role','server','--bind',args.bind,'--peer',args.peer,'--port',args.network_port,'--local-input','9010','--local-output','9002','--status',args.log_dir/'carrier.json')),
      ('wfb-rx',[str(binary/'wfb_rx'),'-a','9002','-u','5801','-K',key,'-i',link,'-p','1','-T','200','-R','4194304','-s','4194304']),
      ('wfb-tx',[str(binary/'wfb_tx'),'-D','9010','-u','5600','-C','9001','-K',key,'-i',link,'-p','0','-M','0','-k','8','-n','12','-T','5','ip-carrier']),
      ('feedback',module_command('feedback','--udp-listen','5801','--air-api','http://127.0.0.1:8090')),
      ('camera',module_command('adaptive_server','--mode','ip','--port','8090','--video-port','5600','--radio-control-port','9001','--wfb-command',binary/'wfb_tx_cmd'))]


def parser():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mode',choices=('ip','radio'),default='ip')
    ap.add_argument('--interface',help='dedicated external monitor/injection radio')
    ap.add_argument('--bind',help='Pi USB Wi-Fi IPv4 address')
    ap.add_argument('--peer',help='allowed NSU USB Wi-Fi IPv4 address')
    ap.add_argument('--network-port',type=int,default=17030)
    ap.add_argument('--config',type=Path,default=DEFAULT_CONFIG);ap.add_argument('--drone',default='drone1')
    ap.add_argument('--binary-dir',type=Path,default=PROJECT_ROOT/'vendor/skvoz-wfb-ng')
    ap.add_argument('--keys',type=Path,default=PROJECT_ROOT/'keys/drone1')
    ap.add_argument('--log-dir',type=Path,default=PROJECT_ROOT/'results/air')
    ap.add_argument('--seconds',type=float,default=0);ap.add_argument('--plan',action='store_true')
    return ap

def main():
    ap=parser();args=ap.parse_args()
    if args.mode=='radio':
        if not args.interface:ap.error('Radio mode requires --interface')
        if not args.plan and os.geteuid()!=0:ap.error('Radio setup requires root')
    elif not args.bind or not args.peer:ap.error('IP mode requires --bind and --peer')
    cfg=validate(json.loads(args.config.read_text()))
    drone=next((d for d in cfg['drones'] if d['id']==args.drone),None)
    if not drone:ap.error('Unknown drone')
    if args.plan:print(json.dumps(build_commands(args,drone),indent=2));return
    for name in ('wfb_rx','wfb_tx','wfb_tx_cmd'):
        if not (args.binary_dir/name).is_file():ap.error('Missing '+name)
    if not (args.keys/'drone.key').is_file():ap.error('Matching drone.key is required')
    args.log_dir.mkdir(parents=True,exist_ok=True);children=[];logs=[];stop=threading.Event()
    signal.signal(signal.SIGTERM,lambda *_:stop.set())
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}));start=time.monotonic()
    try:
        for name,command in build_commands(args,drone):
            log=(args.log_dir/(name+'.log')).open('a');logs.append(log)
            children.append(subprocess.Popen(command,env=child_env(),stdout=log,stderr=log,start_new_session=True))
            if name in ('wfb-tx','radio'):
                deadline=time.monotonic()+12
                while time.monotonic()<deadline:
                    if children[-1].poll() is not None:raise RuntimeError('WFB endpoint exited')
                    try:
                        response=subprocess.run([str(args.binary_dir/'wfb_tx_cmd'),'9001','get_radio'],capture_output=True,text=True,timeout=1)
                        if response.returncode==0 and 'mcs_index' in response.stdout:break
                    except subprocess.TimeoutExpired:pass
                    time.sleep(.2)
                else:raise RuntimeError('WFB TX control startup timeout')
        deadline=time.monotonic()+15
        while time.monotonic()<deadline and not stop.is_set():
            if any(p.poll() is not None for p in children):raise RuntimeError('Transmitter child exited; see '+str(args.log_dir))
            try:
                with op.open('http://127.0.0.1:8090/status',timeout=.5) as response:state=json.load(response)
                if state['running'] and state['frames']>0:break
            except (OSError,ValueError):pass
            time.sleep(.1)
        else:raise RuntimeError('Camera startup timeout')
        print(json.dumps(dict(event='air_ready',mode=args.mode,bind=args.bind,peer=args.peer)),flush=True)
        while not stop.wait(.2):
            if any(p.poll() is not None for p in children):raise RuntimeError('Transmitter subprocess stopped')
            if args.seconds and time.monotonic()-start>=args.seconds:break
    except KeyboardInterrupt:pass
    except (OSError,RuntimeError) as exc:ap.exit(1,str(exc)+'\n')
    finally:
        stop_children(children)
        for log in logs:log.close()
if __name__=='__main__':main()
