---
name: higgsfield-generate
description: 'Generowanie mediów przez Higgsfield API — obraz z promptu (SOUL 2), wideo z promptu (Seedance 2.0 text-to-video) i animacja zdjęcia (Seedance 2.0 image-to-video); czeka na wynik z backoffem i zapisuje pliki lokalnie. Wyzwalacze: "wygeneruj obraz/grafikę", "zrób wideo z promptu", "animuj to zdjęcie", "ożyw obraz", "ile kosztuje wygenerowanie", "higgsfield", "seedance".'
---

# higgsfield-generate

Wszystko przez CLI `higgsfield`, uruchamiane z folderu projektu. Brak komendy albo kluczy
→ skill `higgsfield-setup`.

| Cel | Komenda |
|---|---|
| Obraz | `higgsfield image "<prompt>" [--aspect-ratio 4:3] [--resolution 720p\|1080p] [--batch-size 1\|4] [--seed N] [--style-id UUID] [--no-enhance]` |
| Wideo z promptu | `higgsfield video "<prompt>" [--duration 4-15] [--resolution 480p\|720p\|1080p\|4k] [--aspect-ratio 16:9] [--no-audio]` |
| Animacja obrazu | `higgsfield animate <plik\|https-URL> [--prompt "..."] [--end-image <plik\|URL>] [--duration 4-15] [--resolution ...] [--no-audio]` |

Wspólne flagi: `--estimate` (tylko wycena, nic nie zleca), `--no-wait` (zwraca `request_id`
od razu), `--timeout S`, `--out DIR`, `--force`.

## Przebieg
1. **Koszt**: obraz SOUL 2 ≈ $0.004. Wideo Seedance liczone od tokenów
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

## Obraz wejściowy do `animate`
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
