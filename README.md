# mcp-magento-audit

Serwer [MCP](https://modelcontextprotocol.io) dający agentowi AI narzędzia do oceny
projektu Magento 2 / Adobe Commerce w trzech osiach: **zgodność z docelową wersją
PHP i Magento**, **jakość modułów autorskich** i **bezpieczeństwo zależności**.

Odpowiada na pytanie, które w agencjach Magento wraca bez końca:
*„czy możemy podbić tego klienta na nowszą wersję, co to blokuje i od czego zacząć?"*

> **Status: wczesny etap.** Projekt rozwijany po godzinach. Działają narzędzia
> `project_status` i `check_updates`; reszta narzędzi jest w planie i jeszcze nie istnieje.

## Czym to się różni od `composer audit`

`composer audit` i `composer outdated` są wbudowane w Composera i robią swoje dobrze.
Ten serwer celuje w trzy rzeczy, których one nie dają:

1. **Nie widzą `app/code`.** Moduły autorskie nie istnieją na Packagiście, więc mają
   zerowe pokrycie przez bazy podatności — a to właśnie kod pisany przez agencje.
2. **Nie łączą osi.** Nikt nie dostaje jednej odpowiedzi: *ten moduł blokuje
   aktualizację, ma otwarte CVE, jest porzucony przez autora i ma najgorszą złożoność
   w projekcie — wymień go pierwszy.*
3. **Nie agregują po projektach.** Pytanie „które z dwudziestu sklepów da się podbić
   dziś" wymaga spięcia wyników z wielu katalogów.

**Czego ten serwer nie udaje:** nie istnieje czysty zbiór danych „moduł X działa z
Magento 2.4.8". Wyniki są wyprowadzane z deklaracji w `composer.json`, ze skanu kodu
i z not wydawniczych producenta — to narzędzie wspierające decyzję, nie wyrocznia.
Aktualizacja sklepu produkcyjnego wymaga testów, nie samego raportu.

## Instalacja

```bash
git clone <adres-repozytorium>
cd mcp-magento-audit
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Podłączenie do Claude Code

```json
{
  "mcpServers": {
    "magento-audit": {
      "command": "/sciezka/do/mcp-magento-audit/.venv/bin/mcp-magento-audit"
    }
  }
}
```

## Narzędzia

| Narzędzie | Stan | Opis |
|---|---|---|
| `project_status` | **działa** | wersja Magento, wymaganie PHP, liczba pakietów, pakiety porzucone |
| `check_updates` | **działa** | werdykt per pakiet wobec docelowej wersji PHP i Magento |
| `module_risk` | planowane | skan `app/code` pod kątem wycofanych API |
| `fetch_release_notes` | planowane | noty ze źródła producenta, **bez odpowiadania z pamięci modelu** |
| `upgrade_plan` | planowane | uporządkowany plan z kolejnością i blokerami |

## Rozwój

```bash
.venv/bin/python -m pytest        # testy
.venv/bin/ruff check .            # lint
.venv/bin/mypy src                # typy
```

Decyzje architektoniczne zapisujemy w `docs/adr/`.

## Licencja

MIT
