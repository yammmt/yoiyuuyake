import io, json, sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/"scripts"))
from open_meteo import HOURLY_VARIABLES, OpenMeteoError, build_forecast_url, fetch_today_forecast
class Response(io.BytesIO):
 status=200
 def __enter__(self): return self
 def __exit__(self,*args): return False
def payload(): return {"hourly":{"time":["2026-08-16T18:00"], **{key:[index+1] for index,key in enumerate(HOURLY_VARIABLES)}}}
class OpenMeteoTests(unittest.TestCase):
 def test_url_requests_jst_jma_and_all_required_fields(self):
  url=build_forecast_url(35.6,139.7); self.assertIn("timezone=Asia%2FTokyo",url); self.assertIn("models=jma_seamless",url); self.assertIn("cloud_cover_low",url)
 def test_response_becomes_typed_hourly_data(self):
  hours=fetch_today_forecast(35.6,139.7,opener=lambda *_args,**_kwargs:Response(json.dumps(payload()).encode()))
  self.assertEqual(hours[0].time.hour,18); self.assertEqual(hours[0].visibility,5.0)
 def test_missing_variable_is_an_error(self):
  data=payload(); del data["hourly"]["visibility"]
  with self.assertRaises(OpenMeteoError): fetch_today_forecast(35.6,139.7,opener=lambda *_args,**_kwargs:Response(json.dumps(data).encode()))
