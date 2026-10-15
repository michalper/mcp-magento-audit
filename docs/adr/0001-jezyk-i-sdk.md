# ADR 0001: Python i oficjalne SDK MCP

**Data:** 2026-10-15
**Status:** przyjęty

## Kontekst

Serwer MCP do audytu projektów Magento. Autor ma 14 lat w PHP i cztery miesiące
w pełnym Symfony; Pythona uczy się od 2026-10-11. Do wyboru były PHP i Python.

## Decyzja

**Python**, na oficjalnym SDK `mcp` (wersja 2.x).

## Uzasadnienie

- Jeden artefakt zamyka dwie luki w portfolio naraz: brak serwera MCP i brak
  czegokolwiek publicznego w Pythonie. Python wraca jako wymaganie w ofertach
  z obszaru AI engineering.
- Python SDK jest w **Tier 1** oficjalnej klasyfikacji (razem z TypeScriptem, C#,
  Go, Rustem i Ruby). PHP SDK jest w Tier 3 i przed wersją 1.0 — mniej przykładów,
  mniej stabilne API.
- Domena pozostaje Magento, więc artefakt pokazuje jednocześnie nowy język i wiedzę
  dziedzinową z czterech lat pracy na platformie.

## Konsekwencje

- Narzut na naukę: pierwsze etapy pójdą wolniej, niż poszłyby w PHP.
- **Warunek twardy: autor musi rozumieć każdą linię tego kodu.** Projekt ma być
  dowodem umiejętności na rozmowie kwalifikacyjnej, a nie wydrukiem z generatora.
- `composer.lock` to zwykły JSON, więc brak PHP po stronie implementacji niczego
  nie utrudnia.

## Pułapka do zapamiętania

W SDK `mcp` 2.x klasa `FastMCP` została przemianowana na `MCPServer`
(`from mcp.server.mcpserver import MCPServer`). Kod i przykłady z wersji 1.x
nie zadziałają. API zostało sprawdzone w zainstalowanej wersji, a nie przyjęte
z pamięci — to ta sama zasada, którą ten serwer ma egzekwować wobec modelu.
