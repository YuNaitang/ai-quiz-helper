# AI Agent Instructions

## Project overview
This repository is a small Flask web service in `main.py` that receives quiz questions and options, forwards them to the DeepSeek chat API, and returns the answer in the strict format expected by the caller.

## What the code does
- `main.py` is the only source file and the application entrypoint.
- It loads `DEEPSEEK_API_KEY` from environment variables via `python-dotenv`.
- It exposes a single POST endpoint at `/answer`.
- Request payload should include `question`; `options` is optional.
- The response must be `[[question, answer]]`.
- CORS is enabled so browser-based clients can call the service.

## Agent guidance
- Focus changes on `main.py` unless adding new project structure or tests.
- Preserve the required output format and strict answer-only behavior.
- Keep prompts and API request structure consistent with the current provider integration.
- Use `flask`, `flask-cors`, `httpx`, `tenacity`, `python-dotenv`, and `asyncpg` as the runtime dependencies.
- The backend supports caching for identical question/option/model combinations.
- Requests may include a `model` field; allowed models depend on the configured `API_PROVIDER`.
- The route uses `httpx` async client with retry/backoff and request pooling for better throughput.

## Configuration
- `API_PROVIDER` — 选择预设服务商（deepseek / openai / openrouter / siliconflow / custom）
- `API_KEY` — 服务商 API 密钥（向后兼容 `DEEPSEEK_API_KEY`）
- `API_BASE_URL` / `API_MODEL` — 可选覆盖项
- `API_AUTH_SCHEME` — 认证头前缀，默认 Bearer
- `API_EXTRA_HEADERS` — 自定义请求头（JSON 格式）
- 请求体中的 `model` 字段可指定服务商下的具体模型名

## Run and debug
- Install dependencies manually or with your preferred Python tooling.
- Set `DEEPSEEK_API_KEY` in a `.env` file or environment before running.
- Start locally with:
  ```bash
  python main.py
  ```

## Notes
- There is a `README.md` describing setup and OCS payload format.
- A `.env.example` file is available to show the expected environment variable layout.
- A `.gitignore` file is added to exclude `.env`, `.venv`, and Python cache files.
- If you add tests or a package manifest, update this file with the new commands.
