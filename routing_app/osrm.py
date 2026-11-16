"""Local-only, cached road costs. HTTP tiles never become sequencing chunks."""
import hashlib
import json
import math
import sqlite3
import time
import zlib
from urllib.parse import quote

import numpy as np
import requests


class RoadError(ValueError):
    pass


def coordinate(a):
    return a.get("coordinate", [a.get("lon"), a.get("lat")])


def encode_polyline6(points):
    result, previous = [], [0, 0]
    for lon, lat in points:
        for i, value in enumerate([lat, lon]):
            current = round(value*1e6)
            delta = current-previous[i]
            previous[i] = current
            encoded = ~(delta << 1) if delta < 0 else delta << 1
            while encoded >= 0x20:
                result.append(chr((0x20 | (encoded & 0x1f))+63))
                encoded >>= 5
            result.append(chr(encoded+63))
    return "".join(result)


class OSRM:
    def __init__(self, cache, fingerprint, progress=lambda *a:None, table_locations=800):
        self.base = "http://127.0.0.1:5001"
        self.session = requests.Session()
        self.session.trust_env = False
        self.db = sqlite3.connect(cache / "routing-osrm.sqlite")
        self.db.execute("CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, body BLOB NOT NULL)")
        self.fingerprint = fingerprint
        self.progress = progress
        self.limit = table_locations
        self.started = time.monotonic()
        self.requests = self.hits = 0

    def close(self):
        self.db.close()
        self.session.close()

    def get(self, service, points, **params):
        coords = [coordinate(p) for p in points]
        params = {**params, "generate_hints":"false"}
        if any(p.get("bearing") is not None for p in points):
            params["bearings"] = ";".join(f"{int(p['bearing'])%360},40" if p.get("bearing") is not None else "" for p in points)
            params["radiuses"] = ";".join(str(p.get('snap_radius_m',35)) if p.get("bearing") is not None else "1000" for p in points)
        material = json.dumps([self.fingerprint, service, coords, params], sort_keys=True)
        key = hashlib.sha256(material.encode()).hexdigest()
        row = self.db.execute("SELECT body FROM responses WHERE key=?", (key,)).fetchone()
        if row:
            self.hits += 1
            return json.loads(zlib.decompress(row[0]))
        self.progress(None, f"Local road calculations: {self.requests:,} requests, {self.hits:,} cache hits")
        if self.requests >= 30000 or time.monotonic()-self.started > 7200:
            raise RoadError("The bounded local road-calculation budget was reached. Cached work is preserved.")
        path = (f"{coords[0][0]:.7f},{coords[0][1]:.7f}" if service == "nearest" else
                "polyline6("+quote(encode_polyline6(coords),safe="")+")")
        self.requests += 1
        try:
            response = self.session.get(f"{self.base}/{service}/v1/driving/{path}", params=params, timeout=(4,45))
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RoadError("Local OSRM is unavailable or timed out. Start the Manitoba container on port 5001; no automatic retry was made.") from exc
        if not response.ok or payload.get("code") != "Ok":
            raise RoadError(f"OSRM {service}: {payload.get('message',payload.get('code',response.status_code))}. Locations: {coords[:2]}")
        self.db.execute("INSERT OR REPLACE INTO responses VALUES (?,?)", (key,zlib.compress(json.dumps(payload,separators=(",", ":")).encode())))
        self.db.commit()
        return payload

    def facility(self, site):
        waypoint = self.get("nearest", [site], number=1)["waypoints"][0]
        return {**site, "coordinate":waypoint["location"], "mapped_road":waypoint["name"],
                "mapped_offset_m":round(waypoint["distance"],1), "bearing":None}

    def table(self, sources, destinations):
        durations = np.full((len(sources),len(destinations)),np.inf)
        distances = durations.copy()
        # Complete matrix is assembled before the one section solve. Blocks only
        # bound HTTP size / memory. Neither section nor load state resets here.
        block = min(90, self.limit//2)
        for i in range(0,len(sources),block):
            for j in range(0,len(destinations),block):
                a,b = sources[i:i+block],destinations[j:j+block]
                data = self.get("table", a+b, sources=";".join(map(str,range(len(a)))),
                    destinations=";".join(map(str,range(len(a),len(a)+len(b)))), annotations="duration,distance")
                for x,row in enumerate(data["durations"]):
                    for y,value in enumerate(row):
                        if value is not None:
                            durations[i+x,j+y] = value
                            distances[i+x,j+y] = data["distances"][x][y]
        return durations, distances

    def route(self, points, unrestricted=False):
        # Overlapping replay batches retain the identical predecessor and its
        # direction. They never add depot returns or determine service order.
        unique=[]
        for p in points:
            if not unique or coordinate(p) != coordinate(unique[-1]) or p.get("bearing") != unique[-1].get("bearing"):
                unique.append(p)
        if len(unique) < 2:
            return {"seconds":0.,"meters":0.,"geometry":[coordinate(unique[0])] if unique else [],
                    "reversals":0,"legs":[],"snaps":[coordinate(p) for p in unique]}
        result={"seconds":0.,"meters":0.,"geometry":[],"reversals":0,"legs":[],"snaps":[]}
        for i in range(0,len(unique)-1,69):
            batch=unique[i:i+70]
            if unrestricted:
                batch=[{**p,"bearing":None} for p in batch]
            data=self.get("route",batch,overview="full",geometries="geojson",steps="true",continue_straight="true")
            route=data["routes"][0]
            result["seconds"]+=route["duration"];result["meters"]+=route["distance"]
            geom=route["geometry"]["coordinates"]
            result["geometry"].extend(geom if not result["geometry"] else geom[1:])
            snaps=[w["location"] for w in data["waypoints"]]
            result["snaps"].extend(snaps if not result["snaps"] else snaps[1:])
            for leg in route["legs"]:
                turns=sum(1 for s in leg["steps"] if s["maneuver"].get("modifier")=="uturn" and
                          abs((s["maneuver"].get("bearing_after",0)-s["maneuver"].get("bearing_before",0)+180)%360-180)>=150)
                result["reversals"]+=turns
                steps=leg["steps"]
                geometry=[]
                for step in steps:
                    coords=step.get('geometry',{}).get('coordinates',[])
                    geometry.extend(coords[1:] if geometry and coords and geometry[-1]==coords[0] else coords)
                result["legs"].append({"seconds":leg["duration"],"meters":leg["distance"],"reversals":turns,
                    "geometry":geometry,
                    "departure_bearing":steps[0]["maneuver"].get("bearing_after") if steps else None,
                    "arrival_bearing":steps[-1]["maneuver"].get("bearing_before") if steps else None})
        return result
