Bundled orthomosaic tiles (offline fallback)
=============================================

Drop your pre-rendered orthomosaic tiles here in the standard XYZ layout:

    orthomosaic/{z}/{x}/{y}.png

  • Tile order is {z}/{x}/{y}  (NOTE: different from VWorld base, which is {z}/{y}/{x}).
  • Recommended zoom range: z5 – z20.
  • These tiles ship WITH the app, so the map still shows imagery on a closed /
    air-gapped network with no tile server reachable.
  • OrthoTileLayer.tsx renders these at maxNativeZoom=20 and OVERSCALES them to
    z21–22 (it never requests z21+ files, so you don't need to generate them).
  • Missing tiles fall through to the VWorld satellite base (transparent errorTile),
    so a partial tileset is fine.

Leave this folder empty (just .gitkeep) if you don't need an offline fallback;
the app will use the live server tiles and/or the VWorld satellite base instead.

To generate tiles, e.g. with gdal2tiles:

    gdal2tiles.py --xyz -z 5-20 orthomosaic.tif ./orthomosaic/
