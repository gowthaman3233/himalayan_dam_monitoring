"""Hydrology input handling.

WhiteboxTools runs as an external executable, so the flow-routing steps
themselves cannot be unit tested without the binary. What *can* be tested, and
what actually broke on real data, is the step that prepares the DEM for it.

The Baige 2018 run failed here: the project's own DEM acquisition emits a
three-band Copernicus GLO-30 product (DEM, HEM, WBM), WhiteboxTools rejected
it while reading, produced no output, exited 0, and the module then blamed the
CRS. These tests pin the band extraction that fixes it.

All rasters here are synthetic, written to tmp_path.
"""

from __future__ import annotations

import numpy as np
import pytest
import rasterio
from affine import Affine

from preprocessing.hydrology import ELEVATION_BAND, _whitebox_readable_dem

pytestmark = pytest.mark.synthetic

TRANSFORM = Affine(10.0, 0.0, 450000.0, 0.0, -10.0, 3085000.0)
UTM47N = "EPSG:32647"


def _write(path, bands, *, descriptions=None, compress="deflate", nodata=None):
    """Write a synthetic DEM-like GeoTIFF and return its path."""
    count = len(bands)
    profile = {
        "driver": "GTiff",
        "height": bands[0].shape[0],
        "width": bands[0].shape[1],
        "count": count,
        "dtype": "float32",
        "crs": UTM47N,
        "transform": TRANSFORM,
        "compress": compress,
    }
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as dst:
        for index, band in enumerate(bands, start=1):
            dst.write(band.astype("float32"), index)
            if descriptions:
                dst.set_band_description(index, descriptions[index - 1])
    return path


@pytest.fixture
def glo30_like(tmp_path):
    """A three-band GLO-30-shaped product, as acquisition.dem emits.

    Band 1 is elevation; the others are deliberately given values that could
    not be mistaken for terrain, so a test that silently read the wrong band
    would fail loudly rather than pass on plausible numbers.
    """
    elevation = np.linspace(2800.0, 3400.0, 64).reshape(8, 8)
    height_error = np.full((8, 8), 2.5)
    water_body = np.zeros((8, 8))
    path = _write(
        tmp_path / "DEM_GLO30_v02.tif",
        [elevation, height_error, water_body],
        descriptions=["DEM", "HEM", "WBM"],
    )
    return path, elevation


class TestMultiBandDEM:
    def test_elevation_band_is_extracted(self, glo30_like, tmp_path):
        source, elevation = glo30_like
        out = _whitebox_readable_dem(source, tmp_path, "baige")

        assert out != source, "a multi-band DEM must not be passed through"
        with rasterio.open(out) as src:
            assert src.count == 1
            np.testing.assert_allclose(src.read(1), elevation, rtol=1e-5)

    def test_the_copy_keeps_the_georeferencing(self, glo30_like, tmp_path):
        """A shifted or reprojected copy would move the whole stream network."""
        source, _ = glo30_like
        out = _whitebox_readable_dem(source, tmp_path, "baige")
        with rasterio.open(source) as a, rasterio.open(out) as b:
            assert b.transform == a.transform
            assert b.crs == a.crs
            assert (b.height, b.width) == (a.height, a.width)

    def test_the_band_description_is_carried_over(self, glo30_like, tmp_path):
        source, _ = glo30_like
        out = _whitebox_readable_dem(source, tmp_path, "baige")
        with rasterio.open(out) as src:
            assert src.descriptions[0] == "DEM"

    def test_the_copy_is_written_where_asked(self, glo30_like, tmp_path):
        source, _ = glo30_like
        out_dir = tmp_path / "hydro"
        out_dir.mkdir()
        out = _whitebox_readable_dem(source, out_dir, "myprefix")
        assert out.parent == out_dir
        assert out.name.startswith("myprefix")

    def test_compression_is_one_whitebox_accepts(self, glo30_like, tmp_path):
        """DEFLATE is nominally supported yet was rejected; LZW is written."""
        source, _ = glo30_like
        out = _whitebox_readable_dem(source, tmp_path, "baige")
        with rasterio.open(out) as src:
            assert src.profile.get("compress") == "lzw"

    def test_nodata_is_preserved(self, tmp_path):
        """Losing nodata would let void pixels route flow as real terrain."""
        elevation = np.linspace(2800.0, 3400.0, 64).reshape(8, 8)
        elevation[0, 0] = -32767.0
        source = _write(
            tmp_path / "with_nodata.tif",
            [elevation, np.zeros((8, 8))],
            descriptions=["DEM", "HEM"],
            nodata=-32767.0,
        )
        out = _whitebox_readable_dem(source, tmp_path, "baige")
        with rasterio.open(out) as src:
            assert src.nodata == pytest.approx(-32767.0)


class TestSingleBandDEM:
    def test_a_single_band_dem_is_passed_through_untouched(self, tmp_path):
        """Nothing is rewritten needlessly, so no copy appears on disk."""
        source = _write(
            tmp_path / "already_fine.tif",
            [np.linspace(2800.0, 3400.0, 64).reshape(8, 8)],
            descriptions=["DEM"],
        )
        out = _whitebox_readable_dem(source, tmp_path, "baige")
        assert out == source
        assert not (tmp_path / "baige_elevation.tif").exists()


def test_elevation_band_is_the_first_band():
    """GLO-30 ships DEM first; the constant exists so that is not implicit."""
    assert ELEVATION_BAND == 1
