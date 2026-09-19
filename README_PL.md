# higgsfield-plugin

Plugin Claude Code + CLI `higgsfield` do [Higgsfield API](https://docs.higgsfield.ai):

| Komenda | Model / endpoint |
|---|---|
| `higgsfield image` | SOUL 2 — `higgsfield-ai/soul/v2/standard` |
| `higgsfield edit` | Qwen Image 3 `alibaba/qwen-image-3/edit` · Grok Imagine 2.0 `xai/grok-imagine-image-2.0` · Marketing Studio `marketing-studio/image` |
| `higgsfield video` | Seedance 2.0 — `bytedance/seedance-2.0/text-to-video` |
| `higgsfield animate` | Seedance 2.0 — `bytedance/seedance-2.0/image-to-video` |

Skille: `higgsfield-setup`, `higgsfield-generate`, `higgsfield-jobs`.

## Instalacja

```powershell
uv tool install --editable C:\claude\Higgsfield
higgsfield setup --output-dir C:\claude\Higgsfield\output   # key ID + secret (ukryty prompt)
higgsfield check                                            # klucze + wycena 3 endpointów, 0 kredytów
```

Poświadczenia: `~/.higgsfield/config.json` (poza repo) albo zmienne `HF_API_KEY_ID` /
`HF_API_KEY_SECRET` (mają pierwszeństwo). Wzór: `config.example.json`.

## Cowork (Claude Desktop)

1. Zainstaluj plugin z pliku `dist/higgsfield-plugin.plugin` (podgląd w czacie → przycisk instalacji).
2. Jako folder projektu wskaż `C:\claude\Higgsfield` — zawiera `.higgsfield/config.json`
   (klucze, `"output_dir": "output"`), `input/` na zdjęcia i `output/` na wyniki.
   Katalog domowy Windowsa (`~/.higgsfield`) jest w Cowork niewidoczny.
3. Poproś „sprawdź higgsfield” — skill `higgsfield-setup` zainstaluje CLI w venv
   (`~/.higgsfield-venv`) z kodu pluginu i uruchomi `higgsfield check`.
4. Zdjęcia do animacji wrzucaj do `input/` (wklejone do czatu nie zawsze są plikiem).

Wymaga dostępu sieci do `pypi.org`/`files.pythonhosted.org` (instalacja), `api.higgsfield.ai`
i CDN wyników (`*.cloudfront.net`).

Szukanie configu: `HF_API_KEY_ID`/`HF_API_KEY_SECRET` → `HF_CONFIG_DIR` → `.higgsfield/`
w bieżącym folderze lub nadrzędnym (poniżej katalogu domowego) → `~/.higgsfield/`.
`higgsfield setup --local` zapisuje config w `./.higgsfield/`.

## Użycie

```powershell
higgsfield video "A cinematic tracking shot along a sunlit coastal road" --estimate
higgsfield video "A cinematic tracking shot along a sunlit coastal road" --duration 5
higgsfield image "Editorial portrait in soft daylight" --aspect-ratio 3:4 --resolution 1080p
higgsfield animate .\foto.jpg --prompt "delikatny wiatr, kamera powoli odjeżdża"
higgsfield edit "Add the couple from image 2 to the beach in image 1" -i .\plaza.jpg -i .\para.jpg --model marketing --resolution 2k --quality high --estimate
higgsfield video "..." --no-wait ; higgsfield wait <request_id>
higgsfield jobs --active
```

## Jak to działa

- **SDK** `higgsfield-client` 0.2.x: klient HTTP z nagłówkiem `Authorization: Key id:secret`,
  upload presigned URL, cancel. Klucz przekazywany jawnie (SDK sam szuka innych zmiennych).
- **Bez ponowień POST** — generowanie nie ma klucza idempotencji; domyślny retry SDK
  (5xx/429) mógłby zlecić i obciążyć dwa razy. Błąd sieci przy POST → status
  `submit_unknown`, bez automatycznego ponowienia.
- **Polling** wg dokumentacji: 2 s, ×1.5, maks. 10 s, jitter 0–0.5 s, limit czasu
  (obraz 300 s, wideo 1200 s). 5xx/sieć przy GET → ponowienie; 401/404 → stop.
  Stany końcowe: `completed`, `failed`, `nsfw`, `canceled`.
- **Rejestr** `~/.higgsfield/jobs.json`: `request_id` zapisywany od razu po przyjęciu,
  parametry, status, `X-Correlation-ID`, URL-e i pliki. Blokuje duplikaty (odcisk
  endpoint+parametry; dla plików — SHA-256 treści), pozwala wznowić `wait` i ogranicza
  `status/wait/cancel` do własnych zleceń.
- **Pobieranie** osobnym klientem bez nagłówka `Authorization` do `output_dir`
  (API trzyma wyniki min. 7 dni).
- **Edycja** (`edit`): modele bez stron w dokumentacji — slugi z `GET /models`, limity
  (qwen 1–3, grok 1–10, marketing 1–16 referencji) i dozwolone wartości z walidacji
  `/estimate`. `--estimate` przy `edit` nie wysyła zdjęć (wycena zależy od liczby referencji).
- **Webhooki** (`hf_webhook`) nie są używane — CLI nie ma publicznego endpointu HTTPS.

## Testy

```powershell
uv venv .venv ; uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
.venv\Scripts\python.exe -m pytest -q
```

Testy działają offline: prawdziwe SDK z `httpx.MockTransport`, zegar polling-u wstrzykiwany.
