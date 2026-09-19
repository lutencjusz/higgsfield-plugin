"""Stałe API zweryfikowane z dokumentacją (docs.higgsfield.ai, stan na 2026-09-19).

Źródłem prawdy są strony modeli (/docs/models/...), NIE openapi.json — ten
nie zawiera Seedance ani SOUL v2.
"""

BASE_URL = "https://api.higgsfield.ai"

# Endpointy generowania (ID bez wiodącego ukośnika, jak w SDK)
IMAGE_ENDPOINT = "higgsfield-ai/soul/v2/standard"
VIDEO_ENDPOINT = "bytedance/seedance-2.0/text-to-video"
ANIMATE_ENDPOINT = "bytedance/seedance-2.0/image-to-video"

SOUL_STYLES_PATH = "/v1/text2image/soul-styles/v2"

# SOUL 2 (/docs/models/soul-2/generate)
IMAGE_ASPECT_RATIOS = ("9:16", "16:9", "4:3", "3:4", "1:1", "2:3", "3:2")
IMAGE_RESOLUTIONS = ("720p", "1080p")
IMAGE_BATCH_SIZES = (1, 4)
IMAGE_SEED_RANGE = (1, 1_000_000)

# Seedance 2.0 (/docs/models/seedance-2/text-to-video, /image-to-video)
VIDEO_RESOLUTIONS = ("480p", "720p", "1080p", "4k")
VIDEO_ASPECT_RATIOS = ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9")
VIDEO_DURATION_RANGE = (4, 15)

# Typy plików do uploadu (/docs/concepts/file-uploads) — tu tylko obrazy
UPLOAD_IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

# Statusy (/docs/concepts/requests)
TERMINAL_STATUSES = ("completed", "failed", "nsfw", "canceled")
ACTIVE_STATUSES = ("queued", "in_progress")
# Statusy lokalne rejestru: przed/po niejednoznacznym POST-cie
LOCAL_SUBMITTING = "submitting"
LOCAL_SUBMIT_UNKNOWN = "submit_unknown"

# Polling (/docs/concepts/polling): start 2 s, x1.5, max 10 s, jitter
POLL_INITIAL = 2.0
POLL_FACTOR = 1.5
POLL_MAX = 10.0
POLL_JITTER = 0.5
POLL_MAX_CONSECUTIVE_ERRORS = 6

# Domyślny limit czasu oczekiwania aplikacji (s) — zależny od rodzaju modelu
DEFAULT_TIMEOUTS = {"image": 300, "video": 1200, "animate": 1200}
