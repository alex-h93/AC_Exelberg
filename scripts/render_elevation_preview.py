#!/usr/bin/env python3
"""Offline PNG review of the 10 m CSV; uses already available Pillow."""
import csv
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def main():
    with (ROOT / 'data/processed/route_elevation.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    samples = [(float(r['distance_m']), float(r['terrain_height_m']) if r['valid'] == '1' else None) for r in rows]
    valid_heights = [h for _, h in samples if h is not None]
    low = math.floor(min(valid_heights) / 50) * 50
    high = math.ceil(max(valid_heights) / 50) * 50
    length = samples[-1][0]
    image = Image.new('RGB', (1400, 650), 'white')
    draw = ImageDraw.Draw(image)
    font_path = next((p for p in ['/usr/share/fonts/google-noto/NotoSans-Regular.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'] if Path(p).exists()), None)
    font = ImageFont.truetype(font_path, 18) if font_path else ImageFont.load_default(size=18)
    title = ImageFont.truetype(font_path, 25) if font_path else ImageFont.load_default(size=25)

    def point(distance, height):
        return 90 + distance / length * 1210, 490 - (height - low) / max(high - low, 1) * 370

    draw.text((40, 20), 'Koenigstetten to Marswiese: sampled bare-earth terrain', font=title, fill='#173d25')
    draw.text((40, 60), 'Provisional OSM alignment | raw bilinear heights at <=10 m spacing | not a road survey', font=font, fill='black')
    for elevation in range(low, high + 1, 50):
        _, y = point(0, elevation)
        draw.line((90, y, 1300, y), fill='#dddddd')
        draw.text((15, y - 12), f'{elevation} m', font=font, fill='#444444')
    for kilometre in range(math.floor(length / 1000) + 1):
        x, _ = point(kilometre * 1000, low)
        draw.line((x, 120, x, 490), fill='#eeeeee')
        draw.text((x - 8, 505), str(kilometre), font=font, fill='#444444')
    run = []
    for distance, height in samples:
        if height is None:
            if len(run) > 1:
                draw.line(run, fill='#176b39', width=3)
            run = []
        else:
            run.append(point(distance, height))
    if len(run) > 1:
        draw.line(run, fill='#176b39', width=3)
    for label, distance, height in [('Start', *samples[0]), ('Finish', *samples[-1])]:
        if height is not None:
            x, y = point(distance, height)
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill='black')
            offset = -180 if label == 'Finish' else 10
            draw.text((x + offset, y + 10), f'{label}: {height:.1f} m', font=font, fill='black')
    suspect_x, _ = point(9590, low)
    draw.line((suspect_x, 115, suspect_x, 490), fill='#b84131', width=2)
    draw.text((suspect_x + 8, 125), '9.59 km: investigate narrow terrain dip', font=font, fill='#b84131')
    draw.text((90, 550), 'Distance in km (EPSG:3035 planar) | elevations: documented EVRF2000 Austria', font=font, fill='black')
    draw.text((90, 595), '© BEV, CC BY 4.0; route © OpenStreetMap contributors, ODbL. No vertical smoothing.', font=font, fill='black')
    destination = ROOT / 'data/processed/elevation_profile.png'
    image.save(destination)
    print(destination.relative_to(ROOT))


if __name__ == '__main__':
    main()
