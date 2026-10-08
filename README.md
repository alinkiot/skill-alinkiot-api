# uzyiot-api SKILL

有智云智能物联网平台开发者接入 REST API 封装。通过一个纯标准库的 Python CLI（`scripts/uzyiot_api.py`）调用平台的产品查询、设备查询、设备在线状态、实时/历史数据以及设备控制指令下发等接口。

详细的接口说明见 [`SKILL.md`](./SKILL.md)。

---

## 使用说明

整个流程——安装、配置、验证、调用——都交给 AI agent 完成，你只需用自然语言把需求交给它。

### 1. 安装这个 SKILL

把下面这句话（带上你的凭证）交给 agent，它会自动从仓库拉取、放到正确的 skill 目录，并用凭证完成配置：

> 帮我安装这个 SKILL：https://github.com/alinkiot/uzyiot-api
> 其中 host=http://x.x.x.x, appId=xxxx，Secret=xxxxx

`appId`、`Secret` 获取需要先登录平台管理后台创建一个「应用对接」：

1. 登录有智云平台管理后台。
2. 进入 **项目管理 → 应用对接**。
3. 点击 **新增 / 创建应用**，填写应用名称并选择所属项目，保存。
4. 打开刚创建的应用记录，即可看到并复制 **AppID** 和 **AppSecret**。

### 2. 验证与调用

直接用自然语言让 agent 调用即可，例如：

> 帮我查下产品有哪些

agent 会在后台执行对应命令（如 `login`、`product-list` 等）并返回结果，`code=200` 即表示成功。更多可用接口见 [`SKILL.md`](./SKILL.md)。

---
