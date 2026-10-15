"""Serwer MCP — narzędzia audytu projektu Magento.

Etap 0 planu: szkielet na oficjalnym SDK + jedno realne narzędzie.
UWAGA: w SDK `mcp` 2.x klasa nazywa się MCPServer (w 1.x było FastMCP).
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from .composer import BladProjektu, wczytaj_projekt

serwer = MCPServer(
    name="mcp-magento-audit",
    instructions=(
        "Audyt projektu Magento: zgodność z docelową wersją PHP i Magento, "
        "jakość modułów autorskich, bezpieczeństwo zależności. "
        "Narzędzia czytają pliki projektu wskazanego przez użytkownika — "
        "nie zgaduj stanu projektu, zawsze wywołaj narzędzie."
    ),
)


@serwer.tool(
    description=(
        "Czyta composer.json i composer.lock wskazanego projektu Magento i zwraca "
        "jego stan: wersję Magento, wymaganie PHP, liczbę pakietów i listę "
        "pakietów porzuconych przez autorów."
    )
)
def stan_projektu(sciezka: str) -> dict[str, Any]:
    """Zwraca podstawowy stan projektu pod ścieżką `sciezka`."""
    try:
        projekt = wczytaj_projekt(sciezka)
    except BladProjektu as e:
        return {"blad": str(e)}

    return {
        "sciezka": str(projekt.sciezka),
        "wersja_magento": projekt.wersja_magento,
        "wymog_php_projektu": projekt.wymog_php_projektu,
        "liczba_pakietow": len(projekt.pakiety),
        "porzucone": [p.nazwa for p in projekt.porzucone],
    }


def main() -> None:
    serwer.run(transport="stdio")


if __name__ == "__main__":
    main()
