"""exif_gps.py — Extract decimal-degree GPS from a JPEG or HEIC photo.

Used by linebot-admin's project management UI to read GPS from a "sample"
photo the user took at a site, so the project's GPS centre can be set with
one click instead of typed coordinates.

Ported from synology-photo-tagger as part of openspec change
`consolidate-project-registry`.
"""
from __future__ import annotations

from typing import BinaryIO, Union

from PIL import Image
from PIL.ExifTags import GPSTAGS
import pillow_heif

pillow_heif.register_heif_opener()

_GPS_IFD_TAG = 0x8825


def _dms_to_decimal(dms, ref) -> float:
    d, m, s = (float(x) for x in dms)
    val = d + m / 60 + s / 3600
    return -val if ref in ("S", "W") else val


def extract_gps(source: Union[str, BinaryIO]) -> tuple[float, float]:
    """Return ``(lat, lng)`` in decimal degrees, or raise ``ValueError``.

    Never returns ``(0, 0)`` for a missing fix — callers can trust that a
    returned value is real GPS data.
    """
    try:
        img = Image.open(source)
    except OSError as e:
        raise ValueError(f"無法讀取相片：{e}") from e

    with img:
        exif = img.getexif()
        gps_ifd = exif.get_ifd(_GPS_IFD_TAG) if exif else None
        if not gps_ifd:
            raise ValueError("此相片無 GPS 資訊")

        named = {GPSTAGS.get(k, k): v for k, v in gps_ifd.items()}
        try:
            lat = _dms_to_decimal(named["GPSLatitude"], named["GPSLatitudeRef"])
            lng = _dms_to_decimal(named["GPSLongitude"], named["GPSLongitudeRef"])
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"此相片無 GPS 資訊：{e}") from e

        return round(lat, 6), round(lng, 6)
