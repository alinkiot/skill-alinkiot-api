# uzyiot-api SKILL

有智云智能物联网平台开发者接入 REST API 封装。通过一个纯标准库的 Python CLI（`scripts/uzyiot_api.py`）调用平台的产品查询、设备查询、设备在线状态、实时/历史数据以及设备控制指令下发等接口。

详细的接口说明见 [`SKILL.md`](./SKILL.md)。

---

## 使用说明

整个流程——安装、配置、验证、调用——都交给 AI agent 完成，你只需用自然语言把需求交给它。

### 1. 安装这个 SKILL

把下面这句话（带上你的凭证）交给 agent，它会自动从仓库拉取、放到正确的 skill 目录，并用凭证完成配置：

> 帮我安装这个 SKILL：https://github.com/alinkiot/uzyiot-api
> 其中 appId=xxxx，Secret=xxxxx

运行环境仅需 `python3`（标准库实现，无需 `pip install` 任何依赖），agent 会自动确认。

### 2. 配置

安装时若已带上凭证，agent 会自动从模板生成 `env.ini` 并填入（`env.ini` 已被 `.gitignore` 忽略，不会提交）。也可以之后单独补：

> 用这些配置初始化：host=http://119.91.212.202，appId=sxxxxx，Secret=xxxx

| 配置项 | 说明 |
|--------|------|
| `host` | 平台接入地址，可写完整 URL 或仅域名（自动补 `https://`） |
| `appId` | 应用 AppID |
| `Secret` | 应用 AppSecret |

其中 `appId`、`Secret` 需要先在管理后台创建一个「应用对接」后获取，见下节。

### 3. 验证与调用

直接用自然语言让 agent 调用即可，例如：

> 帮我验证下配置通不通，然后把产品列表拉出来

agent 会在后台执行对应命令（如 `login`、`product-list` 等）并返回结果，`code=200` 即表示成功。更多可用接口见 [`SKILL.md`](./SKILL.md)。

---

## 如何在管理后台创建「应用对接」获取 appId / Secret

`appId`、`Secret` 不在本 SKILL 中生成，需要先登录平台管理后台创建一个「应用对接」：

1. 登录有智云平台管理后台。
2. 进入 **项目管理 → 应用对接**。
3. 点击 **新增 / 创建应用**，填写应用名称并选择所属项目，保存。
4. 打开刚创建的应用记录，即可看到并复制 **AppID** 和 **AppSecret**。
5. 把这两个值分别作为 `appId`、`Secret` 交给 agent（见上面第 1 / 2 步）。

> AppSecret 等同于密钥，请妥善保管，不要提交到代码仓库；本 SKILL 已将 `env.ini` 加入 `.gitignore`。
