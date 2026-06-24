"""
tests/test_geo_utils.py
--------------------------
Valide le point-in-polygon réel (Shapely) sur les géométries officielles des
arrondissements parisiens, avec des coordonnées de monuments connus.

Lancer avec : pytest tests/test_geo_utils.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingestion"))

from geo_utils import find_arrondissement  # noqa: E402


def test_known_landmarks_resolve_to_correct_arrondissement():
    cases = [
        ("Tour Eiffel", 2.2945, 48.8584, 7),
        ("Notre-Dame de Paris", 2.3499, 48.8530, 4),
        ("Sacré-Cœur", 2.3431, 48.8867, 18),
        ("Jardin du Luxembourg", 2.3372, 48.8462, 6),
        ("Bois de Vincennes", 2.4336, 48.8290, 12),
    ]
    for name, lon, lat, expected in cases:
        found = find_arrondissement(lon, lat)
        assert found == expected, f"{name} : attendu {expected}, trouvé {found}"


def test_point_outside_paris_returns_none():
    # Versailles, hors de Paris.
    assert find_arrondissement(2.1301, 48.8049) is None


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
