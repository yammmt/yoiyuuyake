#!/usr/bin/env python3
"""Serve a local, external-service-free terrain visibility page."""
from __future__ import annotations
import argparse, json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from dem_store import DemDataUnavailableError, DemNoElevationError, LocalDemStore
from horizon import calculate_horizon
from visibility import assess_visibility, ray_to_dict

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--data",required=True,type=Path); p.add_argument("--port",type=int,default=8787); args=p.parse_args()
    store=LocalDemStore(args.data); web_root=Path(__file__).parents[1]/"web"
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*a,**kw): super().__init__(*a,directory=str(web_root),**kw)
        def do_GET(self):
            parsed=urlparse(self.path)
            if parsed.path != "/api/horizon": return super().do_GET()
            try:
                q=parse_qs(parsed.query); lat=float(q["lat"][0]); lng=float(q["lng"][0]); azimuth=float(q.get("azimuth",[270])[0]); sun=float(q.get("sun_altitude",[1])[0])
                profile=calculate_horizon(store,lat,lng,azimuth); assessment=assess_visibility(profile,sun)
                self._json(HTTPStatus.OK,{"observer_elevation_meters":profile.observer_elevation_meters,"visibility":assessment.__dict__,"rays":[ray_to_dict(ray) for ray in profile.rays]})
            except (KeyError, ValueError) as error: self._json(HTTPStatus.BAD_REQUEST,{"error":f"入力が不正です: {error}"})
            except (DemDataUnavailableError,DemNoElevationError) as error: self._json(HTTPStatus.UNPROCESSABLE_ENTITY,{"error":str(error)})
        def _json(self,status,payload):
            body=json.dumps(payload,ensure_ascii=False).encode(); self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    server=ThreadingHTTPServer(("127.0.0.1",args.port),Handler)
    print(f"http://127.0.0.1:{args.port}")
    try: server.serve_forever()
    finally: store.close(); server.server_close()
if __name__ == "__main__": main()
