# Constants and configuration for Vocab Flow Ultra.

DEFAULT_UPLOADER_ID = "1000"
APP_RELEASE_CHANNEL = "stable-anki-instant-dict"
MIN_RANDOM_ID = 100000
MAX_RANDOM_ID = 999999
REQUEST_TIMEOUT_SECONDS = 15
DEEPSEEK_REQUEST_TIMEOUT_SECONDS = 120
IOS_RESUME_RELOAD_AFTER_SECONDS = 180
IOS_BROWSER_RESUME_RELOAD_AFTER_SECONDS = 600
MAX_PREVIEW_CARDS = 10
BEIJING_TIMEZONE_OFFSET = 8
MAX_UPLOAD_MB = 200
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
QUICK_LOOKUP_CACHE_MAX = 100
QUICK_LOOKUP_CACHE_VERSION = "v10"
SIMPLE_LOOKUP_CACHE_VERSION = "v1"

# Temp .apkg files: subdir under system temp, cleanup files older than this
APKG_TEMP_SUBDIR = "vocabflow_apkg"
APKG_CLEANUP_MAX_AGE_SECONDS = 24 * 3600  # 24 hours

MIN_WORD_LENGTH = 2
MAX_WORD_LENGTH = 25

AI_BATCH_SIZE = 10
MAX_AUTO_LIMIT = 250
AI_TOPIC_WORDLIST_MAX = 50
AI_WORD_SELECTION_INPUT_LIMIT = 800
AI_WORD_SELECTION_MAX_OUTPUT = 250
AI_CARD_EXAMPLE_COUNT_MIN = 1
AI_CARD_EXAMPLE_COUNT_MAX = 3
AI_CARD_EXAMPLE_COUNT_DEFAULT = 1
DEEPSEEK_BASE_URL_DEFAULT = "https://api.deepseek.com"
OPENAI_MODEL_DEFAULT = "gpt-4o-mini"
DEEPSEEK_MODEL_DEFAULT = "deepseek-chat"
MAX_RETRIES = 3

EXTRACTION_ERROR_PREFIX = "__VOCABFLOW_EXTRACTION_ERROR__:"

TTS_CONCURRENCY = 3
TTS_RETRY_ATTEMPTS = 3
TTS_TASK_TIMEOUT_SECONDS = 25
TTS_TEXT_MAX_CHARS = 240
MIN_AUDIO_FILE_SIZE = 100

ANKI_MODEL_ID = 1842957302
ANKI_MODEL_ID_BASE = 1842957600
ANKI_ETYMOLOGY_FONT_SIZE_PX = 18

DEFAULT_CARD_TEMPLATE = "word_front"
DEFAULT_CARD_AUDIO_MODE = "word_and_example"
CARD_AUDIO_MODES = {
    "none": {
        "label": "不生成音频",
        "description": "最快，只生成文字卡片。",
    },
    "word": {
        "label": "只生成单词音频",
        "description": "速度更快，适合大量单词。",
    },
    "word_and_example": {
        "label": "单词 + 例句音频",
        "description": "信息最完整，但大量单词会更慢。",
    },
}
CARD_TEMPLATES = {
    "word_front": {
        "label": "1. 正面单词",
        "description": "正面显示单词；反面显示中英释义、中英例句。",
    },
    "example_front": {
        "label": "2. 正面例句（单词加粗）",
        "description": "正面显示英文例句并加粗目标词；反面显示中英释义、中英例句。",
    },
    "definition_front": {
        "label": "3. 英文释义 + 词性 + 首字母提示",
        "description": "正面显示英文释义、词性和首字母提示；反面显示单词、中文释义和例句。",
    },
}

ENCODING_PRIORITY = ['utf-8', 'gb18030', 'latin-1']
VOCAB_PROJECT_SOURCE = "NGSL 项目"
VOCAB_PROJECT_NAME = "NGSL+SFI 31K"
VOCAB_PROJECT_FILE = "ngsl_sfi_31k.csv"
VOCAB_PROJECT_MAX_RANK = 31237
VOCAB_BASE_RANK_CUTOFFS = (3000, 5000, 8000, 10000, 12000, 15000, 20000)

DEFAULT_SESSION_STATE = {
    'uploader_id': DEFAULT_UPLOADER_ID,
    'anki_input_text': "",
    'anki_pkg_name': "",
    'url_input_key': "",
}

VOICE_MAP = {
    "👩 美音女声": "en-US-JennyNeural",
    "👨 美音男声": "en-US-ChristopherNeural",
    "👩 英音女声": "en-GB-SoniaNeural",
    "👨 英音男声": "en-GB-RyanNeural",
}
