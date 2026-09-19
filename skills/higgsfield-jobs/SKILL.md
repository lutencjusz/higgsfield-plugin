---
name: higgsfield-jobs
description: 'Zarządzanie zleceniami Higgsfield — lista zleceń z lokalnego rejestru, status, wznawianie czekania i pobranie wyników po request_id, anulowanie zleceń w kolejce. Wyzwalacze: "czy wideo z higgsfield już gotowe", "status zlecenia higgsfield", "pobierz wynik higgsfield", "anuluj generowanie", "co się generuje".'
---

# higgsfield-jobs

- Lista: `higgsfield jobs [--active] [--limit 20]` — JSON z rejestru `jobs.json` obok aktywnego
  configu (`.higgsfield/` projektu albo `~/.higgsfield/`) — uruchamiaj z folderu projektu.
- Status (jedno zapytanie): `higgsfield status <request_id>`.
- Czekaj + pobierz pliki: `higgsfield wait <request_id> [--timeout S] [--out DIR]` —
  polling 2 s ×1.5 do 10 s z jitterem. Działa też na zleceniu już `completed`
  (ponowne pobranie plików, np. po błędzie sieci).
- Anuluj: `higgsfield cancel <request_id>` — tylko w statusie `queued` (zwrot kredytów);
  gdy przetwarzanie ruszyło, API odmawia.

## Zasady
- Komendy działają **tylko dla request_id z lokalnego rejestru** (zleconych tym narzędziem) —
  obce ID są odrzucane z kodem 2. To celowe: rejestr jest zapisem własności zleceń.
- Statusy: `queued`, `in_progress` (trwa) · `completed`, `failed`, `nsfw`, `canceled` (koniec) ·
  lokalne: `submitting`, `submit_unknown` (POST mógł przejść — sprawdź konsolę), `rejected`,
  `upload_failed`.
- URL-e wyników wygasają po ~7 dniach — pobierz przez `wait`, zanim znikną.
