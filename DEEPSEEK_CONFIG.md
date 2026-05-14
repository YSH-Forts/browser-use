# DeepSeek API 配置指南

## 已创建的文件

- `.env` - API Key 配置
- `run_deepseek.py` - 启动脚本（已通过 CapitalIQ 登录测试）
- `DEEPSEEK_CONFIG.md` - 本文档

## 快速启动

```bash
# 1. 激活虚拟环境
.venv\Scripts\activate

# 2. 运行
python run_deepseek.py
```

## 重要说明

**`deepseek-v4-flash` 不支持 function calling**，会报错。请使用 `deepseek-chat` 模型。

## 登录 CapitalIQ 测试结果

已通过测试，成功登录。登录流程：
1. 访问 https://www.capitaliq.com/CIQDotNet/my/dashboard.aspx
2. 填写用户名密码（Okta SSO）
3. 登录成功，跳转到 My Settings 页面

## 启动脚本说明

`run_deepseek.py` 支持：
- 自定义 LLM 模型和 API 地址
- 无头/有头模式（`headless=False` 打开可视化浏览器）
- 自定义任务描述
- Step timeout 控制

## API 配置参数

```python
from browser_use.llm.deepseek.chat import ChatDeepSeek

llm = ChatDeepSeek(
    model='deepseek-chat',           # 模型名称
    api_key='your-api-key',          # API Key
    base_url='https://api.deepseek.com',  # API 地址
    temperature=0.0,                # 可选：温度参数
    max_tokens=4096,                # 可选：最大 token 数
)
```

## 修改任务

编辑 `run_deepseek.py` 中的 `task` 字段即可。
