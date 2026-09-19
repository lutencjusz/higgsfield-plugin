import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from . import config, const, params, pricing
from .client import HfApiError, HfNetworkError, HiggsfieldApi
from .download import download_outputs, output_urls
from .jobs import JobStore, JobStoreError
from .polling import PollTimeout, poll_until_terminal

EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_DUPLICATE = 3
EXIT_TIMEOUT = 4

# Publiczny obraz testowy — tylko do `check` (estimate image-to-video, bez generowania)
_CHECK_IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/a/a9/Example.jpg"


class CliError(Exception):
    def __init__(self, message, code=EXIT_ERROR):
        super().__init__(message)
        self.code = code


def _api() -> HiggsfieldApi:
    return HiggsfieldApi(config.load_credentials())


def _store() -> JobStore:
    return JobStore(config.jobs_file())


def _print(obj, as_json):
    if as_json or not isinstance(obj, str):
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        print(obj)


def _progress(msg):
    print(msg, file=sys.stderr, flush=True)


def _summary(job: dict) -> dict:
    keys = ("request_id", "kind", "status", "error", "files", "outputs", "correlation_id", "created_at")
    return {k: job.get(k) for k in keys}


def _owned_job(store: JobStore, request_id: str) -> dict:
    """Egzekwuje własność: operujemy tylko na zleceniach z lokalnego rejestru."""
    if not params.is_uuid(request_id):
        raise CliError(f"To nie jest poprawny request_id (UUID): {request_id}", EXIT_USAGE)
    job = store.get(request_id)
    if job is None:
        raise CliError(
            f"request_id {request_id} nie występuje w rejestrze {store.path} — "
            "nie zostało zlecone tym narzędziem, więc go nie obsługuję.", EXIT_USAGE)
    return job


# --- setup / check / styles -------------------------------------------------

def cmd_setup(args):
    cfg = {} if args.local and not config.config_file().is_relative_to(Path.cwd()) else config.load_config()
    key_id = os.environ.get(config.ENV_KEY_ID) or input("HF API key ID: ").strip()
    secret = os.environ.get(config.ENV_KEY_SECRET) or getpass.getpass("HF API key secret: ").strip()
    if not key_id or not secret:
        raise CliError("Key ID i secret są wymagane.", EXIT_USAGE)
    cfg.update(api_key_id=key_id, api_key_secret=secret)
    if args.output_dir:
        cfg["output_dir"] = args.output_dir
    path = config.save_config(cfg, local=args.local)
    print(f"Zapisano poświadczenia w {path}. Sprawdź: `higgsfield check`.")


def cmd_check(args):
    """Klucze + dostępność endpointów przez /estimate — nic nie generuje, 0 kredytów."""
    api = _api()
    report = {"credentials": "ok", "soul_styles": "ok", "endpoints": {}}
    try:
        api.soul_styles()
    except HfNetworkError as e:
        raise CliError(f"Brak połączenia z API: {e}") from e
    except HfApiError as e:
        if e.status_code == 401:
            report["credentials"] = report["soul_styles"] = str(e)
            _print(report, True)
            raise CliError("Poświadczenia nie działają — `higgsfield setup`.") from e
        # 403/404/423 na endpoincie stylów to nie są złe klucze — sprawdzamy dalej
        report["soul_styles"] = str(e)
    probes = {
        const.IMAGE_ENDPOINT: params.build_image_args("check"),
        const.VIDEO_ENDPOINT: params.build_video_args("check"),
        const.ANIMATE_ENDPOINT: params.build_animate_args(_CHECK_IMAGE_URL),
    }
    for endpoint, body in probes.items():
        try:
            report["endpoints"][endpoint] = {"ok": True, "estimate": api.estimate(endpoint, body)}
        except (HfApiError, HfNetworkError) as e:
            report["endpoints"][endpoint] = {"ok": False, "error": str(e)}
    report["output_dir"] = str(config.output_dir())
    report["note"] = f"Próba image-to-video używa zewnętrznego obrazu {_CHECK_IMAGE_URL}."
    _print(report, True)
    if not all(v["ok"] for v in report["endpoints"].values()):
        raise CliError("Część endpointów niedostępna dla tego konta (szczegóły wyżej).")


def cmd_styles(args):
    styles = _api().soul_styles()
    if args.json:
        _print(styles, True)
    else:
        for s in styles:
            print(f"{s.get('id')}  {s.get('name')}")


# --- generowanie -------------------------------------------------------------

def _duplicate_message(dup: dict) -> str:
    if dup["request_id"] is None:
        return (f"W rejestrze jest identyczne zlecenie bez request_id (status={dup['status']}, "
                f"{dup['created_at']}) — wysyłka została przerwana albo jej wynik jest nieznany. "
                "Sprawdź historię w https://console.higgsfield.ai; jeśli nic tam nie ma, powtórz z --force.")
    return (f"Identyczne zlecenie już istnieje (request_id={dup['request_id']}, status={dup['status']}). "
            "Nie wysyłam drugi raz — każde zlecenie kosztuje kredyty. "
            f"Wyniki: `higgsfield wait {dup['request_id']}`; świadome powtórzenie: --force.")


def _generate(args, *, kind, endpoint, fp_args, resolve_args, estimate_args=None):
    """Wspólny przebieg: odcisk -> [estimate] -> rezerwacja (duplikaty) -> upload -> POST -> czekanie."""
    api = _api()
    seedance = endpoint in (const.VIDEO_ENDPOINT, const.ANIMATE_ENDPOINT)
    if args.estimate:
        body = estimate_args or resolve_args(api)
        result = api.estimate(endpoint, body)
        if seedance and result.get("type") == "description":
            result["local_estimate"] = pricing.seedance_estimate(body)
        _print(result, True)
        return
    if seedance:
        cost = pricing.seedance_estimate(fp_args)
        _progress(f"Szacunkowy koszt: ≈ {cost['approx_usd']:.2f} USD "
                  f"({cost['duration']} s, {cost['assumed_size']})")
    store = _store()
    fp = params.fingerprint(endpoint, fp_args)
    reserved = store.reserve(kind=kind, endpoint=endpoint, arguments=fp_args, fp=fp, force=args.force)
    if "duplicate" in reserved:
        raise CliError(_duplicate_message(reserved["duplicate"]), EXIT_DUPLICATE)
    job = reserved["job"]

    try:
        arguments = resolve_args(api)
    except (HfApiError, HfNetworkError, KeyboardInterrupt) as e:
        store.update(job["id"], status="upload_failed", error=str(e) or type(e).__name__)
        raise CliError(f"Upload obrazu nie powiódł się: {e or 'przerwano'}") from e

    try:
        resp = api.submit(endpoint, arguments)
    except (HfNetworkError, KeyboardInterrupt) as e:
        store.update(job["id"], status=const.LOCAL_SUBMIT_UNKNOWN, arguments=arguments,
                     error=str(e) or type(e).__name__)
        raise CliError(
            f"Wysyłka przerwana ({e or 'Ctrl-C'}). NIE WIADOMO, czy zlecenie przyjęto — nie ponawiam "
            "automatycznie (API nie ma klucza idempotencji). Sprawdź historię w "
            "https://console.higgsfield.ai; ponowienie tylko świadomie z --force.") from e
    except HfApiError as e:
        store.update(job["id"], status="rejected", arguments=arguments, error=str(e),
                     correlation_id=e.correlation_id)
        raise CliError(str(e)) from e

    job = store.update(job["id"], request_id=resp["request_id"], status=resp.get("status", "queued"),
                       arguments=arguments, correlation_id=resp.get("correlation_id"))
    _progress(f"Przyjęto: request_id={job['request_id']} ({kind}, {endpoint})")
    if args.no_wait:
        _print(_summary(job), True)
        return
    _wait(api, store, job, timeout=args.timeout or const.DEFAULT_TIMEOUTS[kind], out=args.out)


def _wait(api, store, job, *, timeout, out):
    rid = job["request_id"]
    seen = {"status": job["status"]}

    def on_update(data, elapsed):
        if data.get("status") != seen["status"]:
            seen["status"] = data.get("status")
            store.update(job["id"], status=seen["status"])
            _progress(f"[{elapsed:5.0f} s] {seen['status']}")

    try:
        result = poll_until_terminal(lambda: api.status(rid), timeout=timeout, on_update=on_update)
    except PollTimeout as e:
        raise CliError(f"{e}. Zadanie dalej trwa po stronie API — wznów: `higgsfield wait {rid}`.",
                       EXIT_TIMEOUT) from e
    except KeyboardInterrupt:
        raise CliError(f"Przerwano czekanie. Zadanie trwa dalej — wznów: `higgsfield wait {rid}`.", 130)
    except (HfApiError, HfNetworkError) as e:
        raise CliError(f"Nie udało się odczytać statusu: {e}. Wznów: `higgsfield wait {rid}`.") from e

    status = result["status"]
    job = store.update(job["id"], status=status, error=result.get("error"))
    if status == "nsfw":
        raise CliError(f"Moderacja odrzuciła treść (nsfw) — bez opłaty. request_id={rid}")
    if status == "failed":
        raise CliError(f"Generowanie nie powiodło się: {result.get('error') or 'brak szczegółów'} "
                       f"— bez opłaty. request_id={rid}")
    if status == "canceled":
        raise CliError(f"Zlecenie anulowane. request_id={rid}")

    urls = output_urls(result)
    job = store.update(job["id"], outputs=urls)
    try:
        files = download_outputs(urls, config.output_dir(out), kind=job["kind"], request_id=rid)
    except Exception as e:  # sieć/dysk: URL-e są w rejestrze, można ponowić
        raise CliError(f"Wynik gotowy, ale pobieranie nie powiodło się ({e}). URL-e (ważne ≥7 dni): "
                       f"{urls}. Ponów: `higgsfield wait {rid}`.") from e
    job = store.update(job["id"], files=files)
    _print(_summary(job), True)


def cmd_image(args):
    a = params.build_image_args(args.prompt, aspect_ratio=args.aspect_ratio, resolution=args.resolution,
                                batch_size=args.batch_size, enhance_prompt=not args.no_enhance,
                                seed=args.seed, style_id=args.style_id)
    _generate(args, kind="image", endpoint=const.IMAGE_ENDPOINT, fp_args=a, resolve_args=lambda api: a)


def cmd_video(args):
    a = params.build_video_args(args.prompt, duration=args.duration, resolution=args.resolution,
                                aspect_ratio=args.aspect_ratio, generate_audio=not args.no_audio)
    _generate(args, kind="video", endpoint=const.VIDEO_ENDPOINT, fp_args=a, resolve_args=lambda api: a)


def _to_public_url(api, ref):
    if ref is None or params.is_remote(ref):
        return ref
    path, ctype = params.check_local_image(ref)
    _progress(f"Upload {path.name} ({ctype})...")
    return api.upload(path.read_bytes(), ctype)


def cmd_animate(args):
    opts = params.animate_options(prompt=args.prompt, duration=args.duration,
                                  resolution=args.resolution, generate_audio=not args.no_audio)
    for ref in (args.image, args.end_image):
        if ref is not None:
            params.check_image_ref(ref)
    fp_args = {**opts, "image": params.input_ref(args.image), "end_image": params.input_ref(args.end_image)}

    def resolve(api):
        return params.build_animate_args(_to_public_url(api, args.image),
                                         end_image_url=_to_public_url(api, args.end_image), **opts)

    def placeholder(ref):  # wycena zależy od długości/rozdzielczości — bez wysyłania zdjęcia
        return None if ref is None else ref if params.is_remote(ref) else _CHECK_IMAGE_URL

    estimate = params.build_animate_args(placeholder(args.image),
                                         end_image_url=placeholder(args.end_image), **opts)
    _generate(args, kind="animate", endpoint=const.ANIMATE_ENDPOINT, fp_args=fp_args,
              resolve_args=resolve, estimate_args=estimate)


# --- zlecenia ------------------------------------------------------------------

def cmd_status(args):
    store = _store()
    job = _owned_job(store, args.request_id)
    data = _api().status(args.request_id)
    job = store.update(job["id"], status=data.get("status", job["status"]), error=data.get("error"))
    _print({**_summary(job), "api": data}, True)


def cmd_wait(args):
    store = _store()
    job = _owned_job(store, args.request_id)
    _wait(_api(), store, job, timeout=args.timeout or const.DEFAULT_TIMEOUTS.get(job["kind"], 1200), out=args.out)


def cmd_cancel(args):
    store = _store()
    job = _owned_job(store, args.request_id)
    try:
        _api().cancel(args.request_id)
    except HfApiError as e:
        if e.status_code == 400:
            raise CliError("Nie da się anulować — przetwarzanie już ruszyło (anulować można tylko 'queued').") from e
        raise CliError(str(e)) from e
    job = store.update(job["id"], status="canceled")
    _print(_summary(job), True)


def cmd_jobs(args):
    jobs = _store().all()
    if args.active:
        live = (*const.ACTIVE_STATUSES, const.LOCAL_SUBMITTING, const.LOCAL_SUBMIT_UNKNOWN)
        jobs = [j for j in jobs if j["status"] in live]
    _print([_summary(j) for j in jobs[-args.limit:]], True)


# --- parser --------------------------------------------------------------------

def _gen_flags(p, kind):
    p.add_argument("--no-wait", action="store_true", help="tylko zleć, zwróć request_id")
    p.add_argument("--timeout", type=int, help=f"limit czekania w s (domyślnie {const.DEFAULT_TIMEOUTS[kind]})")
    p.add_argument("--estimate", action="store_true", help="tylko wycena (kredyty/USD), bez generowania")
    p.add_argument("--force", action="store_true", help="wyślij mimo identycznego zlecenia w rejestrze")
    p.add_argument("--out", help="katalog na wyniki (nadpisuje output_dir z configu)")


def build_parser():
    p = argparse.ArgumentParser(prog="higgsfield", description="Higgsfield API: obrazy i wideo")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("setup", help="zapisz poświadczenia (~/.higgsfield/ albo ./.higgsfield/ z --local)")
    s.add_argument("--output-dir", help="domyślny katalog na wyniki (względny = od folderu projektu)")
    s.add_argument("--local", action="store_true",
                   help="zapisz w ./.higgsfield/ bieżącego folderu (tryb projektu, np. Cowork)")
    s.set_defaults(func=cmd_setup)
    sub.add_parser("check", help="sprawdź klucze i dostępność endpointów (bez kosztów)").set_defaults(func=cmd_check)
    s = sub.add_parser("styles", help="lista stylów SOUL (style_id)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_styles)

    s = sub.add_parser("image", help="obraz z promptu (SOUL 2)")
    s.add_argument("prompt")
    s.add_argument("--aspect-ratio", default="4:3", choices=const.IMAGE_ASPECT_RATIOS)
    s.add_argument("--resolution", default="720p", choices=const.IMAGE_RESOLUTIONS)
    s.add_argument("--batch-size", type=int, default=1, choices=const.IMAGE_BATCH_SIZES)
    s.add_argument("--seed", type=int)
    s.add_argument("--style-id")
    s.add_argument("--no-enhance", action="store_true", help="wyłącz ulepszanie promptu")
    _gen_flags(s, "image")
    s.set_defaults(func=cmd_image)

    s = sub.add_parser("video", help="wideo z promptu (Seedance 2.0 text-to-video)")
    s.add_argument("prompt")
    s.add_argument("--duration", type=int, default=5, help="4–15 s")
    s.add_argument("--resolution", default="720p", choices=const.VIDEO_RESOLUTIONS)
    s.add_argument("--aspect-ratio", default="16:9", choices=const.VIDEO_ASPECT_RATIOS)
    s.add_argument("--no-audio", action="store_true")
    _gen_flags(s, "video")
    s.set_defaults(func=cmd_video)

    s = sub.add_parser("animate", help="animacja obrazu (Seedance 2.0 image-to-video)")
    s.add_argument("image", help="plik lokalny (jpg/png/webp/gif) albo URL https://")
    s.add_argument("--prompt")
    s.add_argument("--end-image", help="opcjonalna ostatnia klatka (plik albo URL)")
    s.add_argument("--duration", type=int, default=5, help="4–15 s")
    s.add_argument("--resolution", default="720p", choices=const.VIDEO_RESOLUTIONS)
    s.add_argument("--no-audio", action="store_true")
    _gen_flags(s, "animate")
    s.set_defaults(func=cmd_animate)

    s = sub.add_parser("status", help="jednorazowy odczyt statusu zlecenia")
    s.add_argument("request_id")
    s.set_defaults(func=cmd_status)
    s = sub.add_parser("wait", help="czekaj na wynik i pobierz pliki (wznawianie)")
    s.add_argument("request_id")
    s.add_argument("--timeout", type=int)
    s.add_argument("--out")
    s.set_defaults(func=cmd_wait)
    s = sub.add_parser("cancel", help="anuluj zlecenie w kolejce")
    s.add_argument("request_id")
    s.set_defaults(func=cmd_cancel)
    s = sub.add_parser("jobs", help="lista zleceń z lokalnego rejestru")
    s.add_argument("--active", action="store_true")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_jobs)
    return p


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except params.ValidationError as e:
        _progress(f"Błąd parametrów: {e}")
        return EXIT_USAGE
    except CliError as e:
        _progress(str(e))
        return e.code
    except (config.ConfigError, JobStoreError) as e:
        _progress(str(e))
        return EXIT_USAGE
    except (HfApiError, HfNetworkError) as e:
        _progress(str(e))
        return EXIT_ERROR
    return 0


if __name__ == "__main__":
    sys.exit(main())
