"""Constants for pytedee_async."""
API_URL_BASE = "https://api.tedee.com/api/v1.32/"
API_URL_DEVICE = API_URL_BASE + "my/device/"
API_URL_LOCK = API_URL_BASE + "my/lock/"
API_URL_SYNC = API_URL_LOCK + "sync"
API_URL_BRIDGE = API_URL_BASE + "my/bridge/"

API_PATH_UNLOCK = "/operation/unlock"
API_PATH_LOCK = "/operation/lock"
API_PATH_PULL = "/operation/pull"

API_LOCAL_VERSION = "v1.0"
API_LOCAL_PORT = "80"

TIMEOUT = 10
UNLOCK_DELAY = 5
LOCK_DELAY = 5
LOCAL_CALL_MIN_DISTANCE = 1
