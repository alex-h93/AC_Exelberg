# Prototype coordinate contract (version 1)

This records the requested prepared-data convention, not approval of road geometry.
All full-track and prototype authoring uses **EPSG:25833**, metres. Do not recenter
the prototype on its own section. The one common origin is:

- E0 = **589500 m**, N0 = **5346800 m**, H0 = **300 m**.
- Compute full OSM polyline planar arclength in EPSG:25833; interpolate its
  half-arclength point, then round easting and northing independently to nearest
  100 m (NumPy ties-to-even). The unrounded midpoint is in the manifest.
- Blender local **X = E − E0, Y = N − N0, Z = H − 300**, right-handed, metres.
  Inverse: E=X+E0, N=Y+N0, H=Z+300. No axis swap, rotation, or scale.
- H remains the BEV product-documented **EPSG:9274 / EVRF2000 Austria orthometric
  height**. No vertical datum transformation occurs. Do not substitute GPS
  ellipsoidal heights, Adria heights, or treat these heights as RFC 7946 Z.
  Vertical reference/accuracy is not independently surveyed.

## Horizontal operations

`prepare_prototype.py` sets `PROJ_NETWORK=OFF` and explicitly disables pyproj
networking before selecting operations. `TransformerGroup` uses `always_xy=True`
and `allow_ballpark=False`; failure to find an operation is fatal. Longitude,
latitude are used for EPSG:4326; easting,northing for all projected arrays,
regardless of authority-native axis ordering. Only XY is transformed.

Selected in PROJ 9.8.1 / pyproj 3.8.0 (the manifest records actual build versions):

1. EPSG:4326 → EPSG:3035: inverse ETRS89 to WGS 84 (1) + Europe Equal Area
   2001, normalized XY; reported **1 m** accuracy.
2. EPSG:3035 → EPSG:25833: inverse Europe Equal Area 2001 + UTM zone 33N,
   normalized XY; reported **0 m** coordinate-operation accuracy. The same
   selected operation in inverse direction samples the original terrain.

Both selected operations are best-available in the offline environment. Complete
PROJ definitions, descriptions and accuracy are embedded in `manifest.json`.
Operation accuracy is not measured OSM or raster alignment accuracy, and zero
projection-operation accuracy does not mean a perfectly surveyed road.

## Distances and precision

Full route lengths: **15226.291863325048 m in EPSG:3035** and
**15226.670946413231 m in EPSG:25833**. Earlier spherical distance is approximately
15.205 km. These are different distance conventions, not changed road alignment.

Prototype boundaries are precisely interpolated at **1000–2500 m EPSG:3035
chainage**, reconstructed from the original route vertices, not the rounded CSV.
Every interior OSM corner is preserved. Dense points subdivide straight native
EPSG:25833 segments to ≤2 m; chainage labels interpolate the corresponding
EPSG:3035 vertex chainages. Thus labels retain the existing profile convention,
not native UTM arclength. The tiny curvature difference between projected straight
segments is not an alignment refinement.

Arrays are float64 with explicit bool masks. Largest absolute full-route/terrain
local XY is **4804.210174 m**; float32 spacing there is **0.00048828125 m**. This is
numerical precision only, not source accuracy. The manifest stores three widely
separated controls with EPSG:3035, EPSG:25833, local XYZ at a synthetic H=300 m,
and inverse values. Maximum inverse residual is **9.32e-10 m** in this build.
Synthetic control heights verify the origin mapping, not terrain elevation.

See [the consumer contract](../validation/PROTOTYPE_INPUTS.md) for masks,
array names, build commands and limitations.
