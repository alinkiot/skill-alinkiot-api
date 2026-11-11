---
name: uzyiot-api
description: 有智云智能物联网平台（https://prod.uzyiot.com）开发者接入 REST API 封装。提供应用侧凭证（AppID/AppSecret）换取 Token，以及产品/设备/场景/字典查询、设备在线状态、设备实时与历史数据等 REST 接口；文档并说明设备 MQTT/TCP 接入、应用侧 MQTT 通讯与应用数据同步机制，并额外提供设备控制指令下发（平台扩展接口）的 Python CLI 调用能力。适用于第三方系统/AI 应用通过 HTTP 对接有智云平台做数据同步、设备查询与设备控制。
---

# 有智云物联网平台 开发者接入 API

通过一个 Python CLI 脚本（仅依赖标准库）调用有智云物联网平台开发者接入的全部 REST API。

**接入地址：** `https://prod.uzyiot.com`
**脚本路径：** `scripts/uzyiot_api.py`

---

## 平台概念与对象关系

```
项目（project）── 一个工程 / 一个业务，如「智慧工地」
 ├── 应用（app）      对接用的 AppID / AppSecret，归属于项目
 ├── 场景（scene）    项目下的分组，如「A 工地」「B 工地」
 │    ├── 绑定设备（scene_device）  每个场景绑定不同的设备
 │    └── 视图（scene_view）        每个场景可有多个视图，如「正面视图」「侧面视图」
 └── 设备（device）   每台设备属于一个产品（product）

产品（product）── 系统级，可复用，是「一类设备」的抽象
 ├── 协议（protocol）  设备用什么协议接入
 ├── 物模型（thing）   有哪些数据字段（上行）
 ├── 控制指令（control）有哪些可下发的控制（下行）
 └── 面板（category）  这类设备的状态怎么展示
```

| 概念 | 说明 | 对应接口 |
|------|------|----------|
| 项目 | 一个工程或业务。项目下有场景、设备、应用。登录响应里的 `projectId` 即当前应用所属项目 | `login`（返回 `projectId`） |
| 应用 | 第三方系统对接平台的身份（AppID/AppSecret），归属某个项目，用它换 token | `login` |
| 场景 | 项目内的分组，常对应一个物理位置或业务单元（如智慧工地的 A 工地、B 工地）。一个项目有多个场景，每个场景绑定不同设备 | `scene-list`、`scene-detail` |
| 场景绑定设备 | 场景与设备的关联；只记录设备 ID | `scene-device` |
| 视图 | 场景下组织设备展示的方式，一个场景可建多个（如正面视图、侧面视图）；每个视图可以用一个 HTML 模板把设备展示出来。场景 `viewType` 列出该场景有哪些视图类型 | `scene-view` |
| 设备 | 具体的一台设备，有唯一地址 `addr`，属于一个产品 | `device-list`、`device-detail`、`device-batch`、`device-online` |
| 产品 | 系统级、可复用，是一类设备的抽象（如某品牌的变频器）。产品决定这类设备的**协议、物模型、控制指令、面板**；不同产品（即使同类设备、不同品牌）这些都不同 | `product-list`、`product-detail`、`product-batch` |
| 物模型（`thing`） | 产品定义的数据字段：属性名、别名、类型、单位、读写权限、倍率等。设备上报的数据按它解释 | `product-detail` 的 `thing` |
| 控制指令（`control`） | 产品定义的可下发控制：控制哪个变量、控件类型、可选值、值格式 | `product-detail` 的 `control` |
| 面板 | 产品中定义「如何显示这个设备的状态」：如摄像头的面板是视频直播，温度计的面板是温度数据显示。由产品的 `category` 字段指定：`default` 为通用面板，否则为独立的 HTML 面板，见下节「面板与 HTML 页面」 | `product-detail` 的 `category` |

**由此得到的几条原则：**

1. **设备的一切差异来自产品。** 要知道一台设备有哪些数据、能做哪些控制、用什么协议、用什么面板展示，都先找到它的产品（设备详情的 `product` 字段），再读产品详情。不要假设两台设备字段一致，即使它们同属一类（如不同品牌的变频器）。
2. **产品是系统级的，设备按产品复用。** 多台设备共用一个产品，所以读取物模型时应按产品 ID **去重**后再查（`product-batch`），不要对每台设备重复查。
3. **按「项目 → 场景 → 设备」定位数据。** 应用通常从某个项目的场景出发，取场景绑定的设备，再取设备详情和产品物模型，最后查数据或下发控制。
4. **场景决定视图，视图决定展示。** 需要做场景级的页面时，用场景的 `viewType` 找到视图，视图的配置在 `scene-view` 的 `data` 里；视图里的设备标注通过 `devId` / `addr` 关联到具体设备。

---

### 面板与 HTML 页面

**产品面板**（产品详情的 `category` 字段）决定设备状态页怎么展示：

| `category` | 面板 | 展示方式 |
|------------|------|----------|
| `default` | 通用面板 | 卡片显示：**每个物模型字段一张卡片**（别名、值、单位、更新时间），按 `thing` 渲染，所有产品通用；若有 `control` 指令则同时显示控制按钮 |
| 其他值（HTML 文件路径，如 `/upload/20261023141055.html`） | HTML 面板 | 这类设备有自己专属的展示页（如摄像头是视频直播，温度计是温度数据显示），是**一个独立的 HTML 文件**，应用自己加载并组织显示：取设备数据后填充到页面中 |

可用的面板在字典 `iot_product_mgr` 中维护（`dict-data --dict-type iot_product_mgr`）：字典项的 `dictValue` 就是面板标识（即产品 `category` 的取值），HTML 面板的 `dictValue` 为 HTML 文件路径，`listClass` 为 `file`。

**场景视图**（`scene-view`）同样可以使用 HTML 页面：视图的 `data` 里保存 HTML 页面路径等信息，应用自行加载并组织设备展示。

**HTML 页面在平台 Dashboard 中的运行方式**（自行实现应用时可参照）：
- 页面放在沙箱 `iframe` 中运行，页面通过 `postMessage` 与宿主通讯
- 页面里需手动引入 `<script src="/scene-sdk.js"></script>`（若与 Dashboard 不同域，写 Dashboard 完整地址），之后可使用 `window.SceneSDK`，各方法返回 Promise：
  - `getDevices()`、`getDeviceStatus(deviceId)`、`getDeviceProduct(deviceId)`
  - `getDeviceLatestRecord(deviceId)`、`getDeviceHistory(deviceId, options)`
  - `subscribeDeviceStatus(deviceId, callback)`（实时订阅，返回取消订阅函数）
  - 设备 ID 必须属于当前场景
- 这些方法在宿主里最终就是调用本文档的 REST API 与应用侧 MQTT；自行实现应用时，用同样的接口即可提供等价能力

---

## 快速开始（安装）

1. **获取代码**：`git clone <本仓库地址>`，进入 skill 目录（`uzyiot-api/`）。

2. **运行环境**：仅需 `python3`（标准库实现，无需 `pip install` 任何依赖）。
   ```bash
   python3 --version   # 确认有 python3 即可
   ```

3. **配置凭证**：仓库不含 `env.ini`（已被 `.gitignore` 忽略），需从模板复制并填入自己的配置：
   ```bash
   cp env.ini.example env.ini
   # 编辑 env.ini，填入 host / appId / Secret
   ```
   `appId` / `Secret` 在平台「项目管理 → 应用接入」创建应用后获取；`host` 按目标平台填写。

4. **验证**：
   ```bash
   python3 scripts/uzyiot_api.py login          # 返回 code 200 即配置成功
   python3 scripts/uzyiot_api.py product-list   # 查询产品列表
   ```

> 不想用 `env.ini` 时，也可用 `--token` 或 `--app-id/--app-secret` 直接传参，或设置环境变量（见下节「凭证获取规则」）。

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

## 通用约定

**请求头：** 除 `login` 外，所有请求都要在 Header 里带 `token: <token>`（不是 `Authorization`）。`login` 请求体为 JSON：`{"appId":"...","appSecret":"..."}`。

**成功判定：** HTTP 200 且响应体 `code == 200`。

**响应结构有两种：**

| 接口类型 | 结构 |
|----------|------|
| 分页列表（产品、设备、场景、场景设备等 `list`） | `{"msg","code","total","rows":[...]}` |
| 详情 / 批量 / 查询（`:ID`、`:ID1,:ID2`、在线状态、实时数据、字典、场景视图） | `{"msg","code","data": 对象或数组}`（单个详情是对象，批量和查询多为数组；实时数据 `data` 是属性键值对象） |

**错误处理：** HTTP 401 / 403 表示 token 无效或过期，应重新 `login` 后重试；业务失败时 `code` 不为 200，`msg` 为失败原因。

**字段约定：**
- 以 JSON **字符串**形式返回、需再 `json.loads` 的字段：产品的 `thing`、`control`、`config`；场景的 `viewType`；场景视图的 `data`；设备的 `config`
- 状态字段 `status` 为 `"0"` 表示正常
- 请求中的时间格式为 `YYYY-MM-DD HH:mm:ss`；响应里的 `createTime` 形如 `2024-9-29 18:56:25`（月日时分秒不补零）
- 设备在数据类接口（在线状态、实时、历史、控制）里用的是**设备地址 `addr`**，而场景绑定、详情接口用的是**设备 ID `id`**，两者不要混用

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

响应结构为 `{"msg","code","data":{...}}`，`data` 中的关键字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` / `name` / `pk` / `ps` | — | 产品 ID / 名称 / ProductKey / ProductSecret |
| `protocol` | string | 协议类型，如 `Modbus-RTU` |
| `nodeType` / `netType` / `category` | string | 节点类型 / 网络类型 / 产品分类 |
| `thing` | JSON 字符串 | **物模型**（上行数据点定义），需 `json.loads` 解析，见下 |
| `control` | JSON 字符串 | **下行控制指令定义**（可下发哪些控制、界面如何展示、可选值），需 `json.loads` 解析，见下 |
| `config` | JSON 字符串 | 产品自定义配置项（`title`/`name`/`type`/`value`，可含 `options`） |

**`thing`（物模型）** 每项：`name`（属性名）、`title`（别名）、`type`、`access`（`rw` 可读写 / `r` 只读）、`unit`、`min`/`max`/`rate`，Modbus 产品另含 `modbus`（功能码、起始地址等）。

**`control`（下行控制指令）** 是 JSON 数组，每项描述一条可向设备下发的控制指令：

| 字段 | 说明 |
|------|------|
| `name` | 要控制的物模型变量名，对应 `thing` 里的 `name`，也就是 `device-control --name` 的值 |
| `title` | 控制项显示名（如「按钮」） |
| `ctrlType` | 控件类型：`enum` 枚举型（从 `options` 选值）/ `btn` 按钮型（固定 `value`，`desc` 为说明）/ `input` 输入型（用户自由输入） |
| `format` | 下发值的数据类型，取值来自字典 `iot_data_type`（`integer` 整形 / `float` 浮点 / `string` 字符串 / `array` 数组，可用 `dict-data --dict-type iot_data_type` 查询），外加 `hex`（16 进制字符串） |
| `options` | 枚举型的可选项列表，每项 `label`（显示名，如「开」「关」）和 `value`（实际下发值，如 `FF00`、`00`） |
| `value` | 按钮型的固定下发值 |
| `desc` | 按钮型的说明文字 |

例：`[{"name":"status","title":"按钮","format":"hex","ctrlType":"enum","options":[{"label":"开","value":"FF00"},{"label":"关","value":"00"}]}]`
表示：向变量 `status` 下发，「开」= hex `FF00`，「关」= hex `00`，对应命令：

```bash
python3 scripts/uzyiot_api.py device-control --addr <addr> --name status --value FF00 --hex   # 开
python3 scripts/uzyiot_api.py device-control --addr <addr> --name status --value 00 --hex     # 关
```

> `control` 为空或 `[]` 表示该产品未配置控制指令。

### 批量查询产品详情

对应接口：`GET /iotapi/system/product/:ID1,:ID2`（与产品详情同一路径，ID 用英文逗号分隔）

| 参数 | 必填 | 说明 |
|------|------|------|
| `--ids` | ✅ | 产品 ID，多个用逗号分隔，如 `85,143` |

```bash
python3 scripts/uzyiot_api.py product-batch --ids 85,143
```

响应 `data` 为**数组**（单个详情的 `data` 是对象），每项字段与产品详情一致（`thing`/`control`/`config` 仍是 JSON 字符串，`control` 未配置时为 `null`）。

> 典型用法：先用 `device-batch` 批量取设备，收集各设备的 `product` 字段去重，再用 `product-batch` 一次取回这些产品的物模型，用于属性翻译。
> 注意：`thing` 里 `access` 可能是 `read`（只读）、`rw`（可读写）、`write`；`rate`/`precision` 表示数值倍率和小数位数。

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

### 批量查询设备详情

对应接口：`GET /iotapi/system/device/:ID1,:ID2,:ID3`（与设备详情同一路径，ID 用英文逗号分隔）

| 参数 | 必填 | 说明 |
|------|------|------|
| `--ids` | ✅ | 设备 ID，多个用逗号分隔，如 `1095,1096,1633` |

```bash
python3 scripts/uzyiot_api.py device-batch --ids 1095,1096,1633
```

响应 `data` 为数组（单个详情的 `data` 是对象），每项含：`id`、`name`、`addr`（设备地址）、`product`（所属产品 ID）、`project`、`status`（`"0"` 正常）、`dk`/`ds`（设备 Key/Secret，部分设备为空）、`lng`/`lat`/`location`/`country`/`province`/`district`、`lastOnline`、`owner`/`ownerDept`、`config`（JSON 字符串或 null）、`createTime`。

> 用途：已有一批设备 ID（如 `device-list` 结果）时，一次取回详情和所属产品 ID，不必逐个调用 `device-detail`。

### 查询设备在线状态

对应接口：`GET /iotapi/system/device/online`

| 参数 | 必填 | 说明 |
|------|------|------|
| `--addr` | ✅ | 设备地址，多个用逗号分隔，如 `addr1,addr2,addr3` |

```bash
python3 scripts/uzyiot_api.py device-online --token <token> --addr addr1,addr2
```

响应 `data` 是数组，每项含 `addr`（设备地址）和 `online`（`1` 在线，`0` 离线）；多个 `addr` 一次批量查询，返回顺序不一定与传入顺序一致，应按 `addr` 匹配。

```json
{"msg":"操作成功","code":200,"data":[{"online":0,"addr":"DJI000001"},{"online":0,"addr":"SXCG24050012"}]}
```

> `addr` 来自设备详情（`device-batch` / `device-detail`）的 `addr` 字段，不是设备 ID。

### 下发设备控制指令

> **控制指令从哪来：** 产品详情（`product-detail`）返回的 `control` 字段就是该产品的「下行控制指令」定义（JSON 字符串，需解析）。下发前应先查它，确定：
> - `name`：可控制的物模型变量名 → 对应 `--name`
> - `options[].value`：该变量允许下发的值（`label` 为含义，如「开」「关」）→ 对应 `--value`
> - `format`：下发值的数据类型，取值来自字典 `iot_data_type`（`integer`/`float`/`string`/`array`，可用 `dict-data --dict-type iot_data_type` 查询）外加 `hex`。对应 CLI：`integer`→`--type int`，`float`→`--type float`，`string`→`--type string`，`hex`→`--hex`（CLI 转成整数再下发）。`array` 暂不支持。
>   - 服务端说明：REST 接口 `POST /system/control/device`（`send_cmd`）只读取 `addr`/`name`/`value`，**不会读取也不会转发 `format`**；Modbus 协议收到字符串值时会按十进制解析，所以 `FF00` 这类 hex 值必须由调用方转成整数（即用 `--hex`），直接发字符串 `"FF00"` 会被解析失败并按 0 下发。前端走 MQTT `p/in`，才会带 `format` 并由协议模块处理。
> - `ctrlType`：控件类型，共三类（见下表）
>
> | `ctrlType` | 类型 | 特征 | 下发取值 |
> |------------|------|------|----------|
> | `enum` | 枚举型 | 带 `options`（`label`/`value`） | 只能从 `options[].value` 里选一个 |
> | `btn` | 按钮型 | 带固定 `value`（`desc` 为按钮说明），点击即下发 | 固定使用该 `value`，无需用户输入 |
> | `input` | 输入型 | 无 `options`/`value`，由用户自由输入 | 用户输入的值；`format` 为 `hex` 时按 16 进制字符串输入并加 `--hex` |
>
> 例：`control` 为
> ```json
> [
>   {"name":"status","title":"按钮","format":"hex","ctrlType":"enum","options":[{"label":"开","value":"FF00"},{"label":"关","value":"00"}]},
>   {"name":"clean","title":"清空","desc":"按钮","value":"1","format":"hex","ctrlType":"btn"},
>   {"name":"set","title":"设置","format":"hex","ctrlType":"input"}
> ]
> ```
> 则：
> - 枚举：「开」= `--name status --value FF00 --hex`，「关」= `--name status --value 00 --hex`
> - 按钮：「清空」= `--name clean --value 1 --hex`（固定值取自 `value`，`format=hex` 故加 `--hex`）
> - 输入：「设置」= `--name set --value <用户输入> --hex`（值由用户提供，需向用户询问）
>
> 产品 `control` 为空时表示未配置控制指令，不要凭空猜测变量名和值，应向用户确认。
>
> 流程：`device-list` 取设备所属产品 ID（`product`）→ `product-detail --id <product>` 读取 `control` → `device-control` 下发。

对应接口：`POST /iotapi/system/control/device`

> 说明：本接口为平台扩展接口。后端收到后会组装物模型「写」消息并通过内部 MQTT（`p/in/<addr>`）下发给设备；设备在线才会真正到达，离线时接口仍返回成功但不下发。

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

> 下发的 `name` 必须是该设备产品物模型里真实存在、且可写的变量；拿不准时先用 `product-detail` 查产品的 `control` 字段（下行控制指令定义：可控变量、`options` 可选值及 `format`），再结合 `thing` 确认。`format` 为 `hex` 时下发加 `--hex`。

---

## 场景 API

### 查询场景列表

对应接口：`GET /iotapi/system/scene/list`

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `--project` | 可选 | — | 项目 ID（登录响应里的 `projectId`） |
| `--page-num` | 可选 | 1 | 页码 |
| `--page-size` | 可选 | 10 | 每页数量 |

```bash
python3 scripts/uzyiot_api.py scene-list --project 1 --page-num 1 --page-size 10
```

响应 `rows` 每条含：`id`（场景 ID）、`title`（场景名称）、`category`（场景分类）、`icon`、`viewType`（该场景拥有的视图类型列表，JSON 字符串，如 `["table","chart"]`；**有几个就有几个视图**，每个值对应 `scene-view --scene-type` 的取值，见「查询场景视图」）、`status`（`"0"` 正常）、`project`、`owner`、`config`、`createTime`、`remark`；`total` 为总数。

### 查询场景详情

对应接口：`GET /iotapi/system/scene/:ID`

| 参数 | 必填 | 说明 |
|------|------|------|
| `--id` | ✅ | 场景 ID（`scene-list` 返回的 `id`） |

```bash
python3 scripts/uzyiot_api.py scene-detail --id 25
```

响应 `data` 是**对象**（列表接口的 `rows` 是数组），字段与场景列表每条一致：`id`、`title`、`category`、`icon`、`viewType`（JSON 字符串，如 `["table","chart"]`，解析后每个值对应一个视图，见「查询场景视图」）、`status`、`project`、`owner`、`ownerDept`、`config`、`createTime`、`remark`。

> 已知场景 ID 时，用它读取 `viewType` 即可知道有哪些视图，不必翻列表。

### 查询场景下的设备

对应接口：`GET /iotapi/system/scene_device/list`

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `--scene` | ✅ | — | 场景 ID（`scene-list` 返回的 `id`） |
| `--page-num` | 可选 | 1 | 页码 |
| `--page-size` | 可选 | 1000 | 每页数量 |
| `--order-by-desc` | 可选 | createTime | 降序排序字段 |

```bash
python3 scripts/uzyiot_api.py scene-device --scene 19
```

响应 `rows` 是场景与设备的**关联记录**，每条含：`id`（关联记录 ID）、`scene`（场景 ID）、`device`（**设备 ID**）、`owner`、`ownerDept`、`createTime`；`total` 为总数。注意这里只有设备 ID，没有设备名称/地址。

> 典型链路：`scene-list` 取场景 ID → `scene-device --scene <id>` 取设备 ID 列表 → `device-batch --ids <逗号拼接的设备 ID>` 取设备详情（含 `addr`、`product`）→ `product-batch` 取物模型 → `device-last` / `history-list` 查数据。

### 查询场景视图

对应接口：`GET /iotapi/system/scene_view/list`

一个场景可以有多个视图（设备列表、设备地图、全景图或自定义视图等），视图的配置和上传的数据都保存在这里。

**如何知道场景有哪些视图：** 看 `scene-list` 返回的场景 `viewType` 字段（JSON 字符串，需解析成数组）。数组里有多少个类型，该场景就有多少个视图；对每个类型各调用一次 `scene-view --scene <场景ID> --scene-type <类型>` 即可取回对应视图（`table` / `map` / `chart` 例外，它们没有视图内容，见下表）。

```bash
# 例：场景 viewType = ["table","pic","panoramic"]
# table 没有视图内容，直接用 scene-device；pic、panoramic 各取一次
python3 scripts/uzyiot_api.py scene-view --scene 25 --scene-type pic
python3 scripts/uzyiot_api.py scene-view --scene 25 --scene-type panoramic
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--scene` | ✅ | 场景 ID（`scene-list` 返回的 `id`） |
| `--scene-type` | 可选 | 视图类型，如 `panoramic`（全景图）；不传则不按类型过滤（不传时的返回范围以实际响应为准） |

```bash
python3 scripts/uzyiot_api.py scene-view --scene 19 --scene-type panoramic
```

响应 `data` 是数组，每项含：`id`（视图 ID）、`scene`（场景 ID）、`sceneType`（视图类型）、`data`（**视图内容，JSON 字符串**，需 `json.loads` 解析，**结构随 `sceneType` 而不同**）、`createTime`。

**视图类型（`viewType` / `sceneType`）与 `data` 结构：**

场景 `viewType` 的取值来自字典 `iot_scene_type`（`dict-data --dict-type iot_scene_type` 可查中文名）；用户自建的视图以 `custom:<视图名称的 URL 编码>` 表示。

| 视图类型 | 含义 | `scene-view` 数据 |
|----------|------|--------------------|
| `table` | 设备列表 | **没有 `scene_view` 记录**，直接用场景绑定的设备：`scene-device` → `device-batch` |
| `map` | 设备地图 | **没有 `scene_view` 记录**，把场景内**所有设备**的经纬度标注到同一张地图上：`scene-device` → `device-batch` 取设备，用每台设备的 `lng`（经度）/ `lat`（纬度）打点（坐标系为**高德坐标系 GCJ-02**，使用高德地图可直接打点；使用其他地图需先做坐标转换），`name` / `location` 作标注文字；`lng` / `lat` 为 `null` 的设备（未设置位置）跳过；可再用 `device-online` 区分在线 / 离线标注 |
| `pic` | 图片轮播 | `data` = `{"interval":轮播间隔,"height":高度,"pics":["图片路径",...]}` |
| `panoramic` | 全景图 | `data` = `{"caption","path","width","height","markers":[...]}`，见下表 |
| `chart` | 曲线图 | **没有需要读取的视图内容**，就是把场景内设备的数据画成曲线：用 `scene-device` → `device-batch` 取设备，再用 `history-list`（历史曲线）/ `device-last` 或 MQTT 实时数据（当前值）绘制 |
| 其他（如三维、组态、曲线展示等）以及 `custom:<名称>` | **HTML 模板视图** | `data` = `{"path":"HTML 文件路径","caption":"标题"}`，视图就是一个上传的 HTML 页面，应用自行加载并组织设备展示 |

> 判断规则：先看 `viewType`——`table` / `map` / `chart` 不需要查 `scene-view`（直接用场景设备的数据绘制）；`pic` / `panoramic` 按各自结构解析；**其余一律按 HTML 模板处理**，取 `data.path` 加载页面，页面内用设备数据填充（页面可使用上一节「面板与 HTML 页面」里的 `SceneSDK` 获取场景内设备的数据）。

`sceneType=panoramic`（全景图）的 `data` 解析后：

| 字段 | 说明 |
|------|------|
| `caption` | 标题 |
| `path` | 全景图片地址 |
| `width` / `height` | 显示宽高（如 `"100%"`、`"700"`） |
| `markers` | 设备标注数组；每项 `position`（`latitude`/`longitude`，图中的球面位置）、`data`（`devId` 设备 ID、`addr` 设备地址）、`listContent`（标注显示名）。同一设备可有多个标注 |

> 用途：`markers[].data.addr` 可直接用于 `device-last` / `history-list` 查该设备数据。

---

## 字典 API

### 查询字典数据

对应接口：`GET /iotapi/system/dict_data/list`

| 参数 | 必填 | 说明 |
|------|------|------|
| `--dict-type` | ✅ | 字典类型，如 `iot_data_type`（物模型数据类型） |

```bash
python3 scripts/uzyiot_api.py dict-data --dict-type iot_data_type
```

响应 `data` 为数组，每项含：`dictValue`（字典值，实际使用的取值）、`dictLabel`（显示名）、`dictType`、`dictCode`、`dictSort`、`status`（`"0"` 正常）、`isDefault`、`listClass`、`cssClass`、`remark`、`createTime`、`createBy`。

例：`iot_data_type`（物模型 `thing` 中的 `type`）：

| dictValue | dictLabel |
|-----------|-----------|
| `integer` | 整形 |
| `float` | 浮点 |
| `string` | 字符串 |
| `array` | 数组 |

> 用途：把产品 `thing` / `control` 等字段里的编码值翻译成中文含义（取 `dictValue` 对应的 `dictLabel`）。

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

### 批量查询设备实时数据

对应接口：`GET /iotapi/system/device/history/last?addr=...&batch=true`（与单设备实时数据同一路径，多一个 `batch=true`）

| 参数 | 必填 | 说明 |
|------|------|------|
| `--addr` | ✅ | 设备地址，多个用逗号分隔，如 `addr1,addr2`；设备很多时分批 |

```bash
python3 scripts/uzyiot_api.py device-last-batch --addr SXCG24050012,SXCG24050016,SXCG24050017
```

响应 `data` 是**数组**，每项是一台设备的最新一条上报记录，结构与单设备 `device-last` 的 `data` 相同，只是多了 `addr` 用来标识设备：

| 字段 | 说明 |
|------|------|
| `addr` | 设备地址 |
| `createtime` | 采集时间（Unix 秒） |
| `alarmrule` | 触发中的告警规则，空字符串表示无告警 |
| 其余键 | 物模型属性键值对，键是属性名（`thing` 的 `name`），如 `temp1`、`temp2` |

```json
{
  "msg": "操作成功",
  "code": 200,
  "data": [
    {
      "temp2": 2.75509e-40,
      "temp1": 9.1837e-41,
      "createtime": 1794409206,
      "alarmrule": "",
      "addr": "864536071820615A009"
    }
  ]
}
```

> 单设备 `device-last` 的 `data` 是单个对象（不含 `addr`）；批量接口的 `data` 是数组，每项含 `addr`。按 `addr` 匹配每台设备，返回顺序不一定与传入顺序一致；设备没有上报过数据时，该项可能只有 `addr`。
> 属性名要翻译成别名和单位时，用 `product-batch` 取物模型后对照（`device-last-batch` 不支持 `--readable`）：先用 `device-batch` 取设备的 `product`，再按 `thing` 的 `name` 映射到 `title` / `unit`。

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

## 设备接入（MQTT / TCP 透传）

> 本章与前面的 REST API 不同：设备侧通过 **长连接** 与平台通讯，不经过 `uzyiot_api.py`。
> 设备所需的 `addr`、`dk`/`ds`（一机一证）、`pk`/`ps`（一型一密）可从 `device-detail` / `device-batch` / `product-detail` 获取（`dk`/`ds`/`pk`/`ps` 是敏感信息，勿随意输出）。

### 认证方式

| 方式 | 说明 | 适用 |
|------|------|------|
| 一机一证（推荐） | 每台设备使用自己的设备 Key（`dk`）/ 设备 Secret（`ds`） | 安全性高 |
| 一型一密 | 同一产品下所有设备共用产品 Key（`pk`）/ 产品 Secret（`ps`） | 批量生产设备 |

### MQTT 接入

适用于原生支持 MQTT 的设备（传感器、控制器、DTU 等）。前置：已创建产品（协议标识 `mqtt-json`）并添加设备。

| 认证方式 | clientId | username | password |
|----------|----------|----------|----------|
| 一机一证 | `uzy_1_{addr}` | `{dk}` | `{ds}` |
| 一型一密 | `uzy_2_{addr}` | `{pk}` | `{ps}` |

> 服务端按 clientId 前缀 `uzy_1_` / `uzy_2_` 区分认证方式，前缀之后的部分即设备地址 `addr`；认证失败返回用户名或密码错误。

连接地址：**与 API 地址一致**——主机名取 API 接入地址（`env.ini` 的 `host`，默认 `prod.uzyiot.com`，不带 `https://`）；端口 `1883`（TLS 为 `8883`）。切换到其他平台时，MQTT 地址随 `host` 一起切换。

| Topic | 设备动作 | 说明 |
|-------|----------|------|
| `d/out/{addr}` | 发布（publish） | 设备上报数据，JSON 格式并符合产品物模型，平台解析后存储 |
| `d/in/{addr}` | 订阅（subscribe） | 平台下发指令给设备 |

接入流程：
1. 设备上电，用上表参数连接 Broker
2. 连接成功后订阅 `d/in/{addr}`，监听平台下发
3. 定时或按需向 `d/out/{addr}` 发布采集数据
4. 平台设备状态变为在线，实时数据可查（可用 `device-online` / `device-last` 验证）

### TCP 透传接入

适用于工业 DTU、Modbus 网关等经 TCP 透传的设备。前置：已创建产品（协议标识 `tcp-json` 或自定义 TCP 协议）并添加设备。

**连接地址：** 同样与 API 地址一致（`env.ini` 的 `host` 主机名）；TCP 端口以平台实际开放为准，可在平台设备详情「设备鉴权 → TCP 透传接入」页面查看。

**1. 登录注册**（建立 TCP 连接后先发送。报文以文本 `\r\n` 结尾，不可省略；注意平台按**文本字符**匹配——即 4 个 ASCII 字符 `\` `r` `\` `n`（十六进制 `5C 72 5C 6E`），不是回车换行字节 `0D 0A`；在 DTU 配置里直接填写 `\r\n` 文本即可）：

| 认证方式 | 报文 |
|----------|------|
| 一机一证 | `reg,1,{addr},{dk},{ds}\r\n` |
| 一型一密 | `reg,2,{addr},{pk},{ps}\r\n` |

字段之间的分隔符可以是 `,`、`|` 或 `/`。登录失败时平台向设备返回错误码并断开连接：`01` 认证失败（设备或密钥不对）、`02` 产品协议未找到、`99` 其他错误；登录成功没有专门的成功响应，设备可直接开始发心跳和数据。

**2. 心跳保活**：定时发送 `ping\r\n`，建议间隔 30～60 秒，避免被服务器因超时断开。

**3. 数据上报与指令接收**：同一条 TCP 连接双向通信——设备按物模型把数据以 JSON 发送到平台；平台的控制指令直接通过该连接推送给设备（具体二进制/JSON 格式取决于协议插件）。

流程：建立 TCP 长连接 → 发 `reg` → 未收到错误码即登录成功 → 定时 `ping` → 上报数据。


### 接入方式对比

| 维度 | MQTT 设备 | TCP 设备 | 应用 MQTT 对接 |
|------|----------|---------|--------------|
| 适用对象 | 原生 MQTT 设备 | DTU / Modbus 网关 / TCP 透传 | 第三方业务系统 |
| 认证 | 一机一证 / 一型一密 | 一机一证 / 一型一密 | AppID + Token |
| 上报 | 发布 `d/out/{addr}` | TCP 直连发送 | — |
| 接收下发 | 订阅 `d/in/{addr}` | TCP 直连接收 | 见下文 |
| 心跳 | MQTT keepalive | `ping\r\n` | MQTT keepalive |

---

## 协议解析

设备把数据发到平台后，平台按产品的**协议标识**把原始数据解析成物模型 JSON，再保存并推送给应用。当前支持三种协议：

| 协议标识 | 名称 | 接入 | 数据特点 |
|----------|------|------|----------|
| `tcp-json` | JSON over TCP | TCP | 设备主动发送 JSON，多条之间以文本 `\r\n` 分隔 |
| `Modbus-RTU` | Modbus RTU over TCP | TCP | 设备是 Modbus 从机，**平台作为主站按物模型配置轮询**读取，经 DTU / 网关透传 |
| `mqtt-json` | JSON over MQTT | MQTT | 设备向 `d/out/{addr}` 发布 JSON |

三种协议解析出原始数据后，都进入同一套**公共处理**，输出统一的物模型 JSON：

```json
{ "ts": 1741015860, "temp": { "value": 27.9, "ts": 1741015860 } }
```

**公共处理规则**（按产品物模型 `thing` 逐项处理）

1. **公式（`formula`）先行**：物模型属性可配置 `formula`（公共函数名），在以下规则之前执行，把设备的原始 JSON 重组成物模型需要的结构。能力包括：路径引用 `#a/b/items/1/c`（`items/N` 取数组第 N 个元素，从 1 开始）、当前时间 `${CURRENT_TIME}`、时间字符串转 Unix 秒、正则提取 / 替换
2. **只保留物模型中定义的属性**：键不在 `thing` 的 `name` 里则丢弃；本次没有上报的属性不更新
3. **类型**：`string` 原样保留；`integer` / `int` / `float` 收到字符串时转成数字
4. **倍率和偏移**：`值 = 原值 × rate + offset`（`rate` 默认 1，`offset` 默认 0）
5. **精度**：配置了 `precision` 则按该小数位四舍五入
6. **占位值**：值以 `alink_ignore` 开头表示「本次无有效数据」，原样保留不转换
7. 时间戳：每个属性可带自己的 `ts`；缺省用顶层 `ts`；顶层 `ts` 缺省用平台接收时间

> `rate`、`precision` 在**入库前**就已经应用，应用从 REST 或 MQTT 拿到的 `value` 已是换算后的最终值，**不需要再乘 `rate`**。

### JSON over TCP（`tcp-json`）

**接入：** TCP 连接 → `reg` 登录（见「TCP 透传接入」）→ 定时 `ping` → 发送数据。

**数据格式：** 每条数据是一个 JSON 对象，多条之间以文本 `\r\n` 分隔（同样是 4 个 ASCII 字符，不是 `0D 0A` 字节），可以一次连发多条：

```
{"Serial number":"afaa6832380e","Temperature 1":12.8,"Humidity":49.8}\r\n{"Serial number":"afaa6832380f","Temperature 1":13.1,"Humidity":50.2}\r\n
```

**要点：**
- 每条 JSON 必须带 **`Serial number`** 字段，值是数据所属设备的地址；平台靠它找到设备，缺失则该条数据无法处理
- `tcp-json` 面向**网关类产品**：设备以网关地址登录，每条数据用 `Serial number` 指明所属子设备
- 设备原始键通常与物模型属性名不一致（如 `Temperature 1`），用物模型属性的 `formula` 映射成属性名（如 `temperature`），再走公共处理规则
- 当前**不支持下发控制**：平台收到写指令后不会通过 TCP 连接转发给设备

### Modbus RTU over TCP（`Modbus-RTU`）

适用于 Modbus RTU 设备（仪表、传感器、继电器等）经 DTU / 网关透传到 TCP。设备端不需要理解平台协议：DTU 完成 `reg` 登录后，对平台发来的 Modbus RTU 请求透传应答即可。

**工作方式：** 平台是 Modbus **主站**，按产品物模型里配置的寄存器**周期性轮询**，把应答解析成属性值；控制指令则转成写请求下发。

**物模型配置（每个属性的 `modbus` 对象）：**

| 字段 | 说明 |
|------|------|
| `rFunCode` | 读功能码，16 进制字符串，如 `"01"`（线圈）、`"03"`（保持寄存器）、`"04"`（输入寄存器） |
| `start` | 起始地址，16 进制字符串，如 `"0000"` |
| `quantity` | 读取数量（寄存器 / 线圈个数） |
| `wFunCode` | 写功能码，16 进制字符串，如 `"05"`（写单个线圈）、`"06"`（写单个寄存器） |
| `slaveId` | 从站地址，16 进制字符串，缺省 `"01"`；网关下的子设备以子设备地址作为从站地址 |
| `signed` | `"signed"`（默认）/ `"unsigned"` |
| `endianness` | 字节序：`"little"`（默认）/ `"big"`；`"big2"` / `"little2"` 表示每个 16 位字内先交换两个字节再按大端 / 小端解释 |

物模型属性本身的相关字段：`type`（`integer` / `float` / `string`）、`access`（`read` / `rw` 会被轮询；`write` 只写不轮询）、`freq`（轮询周期，秒；缺省或 0 为 30 秒）、`rate` / `precision` / `offset`（公共处理）。

**请求帧：** `[从站地址 1B][功能码 1B][起始地址 2B][数量 2B][CRC16 2B]`，CRC16 为标准 Modbus CRC，低字节在前。例如从站 `01` 读保持寄存器 `0000` 起 1 个：`01 03 00 00 00 01 84 0A`。

**应答解析：**
1. 校验 CRC16 和从站地址，不符则本次读取作废
2. 读应答取数据区（前有 1 字节长度）；写应答原样回显
3. 按**数据区字节数**确定位宽（1 / 2 / 4 / 8 字节 → 8 / 16 / 32 / 64 位），再按 `signed`、`endianness` 和属性 `type` 解释成数值
4. 等待应答最长 10 秒；超时则该属性本轮记为占位值 `alink_ignore_sync_data_timeout`，其他错误（CRC、从站地址不符）该属性本轮跳过
5. 一轮轮询的所有属性合并成一条 JSON，进入公共处理规则

**下发控制（写）：**
- `name` 必须是 `access` 为 `rw` / `write` 且配置了 `modbus` 的属性
- 值统一转成**整数**：整数原样、浮点四舍五入、字符串默认按十进制解析，`format` 为 `hex` 时按 16 进制解析
- 写帧：`[从站][wFunCode][起始地址 2B][值 2B][CRC16]`。即只支持**写单个线圈（05）/ 写单个寄存器（06）**，不支持一次写多个寄存器（10H）
- 线圈开 = `FF00`（65280），关 = `0000`（0）；所以 REST 下发线圈控制要用 `--hex`（见「设备 API」）

**网关与子设备：** 网关产品下的子设备共用网关的 TCP 连接，请求逐个串行发送，以子设备地址（16 进制）作为从站地址。

### JSON over MQTT（`mqtt-json`）

**接入：** MQTT 连接（clientId / username / password 见「MQTT 接入」）→ 订阅 `d/in/{addr}` → 向 `d/out/{addr}` 发布数据。

**数据格式：** 一个 JSON 对象，键是物模型属性名，值可以是裸值，也可以是带时间戳的对象；顶层 `ts` 为 Unix 秒整数：

```json
{
  "ts": 1741015860,
  "temp": 27.9,
  "humidity": { "value": 65.0, "ts": 1741015859 }
}
```

**要点：**
- 设备直接按物模型属性名上报；上报格式与物模型不一致时，用 `formula` 重组
- 物模型里没有的键会被丢弃，所以新增数据点要先在产品物模型里定义
- 设备由 MQTT 连接本身标识（clientId 里的地址），**不需要**在 JSON 里再带设备地址

**下行（平台 → 设备）：** 通过 REST（`device-control`）或应用 MQTT 下发控制时，平台组装 `{"type":"write","name":"<属性名>","value":<值>}`（经应用 MQTT 下发且带 `format` 时一并携带），设备从 `d/in/{addr}` 收到后自行解析并执行。

---

## 应用侧 MQTT 接入

第三方应用系统通过 MQTT 与平台交互：**实时接收设备数据**、**下发控制**、**参与数据同步**。（区别于上面的设备侧接入。）

### 连接

先用 `login` 获取 `token` 和 `projectId`（Token 有效期 `expire` 秒，过期前需重新获取），再连接 MQTT：

| 项 | 值 |
|----|----|
| Broker（后端 / 原生客户端） | 与 API 地址一致（`env.ini` 的 `host` 主机名，默认 `prod.uzyiot.com`），端口 `1883`（TLS `8883`） |
| Broker（浏览器，WebSocket） | 明文 `ws://{host}:8083/mqtt`；加密 `wss://{host}:8084/mqtt`（页面是 https 时必须用 wss）；ClientId、Username、Password 规则相同 |
| ClientId | `app_{appId}_{随机串}`（必须以 `app_` 开头） |
| Username | `{appId}` |
| Password | `{token}` |

> 服务端校验：clientId 以 `app_` 开头，且 Username 必须等于该 Token 对应的 `appId`，否则认证失败。Token 过期后重连会失败，需先重新登录。

### Topic 一览（以应用视角）

| Topic | 应用动作 | 说明 |
|-------|----------|------|
| `app/in/{projectId}/{appId}` | 订阅 | 平台推送给该应用的通知；**数据同步事件**从这里收到（见下节） |
| `p/out/{addr}` | 订阅 | 某台设备的上行数据（按设备维度） |
| `s/out/{projectId}/{sceneId}/{addr}` | 订阅 | 设备上行数据**和设备告警通知**（按场景维度，可用通配符订阅整个场景），用 `msgType` 区分：`deviceData` / `deviceAlarm` |
| `p/in` | **发布** | 应用向平台发消息：**下发设备控制**、**回报同步状态** |

> ⚠️ 方向以**应用**为准：应用向 `p/in` **发布**（下发控制、回报同步状态），向 `p/out/...`、`s/out/...`、`app/in/...` **订阅**。注意设备详情页「设备鉴权」里列出的 Topic 方向是站在**平台**角度写的（如 `p/in` 标为 subscribe、`p/out` 标为 publish），应用侧不要照搬。

### 接收设备数据

- `p/out/{addr}`：载荷是该设备本次上报的数据对象。
- `s/out/{projectId}/{sceneId}/{addr}`：载荷带封装：

```json
{"msgType":"deviceData","data":{"addr":"000001","time":1741015860,"data":{"temp":{"value":27.9,"ts":1741015860}}}}
```

场景维度的 Topic 适合"一个工地一个场景"这类按场景管理设备的应用，只需订阅对应场景。若设备未加入任何场景，服务端会以 `all` 作为 `sceneId` 发布。

> 设备数据以 `p/out/...`、`s/out/...` 为准；`app/in/{projectId}/{appId}` 主要承载同步通知。部分部署也会在 `app/in/...` 上推送设备上报，格式为 `{"addr","created","data":{"<属性名>":{"value","ts"}}}`，应用应按 `msgType` / 字段区分消息类型，并忽略不认识的消息。

### 接收告警事件通知

设备触发告警规则（或告警恢复）时，平台会向应用推送告警通知。

**Topic：** 与场景设备数据相同，`s/out/{projectId}/{sceneId}/{addr}`（设备若不属于任何场景，`sceneId` 为 `all`）；**仅在设备属于某个项目时才发布**。订阅整个场景的通配符：`s/out/{projectId}/{sceneId}/+`，订阅整个项目：`s/out/{projectId}/+/+`。该 Topic 上同时有设备数据和告警，**必须按 `msgType` 区分**：

| `msgType` | 含义 |
|-----------|------|
| `deviceData` | 设备上报数据 |
| `deviceAlarm` | 设备告警 / 告警恢复通知 |

**触发条件：** 告警规则的通知方式（`notifyType`）里包含 `app` 时，才会推送到应用侧 MQTT；规则里选的其他通知方式（`site` 站内通知、`wechat` 微信、`sms` 短信）走各自的渠道，应用收不到。

**告警消息：**

```json
{
  "msgType": "deviceAlarm",
  "data": {
    "addr": "SXCG24050012",
    "time": 1741015860,
    "data": {
      "type": "alarm",
      "stat": { "<属性名>": { "value": 27.9, "ts": 1741015860 } },
      "rule": { "id": 1, "name": "温度过高", "level": "2", "type": "1", "content": "请及时检查并处理!" },
      "wrongInfos": [ ... ]
    }
  }
}
```

**告警恢复消息：** 结构相同，`data.type` 为 `"recover"`，且**没有** `wrongInfos`。

| 字段 | 说明 |
|------|------|
| `data.addr` | 设备地址 |
| `data.time` | 消息发送时间（Unix 秒） |
| `data.data.type` | `alarm` 触发告警 / `recover` 告警恢复 |
| `data.data.stat` | 触发时设备的状态，键为物模型属性名，值含 `value`、`ts` |
| `data.data.rule` | 触发的告警规则：`id`、`name`（规则名）、`level`（`"1"`～`"4"` 对应一级～四级告警，其他值为普通事件）、`type`（`"1"` 告警 / `"2"` 事件）、`content`（处理建议，为空时用默认文案）等 |
| `data.data.wrongInfos` | 仅告警时有：不满足条件的具体项（哪些属性异常） |

**应用的处理建议：**
1. 订阅场景 Topic 后，按 `msgType` 分流；对 `deviceAlarm` 用 `data.addr` 关联本地设备（`device-batch` 取到的设备）
2. `type == alarm`：展示 / 记录告警（规则名、级别、异常属性），可结合产品物模型把属性名翻译成别名和单位
3. `type == recover`：把该设备对应规则的告警标记为已恢复
4. 告警通知是**实时推送**，应用离线期间的告警不会重发；本文档未提供告警记录的查询接口，需要完整告警记录的应用应保证订阅连接稳定（断线自动重连），并在重连后以设备实时数据（`device-last`）校准状态
5. 对不认识的 `msgType` 直接忽略

### 下发设备控制（MQTT 方式）

应用向 `p/in` 发布：

```json
{"msgType":"control_device","data":{"addr":"<设备地址>","type":"write","name":"<物模型变量名>","value":<值>,"format":"<可选>"}}
```

平台转换后向 `p/in/{addr}` 转发（设备经 `d/in/{addr}` 收到）。服务端行为：
- `addr`、`type`、`name`、`value` 必填，缺失则消息被忽略；`format` 可选，会透传给协议模块（Modbus 下 `format=hex` 时把字符串按 16 进制解析，否则按十进制）
- 设备当前不在线（无会话）时，指令会缓存（`device_cmd`），待设备上线再处理
- 同样的控制也可走 REST：`device-control` 子命令（见「设备 API」），区别是 REST 不转发 `format`

---

## 应用数据同步机制

适用于应用在本地维护一份平台设备/产品数据的场景：平台数据变化后，通过 MQTT 通知应用重新同步，应用同步完后回报状态。

### 流程

```
平台                                   应用
 │  ① 管理端触发同步（REST）            │
 │  ② 发布到 app/in/{projectId}/{appId} │
 │ ───────────────────────────────────► │ 收到 sync 事件
 │  同时置状态 sync_status = wait       │ ③ 用 REST API 拉取数据（device-list 等）
 │                                      │ ④ 向 p/in 发布同步状态
 │ ◄─────────────────────────────────── │
 │  更新 sync_status                    │
```

**① 触发**：由平台管理端**手动**触发——在项目的「应用接入」页面选择应用并选择同步内容：「基本数据（设备、产品、场景）」或「设备在线状态」（服务端 `sync_data`，入参 `id`=应用记录 ID、`event`=事件类型）。也可以对整个项目触发，此时该项目下所有应用都会收到事件。平台不会在数据一变化时自动推送，所以应用仍需要定时轮询兜底。

**② 应用收到**（订阅 `app/in/{projectId}/{appId}`）：

```json
{"msgType":"sync","data":{"event":"syncBaseData"}}
{"msgType":"sync","data":{"event":"syncDeviceStatus"}}
```

> **收到同步消息后，项目 ID 从哪来：** 消息体只有 `msgType` 和 `event`，没有 `projectId`。应用不需要从消息里取，因为：
> 1. 应用连接 MQTT 前必须先 `login` 换 token，**登录响应里就返回了 `projectId`**（应用只属于一个项目），应用在内存 / 配置里保存它，收到同步消息后直接用它调用接口，如 `device-list --project <projectId>`、`scene-list --project <projectId>`
> 2. 订阅的 Topic `app/in/{projectId}/{appId}` 本身也带了 `projectId` 和 `appId`，可以从收到消息的 Topic 里解析出来，用来和登录时保存的值核对（一致才处理）
> 3. Token 过期重新登录后，同样以新的登录响应为准更新 `projectId`

| event | 含义 | 应用建议动作 |
|-------|------|--------------|
| `syncBaseData` | 基础数据变更：**设备、产品、场景** | 先拉设备（`device-list` / `device-batch`），再按设备的产品（去重）同步产品（`product-batch`） |
| `syncDeviceStatus` | 同步**设备状态**（在线 / 离线），用于故障后恢复在线状态；只涉及状态，不涉及设备、产品、场景本身的变化 | 用 `device-online` 批量重新查询本地设备的在线状态 |

**③ 收到事件后，必须通过 API 同步数据**：同步事件**只是一个通知，不携带任何变更内容**（载荷里只有 `event`，没有设备 ID、产品 ID 或变更明细），所以应用必须主动调用 REST API 把最新数据拉回来，再与本地库比对更新。

`syncBaseData`（基础数据变更，**包含设备、产品、场景**，所以场景变化也由它通知，没有单独的场景事件）：

> 应用层关心的是**设备**，产品只是为了解释设备数据（物模型、控制、面板）而顺带同步：以设备为主线，设备用到哪些产品就同步哪些产品。

1. 先回报 `{"msgType":"sync","data":{"status":"doing"}}`
2. 确保 token 有效（过期或 HTTP 401 / 403 则先重新 `login`）
3. **先拉设备**：分页调用 `device-list --project <projectId>`（`--page-num` 递增，直到取满 `total`）；需要更多字段时用 `device-batch` 按设备 ID 批量取详情
4. **再按设备的产品同步产品**：从设备数据的 `product` 字段收集产品 ID 并**去重**，用 `product-batch --ids <产品ID列表>`（或单个 `product-detail`）取回这些产品的 `thing` / `control` / `category` 等。只同步设备实际用到的产品，不需要把平台所有产品全拉一遍
5. **同步场景**（场景可能新增、改名、调整视图或绑定的设备）：分页调用 `scene-list --project <projectId>` 取场景（含 `viewType`）；对每个场景调用 `scene-device --scene <id>` 取绑定的设备 ID，重建本地「场景—设备」关系；需要视图内容的场景（`pic` / `panoramic` / HTML 模板视图）再调用 `scene-view`。应用不使用场景则跳过这一步
6. 与本地库比对：按设备 `id`（或 `addr`）、产品 `id` 做新增、更新；**平台已不存在的设备、产品、场景及场景绑定关系按需在本地标记删除或停用**（事件不会告诉你哪些被删了，只能靠全量比对发现）
7. 全部成功后回报 `{"msgType":"sync","data":{"status":"succ"}}`；任一步骤失败回报 `{"msgType":"sync","data":{"status":"fail"}}`，并稍后重试

`syncDeviceStatus`（同步设备状态：在线 / 离线；只更新状态，不需要重新拉设备、产品、场景）：

> 用途：故障恢复。平台或链路发生故障后，应用本地记录的在线状态可能与实际不一致（例如漏掉了上下线通知），管理员触发该事件，让应用把在线状态重新校准到平台的最新状态。应用收到后应以平台返回的结果**覆盖**本地在线状态，而不是只做增量修改。

1. 取出本地库里需要关注的设备 `addr` 列表
2. 调用 `device-online --addr addr1,addr2,...`（多个 `addr` 一次批量查询，设备很多时分批），按返回的 `addr` 匹配更新本地在线状态（`online`：`1` 在线，`0` 离线）
3. 回报 `succ` / `fail`

> 注意：事件到达时数据可能在短时间内连续变更，应用不要对每个事件都全量拉取一遍——可以对事件做合并（例如处理中又收到同类事件，只需在本轮结束后再同步一次）。

**④ 应用回报**（向 `p/in` 发布）：

```json
{"msgType":"sync","data":{"status":"succ"}}
```

| status | 说明 |
|--------|------|
| `doing` | 同步进行中 |
| `succ` | 同步成功 |
| `fail` | 同步失败 |

服务端对同步状态的处理：触发同步时把该应用的 `sync_status` 置为 `wait`；收到应用向 `p/in` 发布的 `msgType=sync` 且带 `status` 的消息后，把该应用的 `sync_status` 更新为所报的 `status` 值（原样写入）。**应用必须以自己的 `app_` 连接身份发布**，服务端用连接认证时保存的 `appId` 来确定更新哪个应用。

### 最佳实践

1. 一个对接系统一套 AppID，权限互不影响
2. 启动时获取 token 与 `projectId`，先全量同步一次设备/产品数据到本地
3. 定时轮询 + 监听同步事件双保险，防止漏数据
4. Token 到期前主动重新登录；MQTT 断线要自动重连，重连前先确认 token 未过期
5. 收到 `sync` 事件后先回 `doing`，完成后回 `succ`，失败回 `fail`，便于平台侧查看同步状态

---

## 构建应用的推荐方式

### 架构建议

- **AppSecret 只放后端。** 前端页面不要持有 AppSecret：由后端调用 `login` 换取 token，再代理 REST 请求或把 token 下发给前端
- **Token 管理：** 登录响应里的 `expire` 是有效期（秒）。后端缓存 token，到期前主动续期；遇到 HTTP 401 / 403 立即重新登录并重试一次
- **产品信息缓存：** 产品（物模型、控制指令、面板）变化很少，且被多台设备共用，应按产品 ID 缓存，收到 `syncBaseData` 同步事件时刷新
- **实时数据优先用 MQTT 推送**，REST 轮询（`device-last`）作为兜底；浏览器里使用 MQTT over WebSocket：`ws://{host}:8083/mqtt`，页面是 https 时用 `wss://{host}:8084/mqtt`（`host` 同 API 主机名，如 `wss://prod.uzyiot.com:8084/mqtt`），认证参数与应用侧 MQTT 相同；https 页面不能使用 `ws://`，会被浏览器拦截

### 流程 1：项目看板 / 场景总览

```
login → projectId
scene-list(project) → 场景列表（title / viewType）
scene-device(scene) → 设备 ID 列表
device-batch(ids)   → 设备详情（addr / product / 经纬度）
product-batch(去重后的 product) → 物模型 / 控制 / 面板
device-online(addr 列表) → 在线状态
device-last-batch(addr 列表) → 批量取最新数据，按物模型翻译为「别名 值 单位」
```

### 流程 2：设备详情页

```
device-detail(id) → addr、product
product-detail(product) → thing / control / category
 ├─ category == default：每个物模型字段一张卡片，数据来自 device-last（或 MQTT 实时）
 └─ category 为 HTML 路径：加载该 HTML 面板，把设备数据传给页面
history-list(addr, begin, end[, step]) → 历史曲线 / 表格
control 非空 → 渲染控制按钮（enum / btn / input），点击后 device-control
```

### 流程 3：场景视图页

```
scene-detail(id) → viewType（视图类型列表）
对每个 viewType：
 ├─ table → scene-device + device-batch 渲染设备列表
 ├─ map   → 把场景所有设备的 lng / lat 标注到一张地图上（跳过无坐标设备）
 ├─ chart → 用场景设备的 history-list / device-last 画曲线
 ├─ pic / panoramic → scene-view(scene, sceneType) 后按各自 data 结构渲染
 └─ 其他 / custom:<名称> → scene-view 取 data.path，作为 HTML 模板加载并填充设备数据
视图中引用的设备（devId / addr）→ 用 device-batch / device-last 补充数据
```

### 流程 4：数据同步服务（把平台数据同步到本地库）

```
启动：login → 分页拉取 device-list → 收集设备的 product 去重 → product-batch → 写入本地库
常驻：应用侧 MQTT 订阅 app/in/{projectId}/{appId}
  收到 syncBaseData     → 先重新拉取设备，再按设备的产品（去重）同步产品，再同步场景及场景设备
  收到 syncDeviceStatus → 批量 device-online 刷新在线状态
  完成后向 p/in 回报 {"msgType":"sync","data":{"status":"succ"}}
兜底：定时轮询
```

### 流程 5：设备控制

```
product-detail → control（可控制项）
按 ctrlType 取值：btn 用固定 value / enum 从 options 选 / input 由用户输入
按 format 转值：hex → 转整数；integer / float → 转数字
device-control(addr, name, value)；设备离线时接口仍返回成功但不下发，下发前可先 device-online 确认
```

---

## API 速查表

| 子命令 | 方法 | 路径 | 必填参数 |
|--------|------|------|---------|
| `login` | POST | `/iotapi/system/user/app/login` | appId, appSecret |
| `product-list` | GET | `/iotapi/system/product/list` | — |
| `product-detail` | GET | `/iotapi/system/product/:ID` | id |
| `product-batch` | GET | `/iotapi/system/product/:ID1,:ID2,...` | ids |
| `device-list` | GET | `/iotapi/system/device/list` | — |
| `device-detail` | GET | `/iotapi/system/device/:ID` | id |
| `device-batch` | GET | `/iotapi/system/device/:ID1,:ID2,...` | ids |
| `device-online` | GET | `/iotapi/system/device/online` | addr |
| `scene-list` | GET | `/iotapi/system/scene/list` | — |
| `scene-detail` | GET | `/iotapi/system/scene/:ID` | id |
| `scene-device` | GET | `/iotapi/system/scene_device/list` | scene |
| `scene-view` | GET | `/iotapi/system/scene_view/list` | scene |
| `dict-data` | GET | `/iotapi/system/dict_data/list` | dict-type |
| `device-last` | GET | `/iotapi/system/device/history/last` | addr |
| `device-last-batch` | GET | `/iotapi/system/device/history/last?batch=true` | addr |
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
- 本 skill 覆盖开发者接入的 **REST API**，外加平台扩展的 **设备控制接口**（`device-control`）；设备侧 MQTT/TCP 接入、应用侧 MQTT 消息收发与数据同步属于长连接协议，已在文档「设备接入」「应用侧 MQTT 接入」「应用数据同步机制」中说明，但不在本 CLI 范围内（CLI 只封装 REST）。
- 查看所有子命令：`python3 scripts/uzyiot_api.py -h`；查看单个子命令参数：`python3 scripts/uzyiot_api.py <command> -h`。
