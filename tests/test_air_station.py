import json
import unittest
from bvs_camera.paths import DEFAULT_CONFIG

class AirPlanTests(unittest.TestCase):
 def test_radio_plan_uses_real_interface_and_camera_radio_mode(self):
  from bvs_camera.air_station import parser,build_commands
  args=parser().parse_args(['--mode','radio','--interface','wlan1'])
  drone=json.loads(DEFAULT_CONFIG.read_text())['drones'][0]
  commands=build_commands(args,drone)
  self.assertEqual([name for name,_ in commands],['radio','camera'])
  self.assertIn('bvs_camera.radio_launcher',commands[0][1]);self.assertIn('wlan1',commands[0][1])
  self.assertEqual(commands[1][1][commands[1][1].index('--mode')+1],'radio')
 def test_ip_plan_still_clearly_uses_ip_carrier(self):
  from bvs_camera.air_station import parser,build_commands
  args=parser().parse_args(['--bind','10.0.0.1','--peer','10.0.0.2'])
  drone=json.loads(DEFAULT_CONFIG.read_text())['drones'][0]
  commands=build_commands(args,drone)
  self.assertEqual(commands[0][0],'carrier')
  self.assertIn('bvs_camera.udp_link',commands[0][1])
  self.assertEqual(commands[-1][1][commands[-1][1].index('--mode')+1],'ip')
if __name__=='__main__':unittest.main()
