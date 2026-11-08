#!/usr/bin/env python3
"""Adaptive camera, RTP and WFB-ng control. Loopback API, reachable over SSH only."""
import argparse
from dataclasses import asdict
import json
import signal
import subprocess
import threading
import time
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
from .http_api import Handler as PreviewHandler
from .adaptive_camera import AdaptiveCamera
from .link_core import PROFILES, ALL_PROFILES, Metric, Policy

PAGE='<!doctype html><html lang="ru"><meta charset="utf-8"><title>БВС · камера</title><h1>БВС · передатчик камеры</h1><p>Видео отправляется на НСУ. Здесь работает только управление передатчиком.</p><p><a href="/status">JSON состояния</a></p><p>API: POST /profile, /auto, /feedback.</p></html>'

class Radio:
    def __init__(self, binary, port):self.binary=binary;self.port=port;self.applied=None
    def run(self,*args):
        result=subprocess.run([self.binary,str(self.port),*args],capture_output=True,text=True,timeout=5)
        if result.returncode:raise RuntimeError(result.stderr.strip() or 'wfb_tx_cmd failed')
        return result.stdout
    def apply(self,p):
        self.run('set_fec_timeout','-T','5')
        self.run('set_fec','-k',str(p.fec_k),'-n',str(p.fec_n))
        self.run('set_radio','-B','20','-G','long','-S','0','-L','0','-M',str(p.mcs))
        values=dict(line.split('=',1) for line in (self.run('get_fec')+self.run('get_radio')).splitlines() if '=' in line)
        if (int(values['k']),int(values['n']),int(values['mcs_index']))!=(p.fec_k,p.fec_n,p.mcs):
            raise RuntimeError('WFB-ng radio readback mismatch')
        self.applied=p

class Engine:
    def __init__(self,camera,radio,mode,simulation_state=None):
        self.camera=camera;self.radio=radio;self.mode=mode;self.policy=Policy();self.simulation_state=simulation_state
        self.lock=threading.RLock();self.automatic=True;self.error=None;self.current=None
        self.last_metric=None;self.transitions=[];self.closed=False;self.grace_until=0
    def apply(self,p,reason):
        previous=self.current
        try:
            # Pause encoder while FEC and modulation are changed, then issue a new keyframe/session.
            with self.camera.change_lock:self.camera._stop_process()
            if self.radio:self.radio.apply(p)
            self.camera.set_profile(p.name)
            self.current=p;self.error=None;self.grace_until=time.monotonic()+2.5
            self.transitions.append(dict(at=time.time(),profile=p.name,reason=reason))
            self.transitions=self.transitions[-30:]
            print(json.dumps(dict(event='profile_applied',mode=self.mode,profile=p.name,mcs=p.mcs,codec=p.codec,fec_k=p.fec_k,fec_n=p.fec_n,reason=reason)),flush=True)
        except Exception as exc:
            self.error=str(exc)
            if previous:
                try:
                    if self.radio:self.radio.apply(previous)
                    self.camera.set_profile(previous.name);self.current=previous
                except Exception as restore:
                    self.error+='; rollback failed: '+str(restore)
            raise
    def observe(self,m):
        with self.lock:
            if m.source=='wfb-ip' and self.mode!='ip':raise ValueError('IP-carrier metrics require ip mode')
            if m.source=='simulation' and self.mode!='emulation':raise ValueError('simulation feedback requires emulation mode')
            self.last_metric=asdict(m)
            if time.monotonic()<self.grace_until:
                self.policy.last_sample=time.monotonic()
                return
            if not self.automatic:
                self.policy.last_sample=time.monotonic()
                return
            old=self.policy.index
            profile=self.policy.sample(m)
            if profile and self.automatic:
                try:self.apply(profile,self.policy.reason)
                except Exception:self.policy.index=old;raise
    def tick(self):
        while not self.closed:
            with self.lock:
                if self.automatic and time.monotonic()>=self.grace_until:
                    old=self.policy.index;p=self.policy.tick()
                    if p:
                        try:self.apply(p,self.policy.reason)
                        except Exception:self.policy.index=old
            time.sleep(.3)
    def manual(self,name):
        p=next((p for p in ALL_PROFILES if p.name==name),None)
        if p is None:raise ValueError('unknown profile')
        with self.lock:
            self.apply(p,'manual');self.automatic=False;self.policy.index=PROFILES.index(p) if p in PROFILES else 3
    def status(self):
        with self.lock:
            age=None if self.policy.last_sample is None else round(time.monotonic()-self.policy.last_sample,2)
            result=self.camera.status()
            result.update(mode=self.mode,automatic=self.automatic,feedback_age_s=age,metrics=self.last_metric,
                          reason=self.policy.reason,control_error=self.error,transitions=self.transitions,
                          radio_controlled=self.radio is not None,phy_controlled=self.mode=='radio',resource_ceiling=PROFILES[self.policy.resource_cap].name)
            return result

class Handler(PreviewHandler):
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/':return self.reply(200,PAGE,'text/html; charset=utf-8')
        if path=='/status':return self.reply(200,json.dumps(self.server.engine.status()),'application/json')
        return super().do_GET()
    def do_POST(self):
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=8192:raise ValueError('invalid request size')
            data=json.loads(self.rfile.read(size));path=urlsplit(self.path).path
            if path=='/simulation':
                engine=self.server.engine
                if engine.mode!='emulation' or engine.simulation_state is None:raise ValueError('Simulation controls disabled')
                phase=data['phase']
                if phase not in ('good','weak','bad','feedback-off'):raise ValueError('Unknown phase')
                tmp=engine.simulation_state.with_suffix('.tmp');tmp.write_text(json.dumps(dict(phase=phase)));tmp.replace(engine.simulation_state)
            elif path=='/feedback':
                m=Metric(**{key:data[key] for key in Metric.__dataclass_fields__ if key in data})
                if type(m.active) is not bool:raise ValueError('active must be boolean')
                self.server.engine.observe(m.validate())
            elif path=='/profile':self.server.engine.manual(data['profile'])
            elif path=='/auto':
                if type(data.get('enabled')) is not bool:raise ValueError('enabled must be boolean')
                with self.server.engine.lock:
                    self.server.engine.automatic=data['enabled'];self.server.engine.policy.good=0
                    self.server.engine.policy.bad=0
                    if data['enabled'] and self.server.engine.current not in PROFILES:
                        self.server.engine.apply(PROFILES[3],'return to automatic profiles')
                    if self.server.engine.current:
                        self.server.engine.policy.index=PROFILES.index(self.server.engine.current)
            else:return self.reply(404,'Not found','text/plain')
            return self.reply(200,json.dumps(self.server.engine.status()),'application/json')
        except (ValueError,TypeError,KeyError) as exc:return self.reply(400,str(exc),'text/plain')
        except Exception as exc:return self.reply(503,str(exc),'text/plain')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port',type=int,default=8090);ap.add_argument('--video-port',type=int,default=5600)
    ap.add_argument('--mode',choices=['camera-only','emulation','radio','ip'],default='camera-only')
    ap.add_argument('--radio-control-port',type=int,default=9001)
    ap.add_argument('--wfb-command',default='wfb_tx_cmd')
    ap.add_argument('--simulation-state',type=Path)
    ap.add_argument('--manual',action='store_true',help='disable automatic policy (diagnostics only)')
    args=ap.parse_args()
    camera=AdaptiveCamera(args.video_port)
    radio=None if args.mode=='camera-only' else Radio(args.wfb_command,args.radio_control_port)
    engine=Engine(camera,radio,args.mode,args.simulation_state)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);server.daemon_threads=True
    server.camera=camera;server.engine=engine
    signal.signal(signal.SIGTERM,lambda *_:threading.Thread(target=server.shutdown,daemon=True).start())
    try:
        engine.apply(PROFILES[1],'startup');engine.automatic=not args.manual
        threading.Thread(target=engine.tick,daemon=True).start()
        server.serve_forever(.25)
    except KeyboardInterrupt:pass
    finally:engine.closed=True;camera.close();server.server_close()
if __name__=='__main__':main()
