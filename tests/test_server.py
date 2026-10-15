from pathlib import Path

from mcp_magento_audit.server import stan_projektu

SKLEP = str(Path(__file__).parent / "fixtures" / "sklep")


def test_zwraca_stan_projektu():
    wynik = stan_projektu(SKLEP)
    assert wynik["wersja_magento"] == "2.4.7"
    assert wynik["liczba_pakietow"] == 3
    assert wynik["porzucone"] == ["stary/modul"]


def test_bledna_sciezka_zwraca_blad_a_nie_wyjatek():
    assert "blad" in stan_projektu("/nie/ma/takiego/katalogu")
