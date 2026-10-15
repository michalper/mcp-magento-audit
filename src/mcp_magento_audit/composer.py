"""Odczyt stanu projektu Magento z plików Composera.

Czysta warstwa Composerowa — celowo bez niczego specyficznego dla Magento,
żeby dało się ją później wydzielić do narzędzia dla dowolnego projektu PHP
(patrz plan: warstwa Composerowa jako osobny moduł).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class BladProjektu(Exception):
    """Projekt nie istnieje albo nie wygląda na projekt Composerowy."""


@dataclass(frozen=True)
class Pakiet:
    nazwa: str
    wersja: str
    wymaga: dict[str, str] = field(default_factory=dict)
    porzucony: bool = False

    @property
    def wymog_php(self) -> str | None:
        return self.wymaga.get("php")


@dataclass(frozen=True)
class Projekt:
    sciezka: Path
    pakiety: tuple[Pakiet, ...]
    wymog_php_projektu: str | None

    @property
    def wersja_magento(self) -> str | None:
        """Wersja wzięta z produktu Magento, jeśli projekt go w ogóle ma."""
        for kandydat in ("magento/product-community-edition", "magento/product-enterprise-edition"):
            for p in self.pakiety:
                if p.nazwa == kandydat:
                    return p.wersja
        return None

    @property
    def porzucone(self) -> tuple[Pakiet, ...]:
        return tuple(p for p in self.pakiety if p.porzucony)


def _wczytaj_json(sciezka: Path) -> dict[str, Any]:
    try:
        dane: Any = json.loads(sciezka.read_text(encoding="utf-8"))
        if not isinstance(dane, dict):
            raise BladProjektu(f"{sciezka.name} nie zawiera obiektu JSON")
        return dane
    except FileNotFoundError as e:
        raise BladProjektu(f"brak pliku {sciezka.name} w {sciezka.parent}") from e
    except json.JSONDecodeError as e:
        raise BladProjektu(f"{sciezka.name} nie jest poprawnym JSON-em: {e}") from e


def wczytaj_projekt(katalog: str | Path) -> Projekt:
    """Wczytuje composer.json i composer.lock z katalogu projektu."""
    kat = Path(katalog).expanduser().resolve()
    if not kat.is_dir():
        raise BladProjektu(f"{kat} nie jest katalogiem")

    composer = _wczytaj_json(kat / "composer.json")
    lock = _wczytaj_json(kat / "composer.lock")

    porzucone = set(lock.get("abandoned") or {})

    pakiety: list[Pakiet] = []
    for grupa in ("packages", "packages-dev"):
        for wpis in lock.get(grupa) or []:
            nazwa = wpis.get("name", "")
            pakiety.append(
                Pakiet(
                    nazwa=nazwa,
                    wersja=wpis.get("version", "?"),
                    wymaga={k: str(v) for k, v in (wpis.get("require") or {}).items()},
                    porzucony=nazwa in porzucone or bool(wpis.get("abandoned")),
                )
            )

    return Projekt(
        sciezka=kat,
        pakiety=tuple(pakiety),
        wymog_php_projektu=(composer.get("require") or {}).get("php"),
    )
