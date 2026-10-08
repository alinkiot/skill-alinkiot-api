# uzyiot-api SKILL

有智云智能物联网平台开发者接入 REST API 封装。通过一个纯标准库的 Python CLI（`scripts/uzyiot_api.py`）调用平台的产品查询、设备查询、设备在线状态、实时/历史数据以及设备控制指令下发等接口。

详细的接口说明见 [`SKILL.md`](./SKILL.md)。

---

## 使用说明

整个流程——安装、配置、验证、调用——都交给 AI agent 完成，你只需用自然语言把需求交给它。

### 1. 安装这个 SKILL

把下面这句话交给 agent，由它自动从仓库拉取并放到正确的 skill 目录：

> 帮我安装这个 SKILL：https://github.com/alinkiot/uzyiot-api

运行环境仅需 `python3`（标准库实现，无需 `pip install` 任何依赖），agent 会自动确认。

### 2. 配置

把你的凭证交给 agent，由它从模板生成 `env.ini` 并填入（`env.ini` 已被 `.gitignore` 忽略，不会提交）：

> 用这些配置初始化：host=http://119.91.212.202，appId=sxxxxx，Secret=xxxx

| 配置项 | 说明 |
|--------|------|
| `host` | 平台接入地址，可写完整 URL 或仅域名（自动补 `https://`） |
| `appId` | 应用 AppID |
| `Secret` | 应用 AppSecret |

其中 `appId`、`Secret` 需要先在管理后台的 **应用对接** 中创建一个应用后获取，再把值交给 agent。

### 3. 验证与调用

直接用自然语言让 agent 调用即可，例如：

> 帮我验证下配置通不通，然后把产品列表拉出来

agent 会在后台执行对应命令（如 `login`、`product-list` 等）并返回结果，`code=200` 即表示成功。更多可用接口见 [`SKILL.md`](./SKILL.md)。
