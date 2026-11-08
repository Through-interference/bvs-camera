"""Adaptive link policy and WFB-ng telemetry normalization (no hardware dependencies)."""
from dataclasses import dataclass, asdict
import math
import time

@dataclass(frozen=True)
class Profile:
    name: str
    mcs: int
    fec_k: int
    fec_n: int
    codec: str
    width: int
    height: int
    fps: int
    bitrate: int
    quality: int = 70

# Starting points for calibration, NOT measured capacities or RSSI thresholds.
PROFILES = [
    Profile('critical', 0, 4, 8, 'mjpeg', 320, 240, 5, 0, 30),
    Profile('low', 0, 8, 12, 'h264', 640, 480, 30, 800_000),
    Profile('medium', 1, 8, 12, 'h264', 1280, 720, 45, 2_500_000),
    Profile('high', 2, 8, 10, 'h264', 1280, 720, 60, 5_000_000),
]

# Manual capture experiment; excluded from the four-step automatic radio policy.
ALL_PROFILES=PROFILES+[Profile('fast',2,8,10,'h264',640,480,200,5_000_000)]

@dataclass
class Metric:
    rssi: float | None
    snr: float | None
    pre_loss: float
    post_loss: float
    active: bool
    source: str = 'wfb'
    receiver_overloaded: bool = False
    decoder_fps: float | None = None
    input_fps: float | None = None
    rx_queue_ms: float | None = None
    receiver_cpu_percent: float | None = None
    receiver_temp_c: float | None = None

    def validate(self):
        if type(self.active) is not bool:raise ValueError('active flag must be boolean')
        for v in (self.pre_loss, self.post_loss):
            if not math.isfinite(v) or not 0 <= v <= 1:
                raise ValueError('loss must be a finite fraction in [0,1]')
        for v, lower, upper in [(self.rssi, -127, 0), (self.snr, -40, 80)]:
            if v is not None and (not math.isfinite(v) or not lower <= v <= upper):
                raise ValueError('invalid radio measurement')
        if type(self.receiver_overloaded) is not bool:raise ValueError('overload flag must be boolean')
        for key,upper in [('decoder_fps',1000),('input_fps',1000),('rx_queue_ms',60000),('receiver_cpu_percent',100),('receiver_temp_c',150)]:
            v=getattr(self,key)
            if v is not None and (not math.isfinite(v) or not 0<=v<=upper):raise ValueError('invalid '+key)
        if self.source not in ('wfb', 'simulation', 'wfb-ip'):
            raise ValueError('unknown telemetry source')
        return self


class Policy:
    def __init__(self, timeout=3., dwell=3., upgrade_samples=5):
        self.index=1
        self.timeout=timeout;self.dwell=dwell;self.upgrade_samples=upgrade_samples
        self.last_sample=None;self.last_change=None;self.smooth=None
        self.good=0;self.bad=0;self.reason='startup'
        self.resource_cap=3;self.resource_bad=0;self.resource_good=0;self.resource_hold_until=0
    def sample(self, metric, now=None):
        metric.validate();now=time.monotonic() if now is None else now
        self.last_sample=now
        if not metric.active:
            return self._change(0,now,'no video packets')
        if metric.receiver_overloaded:
            self.resource_bad+=1;self.resource_good=0
            if self.resource_bad>=3:
                self.resource_cap=min(self.resource_cap,max(1,self.index-1))
                self.resource_hold_until=now+20
        else:
            self.resource_bad=0;self.resource_good+=1
            if self.resource_cap<3 and self.resource_good>=10 and now>=self.resource_hold_until:
                self.resource_cap+=1;self.resource_good=0;self.resource_hold_until=now+20
        alpha=.45
        if self.smooth is None: self.smooth=asdict(metric)
        else:
            for key in ('pre_loss','post_loss'):
                self.smooth[key]=alpha*getattr(metric,key)+(1-alpha)*self.smooth[key]
            for key in ('rssi','snr'):
                v=getattr(metric,key);old=self.smooth[key]
                self.smooth[key]=v if v is None or old is None else 10*math.log10(alpha*10**(v/10)+(1-alpha)*10**(old/10))
        rssi,snr=self.smooth['rssi'],self.smooth['snr']
        target=3
        if rssi is not None: target=min(target,3 if rssi>=-63 else 2 if rssi>=-75 else 1 if rssi>=-85 else 0)
        if snr is not None: target=min(target,3 if snr>=22 else 2 if snr>=12 else 1 if snr>=4 else 0)
        loss=self.smooth['pre_loss'];post=self.smooth['post_loss']
        target=min(target,3 if loss<.02 else 2 if loss<.08 else 1 if loss<.2 else 0)
        if post>.02: target=min(target,1)
        if metric.post_loss>.10: return self._change(0,now,'severe unrecovered loss')
        target=min(target,self.resource_cap)
        if target<self.index:
            self.bad+=1;self.good=0
            if self.bad>=2 and self._due(now):return self._change(target,now,'receiver overloaded' if target==self.resource_cap and self.resource_cap<self.index else 'link degraded')
        elif target>self.index:
            self.good+=1;self.bad=0
            if self.good>=self.upgrade_samples and self._due(now):return self._change(self.index+1,now,'sustained recovery')
        else:self.good=self.bad=0
        return None
    def tick(self, now=None):
        now=time.monotonic() if now is None else now
        if self.last_sample is None or now-self.last_sample>self.timeout:
            self.smooth=None
            return self._change(0,now,'feedback stale')
        return None
    def _due(self,now):return self.last_change is None or now-self.last_change>=self.dwell
    def _change(self,target,now,reason):
        self.good=self.bad=0;self.reason=reason
        if target==self.index:return None
        self.index=target;self.last_change=now
        return PROFILES[target]
