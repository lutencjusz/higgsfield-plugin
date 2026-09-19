---
name: higgsfield-setup
description: 'Instalacja i konfiguracja pluginu Higgsfield (Claude Code i Cowork) — instaluje CLI `higgsfield`, konfiguruje klucze API poza repo i weryfikuje dostęp do endpointów bez wydawania kredytów. Używaj także, gdy komenda `higgsfield` nie istnieje. Wyzwalacze: "skonfiguruj higgsfield", "dodaj klucz higgsfield", "sprawdź połączenie z higgsfield", "czy higgsfield działa", "higgsfield: command not found".'
---

# higgsfield-setup

## 1. CLI — sprawdź, zanim cokolwiek zainstalujesz

`command -v higgsfield` (Windows: `where higgsfield`). Jest → przejdź do kroku 2.

Brak → zainstaluj z kodu **tego pluginu**. Katalog główny pluginu (`<ROOT>`) to dwa poziomy
nad katalogiem tego skilla (zawiera `pyproject.toml` i `src/higgsfield_cli/`).

- **Windows / Claude Code**: `uv tool install --editable <ROOT>` (w Git Bash ścieżki z `/`).
- **Linux, w tym Cowork** — venv, bo systemowy pip bywa zablokowany (PEP 668):

  ```bash
  python3 -m venv ~/.higgsfield-venv
  ~/.higgsfield-venv/bin/pip install -q "<ROOT>"
  mkdir -p ~/.local/bin && ln -sf ~/.higgsfield-venv/bin/higgsfield ~/.local/bin/higgsfield
  ```

  Jeśli `~/.local/bin` nie jest w `PATH`, wywołuj `~/.higgsfield-venv/bin/higgsfield`.
  Instalacja pobiera `higgsfield-client` i `httpx` z PyPI — gdy sieć to blokuje, zgłoś
  użytkownikowi, że środowisko musi dopuszczać `pypi.org` i `files.pythonhosted.org`.
  Bez instalacji (gdy zależności już są): `PYTHONPATH=<ROOT>/src python3 -m higgsfield_cli ...`.

## 2. Klucze — gdzie CLI ich szuka (pierwszy trafiony)

1. Zmienne `HF_API_KEY_ID` + `HF_API_KEY_SECRET`.
2. `HF_CONFIG_DIR/config.json`.
3. **`.higgsfield/config.json` w bieżącym folderze lub nadrzędnym** (tryb projektu).
4. `~/.higgsfield/config.json`.

**W Cowork** katalog domowy Windowsa jest niewidoczny — użyj trybu projektu: folder
projektu musi zawierać `.higgsfield/config.json`:

```json
{ "api_key_id": "<ID>", "api_key_secret": "<sekret>", "output_dir": "output" }
```

Względny `output_dir` liczy się od folderu projektu. Komendy uruchamiaj z folderu
projektu (albo podfolderu). Jeśli pliku nie ma: poproś użytkownika, żeby go utworzył
sam (np. skopiował z `~/.higgsfield/config.json` i zmienił `output_dir` na `output`)
albo uruchomił w folderze projektu `higgsfield setup --local --output-dir output`.

## 3. Weryfikacja

`higgsfield check` — klucze (lista stylów SOUL) + wycena 3 endpointów. **0 kredytów.**
- `HTTP 401` → złe klucze.
- `Brak połączenia z API` → sieć środowiska blokuje `api.higgsfield.ai` (Cowork: dopuść
  domenę w ustawieniach sieci). Pobieranie wyników wymaga też CDN (`*.cloudfront.net`).
- `ok: false` przy endpoincie → model niedostępny dla konta.

## Zasady
- Sekretu nie wypisuj, nie przekazuj w argumentach komend i nie proś o wklejenie go do czatu.
- `.higgsfield/` nigdy nie trafia do gita ani do vaultu Obsidian.
