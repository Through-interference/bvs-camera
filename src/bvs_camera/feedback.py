"""Forward decrypted NSU feedback to the local adaptive controller."""
import argparse,json,select,socket,sys,urllib.request
from dataclasses import asdict
from .link_core import Metric

def parse_metric(payload):
    data=json.loads(payload)
    if not isinstance(data,dict):raise ValueError('Expected a metric object')
    return Metric(**data).validate()

def receive_latest(sock):
    payload=sock.recv(8192)
    # Profile changes can block HTTP for several seconds. Do not replay the
    # accumulated UDP measurements as if they described the current channel.
    while select.select([sock],[],[],0)[0]:
        payload=sock.recv(8192)
    return parse_metric(payload)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--udp-listen',type=int,default=5801)
    ap.add_argument('--air-api',default='http://127.0.0.1:8090')
    args=ap.parse_args();op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.bind(('127.0.0.1',args.udp_listen))
        while True:
            try:
                metric=receive_latest(sock)
                request=urllib.request.Request(args.air_api+'/feedback',data=json.dumps(asdict(metric)).encode(),headers={'Content-Type':'application/json'})
                with op.open(request,timeout=15) as response:response.read()
            except (OSError,ValueError,TypeError) as exc:print('Feedback rejected/unavailable:',exc,file=sys.stderr,flush=True)
if __name__=='__main__':main()
