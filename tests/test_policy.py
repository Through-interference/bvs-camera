import math,unittest
from bvs_camera.link_core import Metric,Policy

class PolicyTests(unittest.TestCase):
 def metric(self,rssi=-55,pre=0,post=0,active=True,snr=30):return Metric(rssi,snr,pre,post,active)
 def test_recovery_requires_multiple_good_samples(self):
  p=Policy(dwell=0)
  for i in range(4):self.assertIsNone(p.sample(self.metric(),i))
  self.assertEqual(p.sample(self.metric(),4).name,'medium')
  for i in range(5,9):self.assertIsNone(p.sample(self.metric(),i))
  self.assertEqual(p.sample(self.metric(),9).name,'high')
 def test_missing_feedback_enters_safe_profile_once(self):
  p=Policy();p.sample(self.metric(),0)
  self.assertEqual(p.tick(4).name,'critical');self.assertIsNone(p.tick(5))
 def test_severe_packet_loss_overrides_strong_signal(self):
  p=Policy();self.assertEqual(p.sample(self.metric(post=.3),0).name,'critical')
 def test_no_packets_is_not_perfect_link(self):
  p=Policy();self.assertEqual(p.sample(self.metric(active=False),0).name,'critical')
 def test_hysteresis_does_not_flap(self):
  p=Policy(dwell=3)
  names=[]
  for i in range(30):
   x=p.sample(self.metric(rssi=-73 if i%2 else -77),i*.1)
   if x:names.append(x.name)
  self.assertLessEqual(len(names),1)
 def test_nan_rejected(self):
  with self.assertRaises(ValueError):self.metric(pre=float('nan')).validate()
 def test_linear_power_averaging(self):
  p=Policy();p.sample(self.metric(rssi=-60),0);p.sample(self.metric(rssi=-80),1)
  expected=10*math.log10(.45*10**(-8)+.55*10**(-6))
  self.assertAlmostEqual(p.smooth['rssi'],expected)
class EngineTests(unittest.TestCase):
 def fake(self):
  from bvs_camera.adaptive_server import Engine
  import threading
  class Camera:
   def __init__(self):self.change_lock=threading.Lock();self.fail=None;self.profile=None
   def _stop_process(self):pass
   def set_profile(self,name):
    if name==self.fail:raise RuntimeError('encoder failed')
    self.profile=name
   def status(self):return dict(profile=self.profile)
  class Radio:
   def apply(self,p):self.profile=p.name
  cam=Camera();radio=Radio();engine=Engine(cam,radio,'emulation')
  from bvs_camera.link_core import PROFILES
  engine.apply(PROFILES[1],'startup');return engine,cam,radio
 def test_encoder_failure_restores_previous_radio_and_codec(self):
  from bvs_camera.link_core import PROFILES
  e,c,r=self.fake();c.fail='high'
  with self.assertRaises(RuntimeError):e.apply(PROFILES[3],'test')
  self.assertEqual(c.profile,'low');self.assertEqual(r.profile,'low');self.assertEqual(e.current.name,'low')
 def test_manual_profile_not_overridden_by_metrics(self):
  e,c,r=self.fake();e.manual('medium');e.grace_until=0
  for i in range(8):e.observe(Metric(-90,0,.4,.3,True,'simulation'))
  self.assertEqual(e.current.name,'medium');self.assertEqual(e.policy.index,2)
 def test_restart_grace_does_not_treat_pause_as_link_failure(self):
  e,c,r=self.fake()
  e.observe(Metric(None,None,0,0,False,'simulation'))
  self.assertEqual(e.current.name,'low')
 def test_manual_fast_profile_is_outside_automatic_steps(self):
  e,c,r=self.fake();e.manual('fast')
  self.assertEqual(e.current.name,'fast');self.assertFalse(e.automatic)
  self.assertEqual(e.policy.index,3)
 def test_simulation_feedback_not_accepted_in_real_radio_mode(self):
  e,c,r=self.fake();e.mode='radio'
  with self.assertRaises(ValueError):e.observe(Metric(-50,30,0,0,True,'simulation'))
