# 项目配置说明

## 快速开始

本项目需要配置一些敏感信息才能正常运行。请按照以下步骤进行配置：

## 1. 环境变量配置

复制示例文件并填入你的配置：

```bash
cp .env.example .env
```

然后编辑 `.env` 文件，填入以下信息：

### 必需配置项

- **LLM API Keys**: 配置你的大模型 API 密钥
  - `LLM_ZHIPU_API_KEY`: 智谱 AI API Key
  - `LLM_DEEPSEEK_API_KEY`: DeepSeek API Key
  - `LLM_PRODUCT_API_KEY`: 其他模型 API Key
  - `LLM_QUANT_API_KEY`: 量化专员 API Key
  - `LLM_VIZ_API_KEY`: 可视化助手 API Key

- **邮件配置** (如果需要邮件功能):
  - `SMTP_HOST`: SMTP 服务器地址
  - `SMTP_PORT`: SMTP 端口
  - `SMTP_USER`: 邮箱账号
  - `SMTP_PASS`: 邮箱密码/授权码

## 2. 前端配置

复制示例文件：

```bash
cp frontend/config.json.example frontend/config.json
```

编辑 `frontend/config.json`，修改以下字段：
- `backend.host`: 你的后端服务器域名或 IP
- `api.baseUrl`: 完整的 API 地址
- `api.wsUrl`: WebSocket 地址

## 3. MCP 配置

复制示例文件：

```bash
cp backend/mcp.json.example backend/mcp.json
```

编辑 `backend/mcp.json`，填入：
- `X-Tushare-Token`: 你的 Tushare API Token（用于金融数据）

获取 Tushare Token: https://tushare.pro/

## 4. PM2 配置（可选）

如果使用 PM2 部署：

```bash
cp ecosystem.config.js.example ecosystem.config.js
```

根据你的实际路径修改配置文件中的路径。

## 安装依赖

### 后端

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 前端

```bash
npm install -g http-server
```

## 运行项目

### 开发模式

**后端**:
```bash
cd backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 5232 --reload
```

**前端**:
```bash
http-server frontend -p 5231 -c-1 --cors
```

### 生产模式（PM2）

```bash
pm2 start ecosystem.config.js
pm2 save
pm2 startup
```

## 注意事项

⚠️ **重要**: 
- 请勿将包含真实密钥的配置文件提交到 Git
- 所有 `.example` 文件可以安全提交
- `.gitignore` 已配置忽略敏感文件

## 常见问题

### Q: 如何获取各个平台的 API Key？

- **智谱 AI**: https://open.bigmodel.cn/
- **DeepSeek**: https://platform.deepseek.com/
- **Tushare**: https://tushare.pro/

### Q: 如何配置 SMTP 邮件服务？

以 QQ 邮箱为例：
1. 登录 QQ 邮箱
2. 设置 -> 账户
3. 开启 SMTP 服务
4. 获取授权码
5. 填入 `.env` 文件

## 技术支持

如有问题，请提交 Issue。

