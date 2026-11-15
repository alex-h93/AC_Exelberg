#!/usr/bin/env python3
"""Render the saved route locally using existing Pillow; no network or installs."""
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def main():
    feature = json.loads((ROOT / 'data/processed/route.geojson').read_text())['features'][0]
    coordinates = feature['geometry']['coordinates']
    west, south, east, north = feature['properties']['bounds_west_south_east_north']
    aspect = math.cos(math.radians((south + north) / 2))
    scale = min(1050 / ((east - west) * aspect), 850 / (north - south))

    def xy(point):
        return 90 + (point[0] - west) * aspect * scale, 100 + (north - point[1]) * scale

    image = Image.new('RGB', (1400, 1100), 'white')
    draw = ImageDraw.Draw(image)
    font_path = next((p for p in [
        '/usr/share/fonts/google-noto/NotoSans-Regular.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    ] if Path(p).exists()), None)
    font = ImageFont.truetype(font_path, 18) if font_path else ImageFont.load_default(size=18)
    title = ImageFont.truetype(font_path, 24) if font_path else ImageFont.load_default(size=24)
    length_km = feature['properties']['length_m'] / 1000
    draw.text((30, 25), f'Koenigstetten to Marswiese | provisional OSM route | {length_km:.3f} km', font=title, fill='black')
    draw.line([xy(p) for p in coordinates], fill='#5530aa', width=5)
    for label, point in [('START: Koenigstetten', coordinates[0]), ('FINISH: Marswiese', coordinates[-1])]:
        x, y = xy(point)
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill='red')
        draw.text((x + 12, y - 18), label, font=font, fill='black')

    # Label one source node per landmark; prefer settlement/hut/peak tags over stops.
    elements = json.loads((ROOT / 'data/interim/osm/merged.json').read_text())['elements']
    for name in ['Dopplerhütte', 'Scheiblingstein', 'Exelberg']:
        matches = [e for e in elements if e['type'] == 'node' and e.get('tags', {}).get('name') == name]
        if not matches:
            continue
        chosen = max(matches, key=lambda e: bool(e['tags'].get('place') or e['tags'].get('natural') == 'peak' or e['tags'].get('tourism')))
        x, y = xy((chosen['lon'], chosen['lat']))
        if 0 < x < 1300 and 65 < y < 1000:
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill='black')
            draw.text((x + 10, y + 8), name, font=font, fill='black')
    draw.text((30, 1030), 'North up | © OpenStreetMap contributors | ODbL | 2D only: no terrain sampled', font=font, fill='black')
    destination = ROOT / 'data/processed/route_preview.png'
    image.save(destination)
    print(destination.relative_to(ROOT))


if __name__ == '__main__':
    main()
