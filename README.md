# DeepSeek AI 后端

这是一个用于 OCS 脚本的后端服务，接收题目和选项后调用 DeepSeek API 生成答案。

## 目录结构
- `main.py` - Flask 应用入口。
- `.env` - 运行时环境变量（不应提交到版本库）。
- `.env.example` - 环境变量模板。
- `requirements.txt` - Python 依赖。

## 准备工作
1. 复制 `.env.example` 为 `.env`：
   ```bash
   copy .env.example .env
   ```
2. 在 `.env` 中设置你的 DeepSeek API Key：
   ```ini
   DEEPSEEK_API_KEY=你的真实Key
   ```
3. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

> 新增依赖 `httpx`、`tenacity` 和 `asyncpg`，用于异步调用 DeepSeek API、重试逻辑和 PostgreSQL 缓存。

## 运行服务
```bash
python main.py
```

服务默认监听 `0.0.0.0:5000`，主要接口：

- `POST /answer`
- 请求 JSON 格式：
  ```json
  {
    "question": "题目内容",
    "options": "A. 选项一\nB. 选项二",
    "model": "deepseek-chat"
  }
  ```
- 返回格式（OCS 要求）：
  ```json
  [["题目内容", "答案"]]
  ```

## 说明
- 支持 `model` 字段，可选 `deepseek-chat` 或 `deepseek-reasoner`。
- 相同题目 + 选项 + 模型会在 PostgreSQL 中缓存，避免重复调用 DeepSeek API。
- 日志写入 `requests.log`，并按大小/天数自动轮转。

## OCS 配置示例
```json
{
    "name": "DeepSeek AI 后端",
    "url": "https://你的公网地址/answer",
    "method": "post",
    "contentType": "json",
    "data": {
        "question": "${title}",
        "options": "${options}"
    },
    "handler": "return (res) => { if (res && res.length > 0) { return [[res[0][0], res[0][1]]]; } return undefined; }"
}
```

## Docker Compose
```bash
docker compose up --build
```

默认服务会从 `.env` 读取 `DEEPSEEK_API_KEY` 和 `DATABASE_URL`。

## 注意
- `.env` 中不要提交真实 API Key。
- 如果运行时无法访问 DeepSeek API，请检查 `DEEPSEEK_API_KEY` 是否正确，并确保服务器能访问外网。
- 如果使用 Docker Compose，确保 `DATABASE_URL` 中的主机名与 `docker-compose.yml` 中的 Postgres 服务名称一致（默认是 `db`）。

