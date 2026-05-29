# DeepSeek AI 后端

这是一个用于 OCS 脚本的后端服务，接收题目和选项后调用 DeepSeek API 生成答案。

## 目录结构
- `main.py` - Flask 应用入口。
- `.env.example` - 环境变量模板（复制为 `.env` 使用）。
- `docker-compose.example.yml` - Docker Compose 模板（复制为 `docker-compose.yml` 使用）。
- `requirements.txt` - Python 依赖。

## 准备工作
1. 复制环境变量模板：
   ```bash
   copy .env.example .env
   ```
2. 在 `.env` 中设置你的 API Key：
   ```ini
   API_KEY=你的真实Key
   ```
3. （可选）复制 Docker Compose 模板：
   ```bash
   copy docker-compose.example.yml docker-compose.yml
   ```
4. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

> 依赖 `httpx`、`tenacity` 和 `asyncpg`，用于异步调用 AI API、重试逻辑和 PostgreSQL 缓存。

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
- 支持 `model` 字段，可以指定当前服务商下的任何模型名。
- 通过 `API_PROVIDER` 环境变量切换服务商（deepseek / openai / openrouter / siliconflow / custom）。
- 相同题目 + 选项 + 模型会在 PostgreSQL 中缓存，避免重复调用 API。
- 日志写入 `requests.log`，并按大小/天数自动轮转。

## OCS 配置示例
> 注意：服务运行在 HTTP 而非 HTTPS，url 中请使用 `http://`

```json
{
    "name": "AI 答题后端",
    "url": "http://你的公网地址/answer",
    "method": "post",
    "contentType": "json",
    "data": {
        "question": "${title}",
        "options": "${options}"
    },
    "handler": "return (res) => res && res.length > 0 ? [res[0][0], res[0][1]] : undefined"
}
```

> ⚠️ **"题库无法连接" 排查清单**：
> 1. **协议** — 必须用 `http://` 而非 `https://`
> 2. **`@connect` 权限** — 油猴默认拦截未知域名，需要添加 `// @connect 你的服务器IP` 到脚本头部元信息，或在脚本管理器设置中将 `@connect` 模式改为"宽松模式"。
> 3. **端口可达** — 确保 `15000` 端口已映射/开放，防火墙放行。
> 4. **`type`** — 加入 `"type": "GM_xmlhttpRequest"` 以使用油猴跨域请求。

```json
[
    {
        "name": "AI 答题后端",
        "url": "http://你的服务器IP:15000/answer",
        "method": "post",
        "contentType": "json",
        "type": "GM_xmlhttpRequest",
        "data": {
            "question": "${title}",
            "options": "${options}"
        },
        "handler": "return (res) => res && res.length > 0 ? [res[0][0], res[0][1]] : undefined"
    }
]
```

## Docker Compose（需要先复制模板）
```bash
copy docker-compose.example.yml docker-compose.yml
# 然后启动
docker compose up --build
```

默认服务会从 `.env` 读取 `API_KEY` 和 `DATABASE_URL`。

## 注意
- `.env` 和 `docker-compose.yml` 已加入 `.gitignore`，不会提交到版本库。
- 每次拉取代码后，如果模板有更新，需要手动合并到你的本地配置文件。
- 如果运行时无法访问 API，请检查 `API_KEY` 是否正确，并确保服务器能访问外网。
- 如果使用 Docker Compose，确保 `DATABASE_URL` 中的主机名与 `docker-compose.yml` 中的 Postgres 服务名称一致（默认是 `db`）。

