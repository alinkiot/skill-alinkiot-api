# uzyiot-api SKILL

有智云智能物联网平台开发者接入 REST API 封装。通过一个纯标准库的 Python CLI（`scripts/uzyiot_api.py`）调用平台的产品查询、设备查询、设备在线状态、实时/历史数据以及设备控制指令下发等接口。

详细的接口说明见 [`SKILL.md`](./SKILL.md)。

---

## 使用说明

### 1. 安装这个 SKILL

```bash
git clone https://github.com/alinkiot/uzyiot-api
cd uzyiot-api
```

运行环境仅需 `python3`（标准库实现，无需 `pip install` 任何依赖）：

```bash
python3 --version   # 确认有 python3 即可
```

### 2. 配置

安装完后，从模板复制一份配置文件并填入自己的凭证（`env.ini` 已被 `.gitignore` 忽略，不会提交）：

```bash
cp env.ini.example env.ini
```

编辑 `env.ini`，配置如下：

```ini
host=http://119.91.212.202
appId=sxxxxx
Secret=xxxx
```

| 配置项 | 说明 |
|--------|------|
| `host` | 平台接入地址，可写完整 URL 或仅域名（自动补 `https://`） |
| `appId` | 应用 AppID |
| `Secret` | 应用 AppSecret |

其中 `appId`、`Secret` 需要在管理后台的 **应用对接** 中创建一个应用后获取。

### 3. 验证

```bash
python3 scripts/uzyiot_api.py login          # 返回 code 200 即配置成功
python3 scripts/uzyiot_api.py product-list   # 查询产品列表
```

> 不想用 `env.ini` 时，也可用 `--token` 或 `--app-id/--app-secret` 直接传参，或设置环境变量 `UZYIOT_TOKEN` / `UZYIOT_APP_ID` + `UZYIOT_APP_SECRET`。详见 [`SKILL.md`](./SKILL.md) 的「凭证获取规则」。
