---
name: uzyiot-api
description: 有智云智能物联网平台（https://prod.uzyiot.com）开发者接入 REST API 封装。基于《有智云物联网平台操作手册》第十章「开发者接入指南」，提供应用侧凭证（AppID/AppSecret）换取 Token，以及产品查询、设备查询、设备在线状态、设备实时数据、设备历史数据等全部 REST 接口，并额外提供设备控制指令下发（平台扩展接口）的 Python CLI 调用能力。适用于第三方系统/AI 应用通过 HTTP 对接有智云平台做数据同步、设备查询与设备控制。
---

# 有智云物联网平台 开发者接入 API

通过一个 Python CLI 脚本（仅依赖标准库）调用有智云平台第十章「开发者接入指南」中的全部 REST API。

**接入地址：** `https://prod.uzyiot.com`
**脚本路径：** `scripts/uzyiot_api.py`

---

## 调用前必读：凭证获取规则

所有 API 调用都需要鉴权。凭证来自平台的 **应用接入（AppID/AppSecret）**：

1. 登录平台 → **项目管理 → 应用接入 → 新增**，填写应用名称、选择项目
2. 保存后点击应用记录，获取 `appId` 和 `appSecret`

脚本按以下优先级解析鉴权（任选一种）：

| 优先级 | 方式 | 说明 |
|--------|------|------|
| 1 | `--token <token>` | 直接传入已获取的 token |
| 2 | `--app-id <id> --app-secret <secret>` | 脚本内部自动登录换 token |
| 3 | 环境变量 `UZYIOT_TOKEN` | 等价于方式 1 |
| 4 | 环境变量 `UZYIOT_APP_ID` + `UZYIOT_APP_SECRET` | 等价于方式 2 |
| 5 | skill 根目录 `env.ini` | 配置 `appId` / `Secret`，脚本自动读取并登录 |

**`env.ini` 格式**（放在 skill 根目录 `uzyiot-api/env.ini`）：

```ini
# 平台接入地址（切换不同平台时改这里）；可写完整 URL 或仅域名（自动补 https://）
host=https://prod.uzyiot.com
appId=********
Secret=****************
```

配置后无需再传任何凭证参数，直接调用即可：

```bash
python3 scripts/uzyiot_api.py product-list
```

> ⚠️ `env.ini` 含密钥，请勿提交到 Git（建议在 `.gitignore` 中加入 `env.ini`）。

> 若用户未提供 `appId`/`appSecret` 或 `token`，且 `env.ini` 也未配置，**必须主动向用户询问**，不要用占位符执行。

**平台地址（Base URL）**支持切换不同平台，解析优先级：
`--base-url` 参数 > 环境变量 `UZYIOT_BASE_URL` > `env.ini` 的 `host` > 默认 `https://prod.uzyiot.com`。

- `env.ini` 的 `host` 可写完整 URL（`https://xxx.com`）或仅域名（`xxx.com`，自动补 `https://`）
- `--base-url` 是全局参数，需放在子命令**之前**，如 `python3 scripts/uzyiot_api.py --base-url https://other.com login`

**退出码：** `0`=成功，`1`=调用失败，`2`=token 过期/鉴权失败（HTTP 401/403，需重新登录）。

---

## 鉴权 API

### 获取 Token

**必须向用户询问的参数：** `appId`、`appSecret`（若未提供）

对应接口：`POST /iotapi/system/user/app/login`

```bash
python3 scripts/uzyiot_api.py login --app-id <appId> --app-secret <appSecret>
```

成功响应包含 `token`、`projectId`（查询设备列表时用）、`expire`（有效期秒数）。
Token 到期需重新获取；收到退出码 `2` 即表示过期。

---

## 产品 API

### 查询产品列表

对应接口：`GET /iotapi/system/product/list`

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `--page-num` | 可选 | 1 | 页码 |
| `--page-size` | 可选 | 20 | 每页数量 |

```bash
python3 scripts/uzyiot_api.py product-list \
  --app-id <appId> --app-secret <appSecret> \
  --page-num 1 --page-size 20
```

返回每条含产品 ID、名称、ProductKey（`pk`）、物模型定义（`thing`）、协议类型。

### 查询产品详情

对应接口：`GET /iotapi/system/product/:ID`

| 参数 | 必填 | 说明 |
|------|------|------|
| `--id` | ✅ | 产品 ID（可先调用 product-list 获取） |

```bash
python3 scripts/uzyiot_api.py product-detail --token <token> --id <productId>
```

---

## 设备 API

### 查询设备列表

对应接口：`GET /iotapi/system/device/list`

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `--project` | 可选 | — | 项目 ID（登录响应里的 `projectId`） |
| `--page-num` | 可选 | 1 | 页码 |
| `--page-size` | 可选 | 20 | 每页数量 |

```bash
python3 scripts/uzyiot_api.py device-list --token <token> --project 16
```

返回每条含设备 ID、唯一编号（`addr`）、设备名称、设备 Key（`dk`）、经纬度。

### 查询设备详情

对应接口：`GET /iotapi/system/device/:ID`

| 参数 | 必填 | 说明 |
|------|------|------|
| `--id` | ✅ | 设备 ID（可先调用 device-list 获取） |

```bash
python3 scripts/uzyiot_api.py device-detail --token <token> --id <deviceId>
```

### 查询设备在线状态

对应接口：`GET /iotapi/system/device/online`

| 参数 | 必填 | 说明 |
|------|------|------|
| `--addr` | ✅ | 设备地址，多个用逗号分隔，如 `addr1,addr2,addr3` |

```bash
python3 scripts/uzyiot_api.py device-online --token <token> --addr addr1,addr2
```

返回 `online: 1` 在线，`0` 离线。

---

## 数据 API

### 查询设备实时数据

对应接口：`GET /iotapi/system/device/history/last`

| 参数 | 必填 | 说明 |
|------|------|------|
| `--addr` | ✅ | 设备地址，多个用逗号分隔 |

```bash
python3 scripts/uzyiot_api.py device-last --token <token> --addr <addr>
```

返回设备最新一条上报记录，含采集时间（`createtime`，Unix 秒）和各物模型属性键值对。

**把属性翻译成中文（物模型对照）**

实时数据里的属性名是物模型的原始键（如 `h1001`、`temp`），并非中文。要显示成中文名，按以下步骤对照该设备所属产品的物模型即可，**无需改脚本**：

1. 用 `device-list` 查到该设备的 `product`（产品 ID）与 `addr`
2. 用 `product-detail --id <product>` 取产品详情，其 `thing` 字段是一段 JSON 字符串，解析后是属性数组，每项含 `name`（原始键）、`title`（中文名）、`unit`（单位）、`access`（读写权限）
3. 用 `name` 把实时数据的键映射到 `title`，并补上 `unit`

例：产品物模型中 `{"name":"h1001","title":"运行频率","unit":"Hz"}`，则实时数据里的 `"h1001": 50` 读作 **运行频率 = 50 Hz**。

> 物模型里没有定义的键（设备只上报了心跳/状态时常见）保持原样显示即可；`createtime` 为采集时间戳，`alarmrule` 为空表示无触发中的告警。

### 查询设备历史数据

对应接口：`GET /iotapi/system/history/list`

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `--addr` | ✅ | — | 设备地址 |
| `--begin` | 可选 | — | 起始时间 `YYYY-MM-DD HH:mm:ss` |
| `--end` | 可选 | — | 结束时间 `YYYY-MM-DD HH:mm:ss` |
| `--page-num` | 可选 | 1 | 页码（单页模式） |
| `--page-size` | 可选 | 10 | 每页数量；`--all` 模式下作为每页抓取大小（建议 100~200） |
| `--all` | 可选 | 关 | 自动翻页拉取全部记录，忽略 `--page-num`，带上限保护 |
| `--max-records` | 可选 | 10000 | `--all` 模式最大条数上限，超过则截断并标记 `truncated` |
| `--step` | 可选 | 0 | 聚合粒度（秒）：0=不聚合返回原始数据，30=按30秒聚合，依此类推 |
| `--readable` | 可选 | 关 | 关联产品物模型，把每条记录属性映射为「别名(title)+属性名(name)+单位」 |
| `--type` | 可选 | table | `table` 表格格式 / `chart` 图表格式 |
| `--order-by-desc` | 可选 | createTime | 降序排序字段 |

```bash
# 单页（默认，手动分页）
python3 scripts/uzyiot_api.py history-list --addr <addr> \
  --begin "2024-12-02 00:00:00" --end "2024-12-02 23:59:59" \
  --page-num 1 --page-size 10

# 全量拉取（自动翻页，返回 total/fetched，超上限时 truncated=true）
python3 scripts/uzyiot_api.py history-list --addr <addr> \
  --begin "2024-12-02 00:00:00" --end "2024-12-02 23:59:59" \
  --all --page-size 200 --max-records 5000

# 全量 + 中文物模型映射
python3 scripts/uzyiot_api.py history-list --addr <addr> \
  --begin "..." --end "..." --all --readable
```

**分页注意事项：** 历史记录常有数百到数千条，默认单页只返回 `--page-size` 条。要完整分析趋势必须考虑分页——用 `--all` 自动翻页取全量（结果含 `total` 总数与 `fetched` 实取条数），或手动递增 `--page-num` 逐页取。`--all` 受 `--max-records` 保护，达到上限会截断并在输出里标记 `truncated: true`，避免原始数据量过大时拉爆。

> `--step 0`（不聚合）在本平台服务端有 bug 会报 500，CLI 已自动改为「省略 step」处理，结果等价于原始数据，无需担心。
> 历史数据查询为空时，确认设备在该时间段内有上报，且时间格式为 `YYYY-MM-DD HH:mm:ss`。

---

## 控制 API

### 下发设备控制指令

对应接口：`POST /iotapi/system/control/device`

> 说明：本接口为平台扩展接口（非操作手册第十章范围）。后端收到后会组装物模型「写」消息并通过内部 MQTT（`p/in/<addr>`）下发给设备；设备在线才会真正到达，离线时接口仍返回成功但不下发。

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `--addr` | ✅ | — | 设备地址 |
| `--name` | ✅ | — | 物模型变量名（可从 `product-detail` 的 `thing` 里查到，取 `access` 为 `rw`/`write` 的项） |
| `--value` | ✅ | — | 下发值，配合 `--hex` / `--type` 决定解析方式 |
| `--hex` | 可选 | 关 | 将 `--value` 按 16 进制整数解析（如 `FF00` → `65280`，`0000` → `0`）；复刻前端「命令下发」弹窗勾选 Hex 的行为 |
| `--type` | 可选 | string | `--value` 的类型：`string` / `int` / `float`；指定 `--hex` 时忽略本项 |

```bash
# 继电器开（hex FF00，等价前端 parseInt("FF00",16)=65280）
python3 scripts/uzyiot_api.py device-control --addr WIND01 --name status --value FF00 --hex

# 继电器关（hex 0000 = 0）
python3 scripts/uzyiot_api.py device-control --addr WIND01 --name status --value 0000 --hex

# 下发十进制整数
python3 scripts/uzyiot_api.py device-control --addr WIND01 --name status --value 1 --type int

# 下发字符串（默认）
python3 scripts/uzyiot_api.py device-control --addr <addr> --name <var> --value "open"
```

请求体等价于：`{"msgType":"control_device","name":"<name>","value":<value>}`，`addr` 作为 query 参数。
成功返回 `{"msg":"操作成功","code":200}`。

> 下发的 `name` 必须是该设备产品物模型里真实存在、且可写的变量；拿不准时先用 `product-detail` 查 `thing`。

---

## API 速查表

| 子命令 | 方法 | 路径 | 必填参数 |
|--------|------|------|---------|
| `login` | POST | `/iotapi/system/user/app/login` | appId, appSecret |
| `product-list` | GET | `/iotapi/system/product/list` | — |
| `product-detail` | GET | `/iotapi/system/product/:ID` | id |
| `device-list` | GET | `/iotapi/system/device/list` | — |
| `device-detail` | GET | `/iotapi/system/device/:ID` | id |
| `device-online` | GET | `/iotapi/system/device/online` | addr |
| `device-last` | GET | `/iotapi/system/device/history/last` | addr |
| `history-list` | GET | `/iotapi/system/history/list` | addr |
| `device-control` | POST | `/iotapi/system/control/device` | addr, name, value |

---

## 错误处理

| 现象 | 原因 / 处理 |
|------|-------------|
| 退出码 2 / HTTP 401 | Token 已过期，重新执行 `login` 获取新 token |
| 登录失败 | 核对 appId / appSecret 是否正确、应用是否被禁用 |
| 历史数据为空 | 确认时间范围内有上报数据，时间格式 `YYYY-MM-DD HH:mm:ss` |
| 网络错误 | 检查到 `prod.uzyiot.com` 的网络连通性 |

---

## 备注

- 脚本仅使用 Python 标准库（`urllib`），无需安装第三方依赖，`python3` 即可运行。
- 本 skill 覆盖操作手册第十章的 **REST API**，外加平台扩展的 **设备控制接口**（`device-control`，非手册第十章）；设备侧 MQTT/TCP 接入与应用侧 MQTT 实时订阅（10.5/10.9/10.10/10.11）属于长连接协议，不在本 CLI 范围内，如需请参考操作手册对应章节。
- 查看所有子命令：`python3 scripts/uzyiot_api.py -h`；查看单个子命令参数：`python3 scripts/uzyiot_api.py <command> -h`。
