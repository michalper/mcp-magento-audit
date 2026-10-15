from pathlib import Path

import pytest

from mcp_magento_audit.composer import BladProjektu, wczytaj_projekt

SKLEP = Path(__file__).parent / "fixtures" / "sklep"


def test_czyta_wersje_magento_i_wymog_php():
    projekt = wczytaj_projekt(SKLEP)
    assert projekt.wersja_magento == "2.4.7"
    assert projekt.wymog_php_projektu == "~8.2.0||~8.3.0"


def test_liczy_pakiety_z_obu_grup():
    assert len(wczytaj_projekt(SKLEP).pakiety) == 3


def test_rozpoznaje_pakiet_porzucony():
    porzucone = [p.nazwa for p in wczytaj_projekt(SKLEP).porzucone]
    assert porzucone == ["stary/modul"]


def test_wymog_php_pakietu():
    pakiet = next(p for p in wczytaj_projekt(SKLEP).pakiety if p.nazwa == "stary/modul")
    assert pakiet.wymog_php == "^7.4"


def test_brak_katalogu_daje_czytelny_blad():
    with pytest.raises(BladProjektu, match="nie jest katalogiem"):
        wczytaj_projekt("/nie/ma/takiego/katalogu")


def test_katalog_bez_composera_daje_czytelny_blad(tmp_path):
    with pytest.raises(BladProjektu, match="brak pliku composer.json"):
        wczytaj_projekt(tmp_path)
