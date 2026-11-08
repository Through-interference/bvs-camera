import json,unittest
from bvs_camera.feedback import parse_metric
class FeedbackTests(unittest.TestCase):
 def test_nsu_wire_message(self):
  m=parse_metric(json.dumps(dict(rssi=None,snr=None,pre_loss=.05,post_loss=0,active=True,source='wfb-ip',decoder_fps=30,receiver_cpu_percent=15,receiver_overloaded=False)).encode())
  self.assertEqual(m.source,'wfb-ip');self.assertTrue(m.active);self.assertEqual(m.decoder_fps,30)
 def test_wrong_activity_type_rejected(self):
  with self.assertRaises(ValueError):parse_metric('{"rssi":-60,"snr":20,"pre_loss":0,"post_loss":0,"active":"false"}')
 def test_non_object_rejected(self):
  with self.assertRaises(ValueError):parse_metric('[]')
