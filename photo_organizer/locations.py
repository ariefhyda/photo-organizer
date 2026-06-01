"""Pengelompokan lokasi GPS, reverse-geocoding, dan pembuatan peta HTML."""

from __future__ import annotations

import html
import json
import math
import tempfile
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Optional


def cluster_locations(rows, decimals: int = 2) -> list[dict]:
    """Kelompokkan foto ber-GPS menjadi 'tempat' berdasarkan grid koordinat.

    decimals=2 ≈ sel ~1.1 km. Mengembalikan daftar klaster terurut dari yang
    paling banyak fotonya, tiap klaster: {key, lat, lon, count, ids, label}.
    """
    groups: dict[tuple, list] = defaultdict(list)
    for r in rows:
        if r["lat"] is None or r["lon"] is None:
            continue
        key = (round(r["lat"], decimals), round(r["lon"], decimals))
        groups[key].append(r)

    clusters = []
    for key, members in groups.items():
        clat = sum(m["lat"] for m in members) / len(members)
        clon = sum(m["lon"] for m in members) / len(members)
        clusters.append({
            "key": f"{key[0]},{key[1]}",
            "lat": round(clat, 6),
            "lon": round(clon, 6),
            "count": len(members),
            "ids": [m["id"] for m in members],
            "label": f"{clat:.3f}, {clon:.3f}",
        })
    clusters.sort(key=lambda c: c["count"], reverse=True)
    return clusters


def reverse_geocode(lat: float, lon: float,
                    timeout: float = 6.0) -> Optional[str]:
    """Ubah koordinat jadi nama tempat via OpenStreetMap Nominatim (online).

    Mengembalikan label ringkas, atau None bila gagal/offline.
    """
    params = urllib.parse.urlencode({
        "format": "jsonv2", "lat": f"{lat:.5f}", "lon": f"{lon:.5f}",
        "zoom": "14", "accept-language": "id",
    })
    url = f"https://nominatim.openstreetmap.org/reverse?{params}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "PhotoOrganizer/1.0 (desktop app)",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    addr = data.get("address", {})
    locality = (addr.get("suburb") or addr.get("village") or addr.get("town")
                or addr.get("city_district") or addr.get("city")
                or addr.get("county"))
    region = addr.get("state") or addr.get("region")
    country = addr.get("country")
    parts = [p for p in (locality, region or country) if p]
    if parts:
        return ", ".join(dict.fromkeys(parts))  # buang duplikat, jaga urutan
    return data.get("display_name", "").split(",")[0] or None


# ----------------------------------------------------------------- peta HTML
_MAP_TEMPLATE = """<!DOCTYPE html>
<html lang="id"><head><meta charset="utf-8">
<title>{title}</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
<style>
  html,body,#map{{height:100%;margin:0;background:#16171b}}
  .leaflet-popup-content-wrapper{{background:#202127;color:#e7e8ea;border-radius:12px}}
  .leaflet-popup-tip{{background:#202127}}
  .leaflet-popup-content{{font-family:Segoe UI,sans-serif;margin:10px 12px}}
  .pp img{{display:block;max-width:260px;max-height:260px;border-radius:10px;margin-bottom:8px}}
  .pp b{{font-size:14px}} .pp .meta{{color:#9aa0aa;font-size:12px;line-height:1.5}}
  /* Pin berupa thumbnail */
  .photo-pin .pin{{width:48px;height:48px;border-radius:10px;border:3px solid #fff;
     box-shadow:0 2px 5px rgba(0,0,0,.55);overflow:hidden;background:#202127;position:relative}}
  .photo-pin .pin img{{width:100%;height:100%;object-fit:cover;display:block}}
  .photo-pin .pin:after{{content:'';position:absolute;left:50%;bottom:-9px;transform:translateX(-50%);
     border-left:7px solid transparent;border-right:7px solid transparent;border-top:9px solid #fff}}
  .photo-pin .dot{{width:16px;height:16px;border-radius:50%;background:#6c8cff;border:3px solid #fff;
     box-shadow:0 2px 5px rgba(0,0,0,.55)}}
  .hdr{{position:absolute;z-index:1000;top:10px;left:50px;background:#202127;color:#e7e8ea;
       padding:8px 14px;border-radius:10px;font-family:Segoe UI,sans-serif;box-shadow:0 2px 8px rgba(0,0,0,.4)}}
</style></head><body>
<div class="hdr">📍 {title} — {count} foto berlokasi</div>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script>
const points = {points_json};
const map = L.map('map', {{preferCanvas:false}});
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 19, attribution: '&copy; OpenStreetMap'
}}).addTo(map);

function makeIcon(p) {{
  if (p.thumb) {{
    return L.divIcon({{className:'photo-pin',
      html:'<div class="pin"><img src="'+p.thumb+'"></div>',
      iconSize:[54,54], iconAnchor:[27,54], popupAnchor:[0,-52]}});
  }}
  return L.divIcon({{className:'photo-pin', html:'<div class="dot"></div>',
      iconSize:[22,22], iconAnchor:[11,22], popupAnchor:[0,-20]}});
}}

const markers = L.markerClusterGroup({{maxClusterRadius:48}});
const bounds = [];
points.forEach(p => {{
  const m = L.marker([p.lat, p.lon], {{icon: makeIcon(p)}});
  let html = '<div class="pp">';
  const big = p.full || p.thumb;
  if (big) html += '<img src="' + big + '">';
  html += '<b>' + p.name + '</b><div class="meta">' +
          (p.date ? p.date + '<br>' : '') +
          '📍 ' + p.lat.toFixed(5) + ', ' + p.lon.toFixed(5) +
          (p.place ? '<br>' + p.place : '') + '</div></div>';
  m.bindPopup(html, {{maxWidth: 300}});
  markers.addLayer(m);
  bounds.push([p.lat, p.lon]);
}});
map.addLayer(markers);
if (bounds.length) map.fitBounds(bounds, {{padding:[50,50], maxZoom:16}});
else map.setView([0,0], 2);
</script></body></html>"""


def _file_uri(path: Path) -> str:
    return path.resolve().as_uri()


def build_map_html(points: list[dict], title: str = "Peta Foto",
                   out_path: Optional[Path] = None) -> Path:
    """Tulis berkas HTML peta interaktif. `points`: list {lat,lon,name,date,thumb}.

    `thumb` (opsional) adalah Path thumbnail lokal. Kembalikan path HTML.
    """
    js_points = []
    for p in points:
        thumb = p.get("thumb")
        js_points.append({
            "lat": p["lat"], "lon": p["lon"],
            "name": html.escape(str(p.get("name", ""))),
            "date": html.escape(str(p.get("date") or "")),
            "place": html.escape(str(p.get("place") or "")),
            "thumb": _file_uri(Path(thumb)) if thumb else "",
            "full": _file_uri(Path(p["full"])) if p.get("full") else "",
        })
    out = out_path or (Path(tempfile.gettempdir()) / "photo_organizer_map.html")
    out.write_text(_MAP_TEMPLATE.format(
        title=html.escape(title),
        count=len(js_points),
        points_json=json.dumps(js_points),
    ), encoding="utf-8")
    return out
