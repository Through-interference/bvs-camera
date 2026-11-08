"""Hardware encode once and publish complete RTP packets; no on-air preview decoder."""
import socket
import subprocess
import threading
import time
from .camera_base import Camera
from .link_core import ALL_PROFILES as PROFILES

class AdaptiveCamera(Camera):
    def __init__(self, video_port=5600):
        super().__init__()
        import gi
        gi.require_version('Gst','1.0')
        from gi.repository import Gst
        Gst.init(None)
        self.Gst=Gst;self.pipeline=None;self.capture=None
        self.video_port=video_port;self.applied=None;self.packet_count=0;self.socket_drops=0
        self.ready=threading.Event()
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,4*1024*1024)
        self.sock.setblocking(False)

    def status(self):
        with self.condition:
            p=self.applied or PROFILES[1]
            return dict(profile=p.name,width=p.width,height=p.height,fps=p.fps,
                        codec=p.codec,bitrate=p.bitrate,mcs=p.mcs,fec_k=p.fec_k,fec_n=p.fec_n,
                        frames=self.frames,frame_kind='rtp_tx',rtp_packets=self.packet_count,tx_socket_drops=self.socket_drops,
                        frame_age_s=round(time.monotonic()-self.last_frame,2) if self.last_frame else None,
                        running=self.process is not None and self.process.poll() is None,
                        error=self.error,recent_camera_logs=list(self.logs))

    def _stop_process(self):
        with self.condition:self.generation+=1
        if self.capture and self.capture.poll() is None:
            self.capture.terminate()
            try:self.capture.wait(timeout=4)
            except subprocess.TimeoutExpired:self.capture.kill();self.capture.wait(timeout=4)
        if self.pipeline:
            self.pipeline.set_state(self.Gst.State.NULL)
            self.pipeline=None
        if self.capture and self.capture.stdout:self.capture.stdout.close()
        self.capture=None;self.process=None

    def set_profile(self, profile):
        p=next((p for p in PROFILES if p.name==profile),None)
        if p is None:raise ValueError('Unknown profile')
        with self.change_lock:
            if self.closing:raise RuntimeError('closing')
            self._stop_process();self.ready.clear()
            cmd=['rpicam-vid','--nopreview','--timeout','0','--verbose','0','--width',str(p.width),
                 '--height',str(p.height),'--framerate',str(p.fps),'--codec',p.codec,
                 '--buffer-count','4','--denoise','cdn_off','--flush','-o','-']
            if p.codec=='h264':cmd+=['--profile','baseline','--level','4.2','--bitrate',str(p.bitrate),'--intra',str(max(1,p.fps//2)),'--inline']
            else:cmd+=['--quality',str(p.quality)]
            cap=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
            parse_pay=('h264parse ! video/x-h264,stream-format=byte-stream,alignment=au ! '
                       'rtph264pay pt=96 config-interval=-1 mtu=1200') if p.codec=='h264' else 'jpegparse ! rtpjpegpay pt=26 mtu=1200'
            try:
                pipeline=self.Gst.parse_launch(f'fdsrc fd={cap.stdout.fileno()} do-timestamp=true ! {parse_pay} ! appsink name=rtp emit-signals=true sync=false max-buffers=16 drop=false')
                sink=pipeline.get_by_name('rtp')
                with self.condition:
                    self.capture=cap;self.process=cap;self.pipeline=pipeline;self.applied=p;self.profile=p.name
                    self.last_frame=None;self.error=None;self.logs.clear();generation=self.generation
                def on_packet(sink):
                    sample=sink.emit('pull-sample')
                    if sample is None:return self.Gst.FlowReturn.EOS
                    buf=sample.get_buffer();packet=buf.extract_dup(0,buf.get_size())
                    with self.condition:
                        if generation!=self.generation or self.closing:return self.Gst.FlowReturn.FLUSHING
                        try:self.sock.sendto(packet,('127.0.0.1',self.video_port))
                        except OSError:self.socket_drops+=1
                        self.packet_count+=1
                        if len(packet)>1 and packet[1]&128:
                            self.frames+=1;self.last_frame=time.monotonic();self.condition.notify_all()
                    self.ready.set()
                    return self.Gst.FlowReturn.OK
                sink.connect('new-sample',on_packet)
                threading.Thread(target=self._read_errors,args=(cap,generation),daemon=True).start()
                pipeline.set_state(self.Gst.State.PLAYING)
                if not self.ready.wait(timeout=10):
                    error=pipeline.get_bus().pop_filtered(self.Gst.MessageType.ERROR)
                    detail=str(error.parse_error()) if error else ' | '.join(self.logs)
                    raise RuntimeError('Camera did not produce RTP packets: '+detail)
            except Exception:
                self._stop_process();raise

    def close(self):
        super().close();self.sock.close()
