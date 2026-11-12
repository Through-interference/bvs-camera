"""Recover capture stalls and send current feedback after a slow profile change."""
from dataclasses import asdict
import json
import threading
import unittest
from unittest.mock import Mock,patch
from bvs_camera.adaptive_server import Engine
from bvs_camera.feedback import receive_latest
from bvs_camera.link_core import Metric,PROFILES


class Camera:
    def __init__(self):
        self.change_lock=threading.Lock()
        self.state={'running':True,'frame_age_s':0}
        self._stop_process=Mock()
        self.set_profile=Mock()
    def status(self):return dict(self.state)


class CameraRecoveryTests(unittest.TestCase):
    def engine(self):
        camera=Camera()
        engine=Engine(camera,None,'camera-only')
        engine.current=PROFILES[1]
        engine.automatic=False
        return engine,camera

    def test_stopped_capture_restarts_in_manual_mode(self):
        engine,camera=self.engine();camera.state['running']=False
        engine.poll()
        camera.set_profile.assert_called_once_with('low')
        self.assertFalse(engine.automatic)

    def test_live_process_with_stale_rtp_is_restarted(self):
        engine,camera=self.engine();camera.state['frame_age_s']=6
        engine.poll()
        camera.set_profile.assert_called_once_with('low')

    def test_missing_complete_frames_is_treated_as_stall(self):
        engine,camera=self.engine();camera.state['frame_age_s']=None
        engine.poll()
        camera.set_profile.assert_called_once_with('low')

    def test_healthy_capture_and_startup_grace_do_not_restart(self):
        engine,camera=self.engine()
        engine.poll()
        camera.set_profile.assert_not_called()
        camera.state['running']=False;engine.grace_until=20
        with patch('bvs_camera.adaptive_server.time.monotonic',return_value=10):engine.poll()
        camera.set_profile.assert_not_called()

    def test_failed_restart_is_retried_after_backoff(self):
        engine,camera=self.engine();camera.state['running']=False
        camera.set_profile.side_effect=RuntimeError('capture unavailable')
        with patch('bvs_camera.adaptive_server.time.monotonic',return_value=10):
            engine.poll()
            attempts=camera.set_profile.call_count
            self.assertGreater(attempts,0)
            engine.poll()
            self.assertEqual(camera.set_profile.call_count,attempts)
        with patch('bvs_camera.adaptive_server.time.monotonic',return_value=14):engine.poll()
        self.assertGreater(camera.set_profile.call_count,attempts)
        self.assertIn('capture unavailable',engine.error)

    def test_closed_engine_does_not_restart_capture(self):
        engine,camera=self.engine();camera.state['running']=False;engine.closed=True
        engine.poll()
        camera.set_profile.assert_not_called()

    def test_feedback_backlog_keeps_only_newest_metric(self):
        metrics=[Metric(None,None,0,.5,True,'wfb-ip'),Metric(None,None,0,0,True,'wfb-ip')]
        sock=Mock();sock.recv.side_effect=[json.dumps(asdict(m)).encode() for m in metrics]
        with patch('bvs_camera.feedback.select.select',side_effect=[([sock],[],[]),([],[],[])]):
            self.assertEqual(receive_latest(sock),metrics[-1])
        self.assertEqual(sock.recv.call_count,2)


if __name__=='__main__':unittest.main()
