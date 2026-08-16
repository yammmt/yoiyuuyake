from datetime import date
import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/"scripts"))
from astronomy import sunset_on
class AstronomyTests(unittest.TestCase):
 def test_tokyo_sunset_has_expected_time_direction_and_altitude(self):
  sunset=sunset_on(date(2026,8,16),35.6812,139.7671)
  self.assertEqual(sunset.time.tzinfo.key,"Asia/Tokyo"); self.assertTrue(17 <= sunset.time.hour <= 19); self.assertTrue(240 < sunset.azimuth_degrees < 300); self.assertTrue(-1.1 < sunset.altitude_degrees < -0.6)
