import glob
import json
import logging
import os
import re
import time
from logging.handlers import RotatingFileHandler
from threading import Lock
from typing import Optional

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

# 加载 .env 环境变量
load_dotenv()

app = Flask(__name__)
CORS(app)  # 允许跨域，让 OCS 脚本能访问

# DeepSeek 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEFAULT_MODEL = "deepseek-chat"
ALLOWED_MODELS = {"deepseek-chat", "deepseek-reasoner"}

# 本地缓存，避免重复调用同一条题目
CACHE_LOCK = Lock()
answer_cache = {}
CACHE_TTL_SECONDS = 24 * 3600

# 日志配置
LOG_FILE = "requests.log"
MAX_LOG_BYTES = 5 * 1024 * 1024
MAX_LOG_BACKUPS = 30
LOG_RETENTION_DAYS = 30

if not DEEPSEEK_API_KEY:
    raise RuntimeError(
        "DEEPSEEK_API_KEY is not set. Set it in .env or the environment before starting the app."
    )

async_client = httpx.AsyncClient(
    base_url=DEEPSEEK_API_URL,
    headers={
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    },
    timeout=httpx.Timeout(10.0, connect=5.0),
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
)

logger = logging.getLogger("ai_tiku")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_LOG_BYTES,
        backupCount=MAX_LOG_BACKUPS,
        encoding="utf-8",
    )
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def cleanup_old_logs():
    cutoff = time.time() - LOG_RETENTION_DAYS * 86400
    for path in glob.glob(LOG_FILE + "*"):
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            pass


cleanup_old_logs()


SYSTEM_PROMPT = """你是一个答题助手。用户会提供题目和选项，你只需要输出正确答案的内容（不要输出任何额外解释或标点符号）。
如果题目是判断题，请只回答“正确”或“错误”。
如果题目是单选题或多选题，请只输出选项的字母（如 A、AB、ACD），不需要输出选项文本。
如果题目是填空题，直接输出填空内容。
严格遵守以上输出格式。"""


def detect_question_type(question: str, options: str) -> str:
    lower_question = question.lower()
    if any(keyword in lower_question for keyword in ["判断", "是否", "对错", "正确还是错误", "真还是假"]):
        return "judgment"
    if any(marker in question for marker in ["__", "____", "（）", "( )", "填空", "空格"]):
        return "fill_blank"
    if options:
        return "choice"
    return "generic"


def get_system_prompt(question: str, options: str) -> str:
    question_type = detect_question_type(question, options)
    if question_type == "judgment":
        return (
            SYSTEM_PROMPT
            + "\n请直接回答“正确”或“错误”，不要添加任何解释或额外符号。"
        )
    if question_type == "fill_blank":
        return (
            SYSTEM_PROMPT
            + "\n请直接填写空缺内容，不要输出题目、选项或任何解释。"
        )
    if question_type == "choice":
        return (
            SYSTEM_PROMPT
            + "\n如果是单选题，请只输出一个选项字母，如 A。如果是多选题，请只输出多个选项字母，如 AC。不要输出选项文本。"
        )
    return SYSTEM_PROMPT


def is_cache_valid(entry: tuple) -> bool:
    answer, timestamp = entry
    return time.time() - timestamp < CACHE_TTL_SECONDS


def make_cache_key(question: str, options: str, model: str) -> str:
    return json.dumps(
        {"question": question, "options": options, "model": model},
        ensure_ascii=False,
        sort_keys=True,
    )


def should_retry(exception: Exception) -> bool:
    if isinstance(exception, httpx.RequestError):
        return True
    if isinstance(exception, httpx.HTTPStatusError) and exception.response is not None:
        return exception.response.status_code >= 500
    return False


@retry(
    retry=retry_if_exception(should_retry),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
async def fetch_deepseek(question: str, options: str, model: str) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": get_system_prompt(question, options)},
            {"role": "user", "content": f"题目：{question}{'\n选项：' + options if options else ''}"},
        ],
        "temperature": 0.1,
        "max_tokens": 50,
    }
    response = await async_client.post("", json=payload)
    response.raise_for_status()
    return response.json()


def make_cache_key(question: str, options: str, model: str) -> str:
    return json.dumps(
        {"question": question, "options": options, "model": model},
        ensure_ascii=False,
        sort_keys=True,
    )


def normalize_answer(answer_text: str, has_options: bool) -> Optional[str]:
    if not answer_text:
        return None

    text = re.sub(r"[\r\n]+", " ", answer_text).strip()
    text = re.sub(
        r"^(?:答案|Answer|回答|结果|选项|option|result|the answer is|answer is)\s*[:：]?\s*",
        "",
        text,
        flags=re.I,
    ).strip()
    text = text.strip(" \t\n\r\"'。；;：,，、")
    if not text:
        return None

    if has_options:
        match = re.search(r"\b([A-Za-z](?:\s*[A-Za-z]){0,5})\b", text)
        if match:
            letters = re.sub(r"\s+", "", match.group(1)).upper()
            if re.fullmatch(r"[A-Z]{1,6}", letters):
                return letters

    boolean_match = re.fullmatch(r"^(?:正确|错误|true|false|yes|no)$", text, flags=re.I)
    if boolean_match:
        normalized = text.lower()
        if normalized in {"true", "yes"}:
            return "正确"
        if normalized in {"false", "no"}:
            return "错误"
        return text

    if len(text) > 200:
        return None

    return text


@app.route("/answer", methods=["POST"])
async def answer():
    """
    接收 OCS 发来的请求，调用 DeepSeek 获取答案。
    请求体支持字段：question, options, model
    """
    start_time = time.perf_counter()
    cleanup_old_logs()

    try:
        data = request.get_json()
        if not data:
            logger.warning("Missing JSON data")
            return jsonify({"error": "No JSON data"}), 400

        question = str(data.get("question") or "").strip()
        options = str(data.get("options") or "").strip()
        model = str(data.get("model") or DEFAULT_MODEL).strip()

        if not question:
            logger.warning("Missing question field")
            return jsonify({"error": "Missing question"}), 400

        if model not in ALLOWED_MODELS:
            logger.warning(
                "Unsupported model %s, defaulting to %s",
                model,
                DEFAULT_MODEL,
            )
            model = DEFAULT_MODEL

        cache_key = make_cache_key(question, options, model)
        with CACHE_LOCK:
            entry = answer_cache.get(cache_key)
            cached_answer = entry[0] if entry and is_cache_valid(entry) else None

        if cached_answer:
            elapsed = time.perf_counter() - start_time
            logger.info(
                "cache_hit model=%s question=%r options=%r answer=%r elapsed=%.3fs",
                model,
                question,
                options,
                cached_answer,
                elapsed,
            )
            return jsonify([[question, cached_answer]])

        try:
            result = await fetch_deepseek(question, options, model)
        except httpx.HTTPStatusError as e:
            elapsed = time.perf_counter() - start_time
            logger.error(
                "api_status_error model=%s question=%r options=%r status=%s elapsed=%.3fs",
                model,
                question,
                options,
                e.response.status_code,
                elapsed,
            )
            return jsonify({"error": f"DeepSeek API status error: {e.response.status_code}"}), 502
        except httpx.RequestError as e:
            elapsed = time.perf_counter() - start_time
            logger.error(
                "api_request_error model=%s question=%r options=%r error=%s elapsed=%.3fs",
                model,
                question,
                options,
                str(e),
                elapsed,
            )
            return jsonify({"error": f"DeepSeek API request error: {str(e)}"}), 502
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            logger.exception(
                "api_unexpected_error model=%s question=%r options=%r error=%s elapsed=%.3fs",
                model,
                question,
                options,
                str(e),
                elapsed,
            )
            return jsonify({"error": str(e)}), 500

        choices = result.get("choices")
        if not isinstance(choices, list) or not choices:
            logger.warning(
                "empty_choices model=%s question=%r options=%r result=%r elapsed=%.3fs",
                model,
                question,
                options,
                result,
                time.perf_counter() - start_time,
            )
            return jsonify([]), 200

        raw_answer = str(choices[0].get("message", {}).get("content", "")).strip()
        answer_text = normalize_answer(raw_answer, bool(options))
        elapsed = time.perf_counter() - start_time

        if not answer_text:
            logger.warning(
                "invalid_ai_answer model=%s question=%r options=%r raw=%r elapsed=%.3fs",
                model,
                question,
                options,
                raw_answer,
                elapsed,
            )
            return jsonify([]), 200

        with CACHE_LOCK:
            answer_cache[cache_key] = (answer_text, time.time())

        logger.info(
            "answered model=%s question=%r options=%r answer=%r elapsed=%.3fs",
            model,
            question,
            options,
            answer_text,
            elapsed,
        )
        return jsonify([[question, answer_text]])

    except Exception as e:
        elapsed = time.perf_counter() - start_time
        logger.exception(
            "unexpected_error model=%s question=%r options=%r elapsed=%.3fs",
            model,
            question,
            options,
            elapsed,
        )
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
