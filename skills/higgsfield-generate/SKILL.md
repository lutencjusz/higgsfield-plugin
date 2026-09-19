---
name: higgsfield-generate
description: 'Generowanie mediów przez Higgsfield API — obraz z promptu (SOUL 2), edycja/kompozycja obrazu z referencji (Qwen Image 3, Grok Imagine 2.0, Marketing Studio), wideo z promptu (Seedance 2.0 text-to-video) i animacja zdjęcia (Seedance 2.0 image-to-video); czeka na wynik z backoffem i zapisuje pliki lokalnie. Wyzwalacze: "wygeneruj obraz/grafikę", "wkomponuj osoby w zdjęcie", "edytuj zdjęcie", "połącz zdjęcia", "zrób wideo z promptu", "animuj to zdjęcie", "ożyw obraz", "ile kosztuje wygenerowanie", "higgsfield", "seedance".'
---

# higgsfield-generate

Wszystko przez CLI `higgsfield`, uruchamiane z folderu projektu. Brak komendy albo kluczy
→ skill `higgsfield-setup`.

| Cel | Komenda |
|---|---|
| Obraz | `higgsfield image "<prompt>" [--aspect-ratio 4:3] [--resolution 720p\|1080p] [--batch-size 1\|4] [--seed N] [--style-id UUID] [--no-enhance]` |
| Edycja / kompozycja | `higgsfield edit "<instrukcja>" -i <plik\|URL> [-i ...] [--model qwen\|grok\|marketing] [--resolution 1k\|2k\|4k] [--aspect-ratio 4:3] [--quality low\|medium\|high] [--seed N]` |
| Wideo z promptu | `higgsfield video "<prompt>" [--duration 4-15] [--resolution 480p\|720p\|1080p\|4k] [--aspect-ratio 16:9] [--no-audio]` |
| Animacja obrazu | `higgsfield animate <plik\|https-URL> [--prompt "..."] [--end-image <plik\|URL>] [--duration 4-15] [--resolution ...] [--no-audio]` |

Wspólne flagi: `--estimate` (tylko wycena, nic nie zleca), `--no-wait` (zwraca `request_id`
od razu), `--timeout S`, `--out DIR`, `--force`.

## Przebieg
1. **Koszt**: obraz SOUL 2 ≈ $0.004. Edycja (2 referencje): qwen 1k $0.04 / 2k $0.075,
   grok 1k $0.08 / 2k $0.10, marketing 2k high ≈ $0.30–0.32 / 4k high ≈ $0.48 (cena rośnie z liczbą
   referencji w grok i marketing). `--estimate` przy `edit` nie wysyła zdjęć. Wideo Seedance liczone od tokenów
   (sek × szer × wys × 24 / 1024; $0.014/1k tokenów do 1080p, $0.008 dla 4K): 5 s 720p ≈ $1.51,
   5 s 1080p ≈ $3.40, 15 s 1080p ≈ $10.20. API zwraca dla Seedance tylko opis reguły, więc
   `--estimate` dokłada `local_estimate` (szacunek CLI; wymiary założone, dla `animate` 16:9).
   Przed każdym zleceniem wideo CLI wypisuje „Szacunkowy koszt ≈ X USD" na stderr.
   Przy drogich parametrach najpierw `--estimate` i pokaż kwotę użytkownikowi.
2. Zlecenie → wypisuje postęp na stderr (`[  12 s] in_progress`), na końcu JSON na stdout:
   `request_id`, `status`, `files` (ścieżki lokalne), `outputs` (URL-e CDN, ważne ≥ 7 dni).
3. Pliki lądują w `output_dir` z configu (w trybie projektu: `output/` folderu projektu),
   nazwa `YYYY-MM-DD_<rodzaj>_<request_id[:8]>[_n].<ext>`.
4. Wideo potrafi trwać minuty: przy długich zadaniach użyj `--no-wait`, a potem
   `higgsfield wait <request_id>` (skill `higgsfield-jobs`).

## Kody wyjścia
- `0` gotowe · `2` złe parametry/brak kluczy · `3` **duplikat** — identyczne zlecenie już
  trwa albo jest gotowe; NIE dodawaj `--force` bez zgody użytkownika (każde zlecenie kosztuje)
- `4` limit czasu — zadanie trwa dalej, wznów `higgsfield wait <id>`
- `1` błąd API / `failed` / `nsfw` (oba bez opłaty) / `canceled`. Komunikat zawiera wskazówkę
  (401 klucze, 403 kredyty, 400 limit równoległych zadań, 423/503 model chwilowo niedostępny).

> [!warning] Błąd sieci przy wysyłaniu = status `submit_unknown`
> API nie ma klucza idempotencji, więc CLI **nie ponawia** POST-a. Zanim użyjesz `--force`,
> niech użytkownik sprawdzi historię w https://console.higgsfield.ai.

## Edycja / kompozycja (`edit`)
Modele bez stron w dokumentacji — slugi z `GET /models`, parametry z walidacji `/estimate`.

| `--model` | Endpoint | Referencje | Rozdzielczość | Inne |
|---|---|---|---|---|
| `qwen` (domyślny) | `alibaba/qwen-image-3/edit` | 1–3 | 1k, 2k | `--seed` |
| `grok` | `xai/grok-imagine-image-2.0` | 1–10 | 1k, 2k | `--quality low\|medium`, proporcje `auto` |
| `marketing` | `marketing-studio/image` | 1–16 | 1k, 2k, 4k | `--quality low\|medium\|high`, proporcje `auto` |

- Kolejność `-i` ma znaczenie — w instrukcji odwołuj się do „image 1”, „image 2”…
  (np. image 1 = tło, image 2 = osoby).
- **Wierność twarzy**: najlepiej wypada `marketing` (2k/high). Pomaga dodatkowa referencja
  z ciasnym kadrem samych twarzy i jawne „IDENTITY IS THE TOP PRIORITY…” w promptcie.
  `qwen` jest tani na prototyp, ale przerysowuje twarze. Pominięte parametry = domyślne modelu.
- `nano-banana-pro/edit` istnieje w API, ale na koncie ma status `model_disabled`.

## Obraz wejściowy do `animate` i `edit`
- Plik `.jpg/.jpeg/.png/.webp/.gif` (upload przez presigned URL) albo publiczny `https://`.
- CLI potrzebuje **ścieżki do pliku**. Zdjęcie wklejone do czatu (np. w Cowork) nie zawsze
  jest plikiem w środowisku: najpierw szukaj go w folderze projektu (`input/`, ostatnio
  zmienione obrazy) i w katalogu załączników sesji, jeśli istnieje. Nie znajdziesz → poproś
  użytkownika o zapisanie zdjęcia w `input/` folderu projektu. Nie odtwarzaj obrazu z podglądu.
- Upload wysyła zdjęcie do storage Higgsfield (tymczasowo) — przy zdjęciach prywatnych
  (osoby, dokumenty) upewnij się, że użytkownik się na to godzi.

## Zasady
- Nie wymyślaj parametrów spoza tabeli — CLI waliduje je wg dokumentacji i odrzuci resztę.
- Po wygenerowaniu podaj użytkownikowi ścieżki z `files`.
