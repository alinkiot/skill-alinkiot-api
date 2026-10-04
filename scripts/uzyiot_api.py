#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
uzyiot_api.py — 有智云智能物联网平台 开发者接入 REST API CLI

实现《有智云物联网平台操作手册》第十章「开发者接入指南」中的全部 REST API：

  鉴权
    login              获取鉴权 Token（POST /iotapi/system/user/app/login）

  产品
    product-list       查询产品列表（GET /iotapi/system/product/list）
    product-detail     查询产品详情（GET /iotapi/system/product/:ID）

  设备
    device-list        查询设备列表（GET /iotapi/system/device/list）
    device-detail      查询设备详情（GET /iotapi/system/device/:ID）
    device-online      查询设备在线状态（GET /iotapi/system/device/online）

  数据
    device-last        查询设备实时数据（GET /iotapi/system/device/history/last）
    history-list       查询设备历史数据（GET /iotapi/system/history/list）

  控制
    device-control     向设备下发控制指令（POST /iotapi/system/control/device）

鉴权凭证来源（优先级从高到低）：
  1. 命令行 --token
  2. 命令行 --app-id / --app-secret（自动登录换取 token）
  3. 环境变量 UZYIOT_TOKEN
  4. 环境变量 UZYIOT_APP_ID / UZYIOT_APP_SECRET（自动登录）

示例：
  # 登录拿 token
  python3 uzyiot_api.py login --app-id xxx --app-secret yyy

  # 用 app-id/secret 直接调用（脚本内部自动登录）
  python3 uzyiot_api.py product-list --app-id xxx --app-secret yyy --page-num 1 --page-size 20

  # 用已有 token 调用
  python3 uzyiot_api.py device-list --token 38ad4ce6... --project 16

输出：JSON（stdout）；错误信息（stderr）
退出码：0=成功，1=调用失败，2=token 过期/鉴权失败（HTTP 401/403）
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE_URL = "https://prod.uzyiot.com"
TIMEOUT = 30

# env.ini 位于 skill 根目录（本脚本在 skills/uzyiot-api/scripts/ 下）
_ENV_INI_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "env.ini"
)


# --------------------------------------------------------------------------- #
#  env.ini 读取
# --------------------------------------------------------------------------- #
def load_env_ini(path=_ENV_INI_PATH):
    """
    读取简单的 key=value 配置文件，返回 dict。
    支持 '#' / ';' 行注释，忽略空行；缺失文件返回空 dict。
    键名大小写不敏感处理：原样保留，调用方自行匹配。
    """
    cfg = {}
    if not os.path.isfile(path):
        return cfg
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith(";"):
                    continue
                if "=" not in line:
                    continue
                key, _, val = line.partition("=")
                cfg[key.strip()] = val.strip().strip('"').strip("'")
    except OSError:
        pass
    return cfg


def creds_from_env_ini():
    """
    从 env.ini 解析 (app_id, app_secret)。
    兼容键名：appId / app_id / APP_ID，Secret / appSecret / app_secret / APP_SECRET。
    """
    cfg = load_env_ini()
    if not cfg:
        return None, None
    lower = {k.lower(): v for k, v in cfg.items()}
    app_id = lower.get("appid") or lower.get("app_id")
    app_secret = (
        lower.get("secret")
        or lower.get("appsecret")
        or lower.get("app_secret")
    )
    return app_id, app_secret


def host_from_env_ini():
    """
    从 env.ini 解析平台地址，返回完整 base_url（如 https://prod.uzyiot.com）或 None。
    兼容键名：host / baseUrl / base_url / BASE_URL。
    若值不带协议前缀（如仅 'prod.uzyiot.com'），自动补 https://。
    """
    cfg = load_env_ini()
    if not cfg:
        return None
    lower = {k.lower(): v for k, v in cfg.items()}
    host = lower.get("host") or lower.get("baseurl") or lower.get("base_url")
    if not host:
        return None
    host = host.strip().rstrip("/")
    if not host:
        return None
    if not host.startswith(("http://", "https://")):
        host = "https://" + host
    return host


# --------------------------------------------------------------------------- #
#  HTTP 封装
# --------------------------------------------------------------------------- #
def _request(method, url, headers=None, body=None):
    """
    发起 HTTP 请求，返回 (http_status:int, parsed_json_or_text).
    网络错误时抛出 RuntimeError。
    """
    headers = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url=url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, _try_json(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        return e.code, _try_json(raw)
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络错误: {e.reason}") from e


def _try_json(text):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return {"raw": text}


def _print_json(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _build_url(base_url, path, params=None):
    url = base_url.rstrip("/") + path
    if params:
        # 过滤 None，保留显式空串
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url += "?" + urllib.parse.urlencode(clean, doseq=True)
    return url


# --------------------------------------------------------------------------- #
#  Token 获取
# --------------------------------------------------------------------------- #
def do_login(base_url, app_id, app_secret):
    """调用登录接口，返回 (http_status, 响应 dict)。网络错误时返回 (0, {错误}）。"""
    url = _build_url(base_url, "/iotapi/system/user/app/login")
    try:
        status, resp = _request(
            "POST", url, body={"appId": app_id, "appSecret": app_secret}
        )
    except RuntimeError as e:
        return 0, {"code": 0, "msg": str(e)}
    if status in (401, 403):
        resp.setdefault("_httpStatus", status)
    return status, resp


def resolve_token(args):
    """
    按优先级解析 token。
    返回 (token:str, project_id:int|None)。
    若无法获得 token，打印错误并 sys.exit。
    """
    # 1. 显式 token
    token = args.token or os.environ.get("UZYIOT_TOKEN")
    project_id = getattr(args, "project", None)
    if token:
        return token, project_id

    # 2. app-id / app-secret（命令行或环境变量，最后回退 env.ini）→ 登录
    app_id = args.app_id or os.environ.get("UZYIOT_APP_ID")
    app_secret = args.app_secret or os.environ.get("UZYIOT_APP_SECRET")
    if not (app_id and app_secret):
        ini_id, ini_secret = creds_from_env_ini()
        app_id = app_id or ini_id
        app_secret = app_secret or ini_secret
    if app_id and app_secret:
        status, resp = do_login(args.base_url, app_id, app_secret)
        if status == 200 and resp.get("code") == 200 and resp.get("token"):
            return resp["token"], resp.get("projectId", project_id)
        sys.stderr.write("登录失败，无法获取 token:\n")
        sys.stderr.write(json.dumps(resp, ensure_ascii=False, indent=2) + "\n")
        sys.exit(2 if status in (401, 403) else 1)

    sys.stderr.write(
        "错误：未提供鉴权凭证。请使用 --token，或 --app-id/--app-secret，"
        "或设置环境变量 UZYIOT_TOKEN / UZYIOT_APP_ID+UZYIOT_APP_SECRET，"
        "或在 skill 根目录 env.ini 配置 appId / Secret。\n"
    )
    sys.exit(1)


def call_api(args, method, path, params=None, body=None, need_token=True):
    """通用鉴权请求：解析 token → 发请求 → 打印 → 按 code/http 退出。"""
    headers = {}
    if need_token:
        token, _ = resolve_token(args)
        headers["token"] = token

    url = _build_url(args.base_url, path, params)
    try:
        status, resp = _request(method, url, headers=headers, body=body)
    except RuntimeError as e:
        sys.stderr.write(str(e) + "\n")
        sys.exit(1)

    _print_json(resp)

    if status in (401, 403):
        sys.exit(2)
    code = resp.get("code") if isinstance(resp, dict) else None
    if status == 200 and (code is None or code == 200):
        sys.exit(0)
    sys.exit(1)


def _auth_get(args, path, params=None):
    """
    发起一次鉴权 GET，返回 (http_status, resp_dict)，不退出进程。
    token 解析一次后缓存到 args._token 复用，避免多次登录。
    """
    token = getattr(args, "_token", None)
    if token is None:
        token, _ = resolve_token(args)
        args._token = token
    url = _build_url(args.base_url, path, params)
    return _request("GET", url, headers={"token": token})


def _resolve_device_product(args, addr):
    """
    由设备 addr 找到其所属产品信息，返回 (product_row, device_row)。
    链路：device/list(按 addr 匹配) → 取 product id → product/:id。
    任一步失败返回 (None, None)。
    """
    try:
        project = getattr(args, "project", None)
        # device-list 支持按 addr 过滤，直接精确匹配，避免分页遍历全部设备
        _, dev_resp = _auth_get(
            args,
            "/iotapi/system/device/list",
            {"addr": addr, "pageNum": 1, "pageSize": 20, "project": project},
        )
        device_row = None
        for row in dev_resp.get("rows") or []:
            if str(row.get("addr")) == str(addr):
                device_row = row
                break
        if not device_row or device_row.get("product") is None:
            return None, device_row
        _, prod_resp = _auth_get(
            args, f"/iotapi/system/product/{device_row['product']}"
        )
        return (prod_resp.get("data") or None), device_row
    except (RuntimeError, ValueError, TypeError, KeyError):
        return None, None


def _thing_mapping(product_row):
    """
    从产品信息解析物模型，返回 {属性名(name): {alias/别名(title), unit, access}}。
    product_row 的 thing 字段是 JSON 字符串。
    """
    mapping = {}
    if not product_row:
        return mapping
    thing_raw = product_row.get("thing") or "[]"
    try:
        thing = json.loads(thing_raw) if isinstance(thing_raw, str) else thing_raw
    except (ValueError, TypeError):
        return mapping
    for a in thing or []:
        if isinstance(a, dict) and "name" in a:
            mapping[a["name"]] = {
                "alias": a.get("title", a["name"]),
                "unit": a.get("unit", ""),
                "access": a.get("access", ""),
            }
    return mapping


def _annotate_attrs(data, mapping):
    """
    把一条数据记录的属性与物模型对应起来。
    返回属性列表，每项含 name(属性名)、alias(别名)、value、unit。
    createtime/alarmrule/status 作为元信息单独放到结果里。
    """
    meta_keys = {"createtime", "alarmrule", "status"}
    attrs = []
    meta = {}
    for k, v in data.items():
        if k in meta_keys:
            meta[k] = v
            continue
        info = mapping.get(k)
        attrs.append(
            {
                "name": k,
                "alias": info["alias"] if info else None,
                "value": v,
                "unit": info["unit"] if info else "",
            }
        )
    return attrs, meta


def _run_readable_data(args, path, params, is_history):
    """
    查实时/历史数据并把属性与所属产品物模型对应起来后输出。
    """
    try:
        status, resp = _auth_get(args, path, params)
    except RuntimeError as e:
        sys.stderr.write(str(e) + "\n")
        sys.exit(1)
    if status in (401, 403):
        _print_json(resp)
        sys.exit(2)
    if not (status == 200 and resp.get("code") in (None, 200)):
        _print_json(resp)
        sys.exit(1)

    first_addr = args.addr.split(",")[0].strip()
    product_row, device_row = _resolve_device_product(args, first_addr)
    mapping = _thing_mapping(product_row)

    out = {
        "addr": args.addr,
        "code": resp.get("code", 200),
        "product": None,
    }
    if product_row:
        out["product"] = {
            "id": product_row.get("id"),
            "name": product_row.get("name"),
            "pk": product_row.get("pk"),
            "protocol": product_row.get("protocol"),
        }
    if device_row:
        out["device"] = {
            "name": device_row.get("name"),
            "addr": device_row.get("addr"),
        }

    data = resp.get("data")
    if is_history:
        rows = data if isinstance(data, list) else (resp.get("rows") or [])
        records = []
        for rec in rows:
            if isinstance(rec, dict):
                attrs, meta = _annotate_attrs(rec, mapping)
                records.append({"attrs": attrs, **meta})
        out["records"] = records
        if isinstance(resp.get("total"), int):
            out["total"] = resp["total"]
    else:
        rec = data if isinstance(data, dict) else {}
        attrs, meta = _annotate_attrs(rec, mapping)
        out["attrs"] = attrs
        out.update(meta)

    _print_json(out)
    sys.exit(0)
def cmd_login(args):
    app_id = args.app_id or os.environ.get("UZYIOT_APP_ID")
    app_secret = args.app_secret or os.environ.get("UZYIOT_APP_SECRET")
    if not (app_id and app_secret):
        ini_id, ini_secret = creds_from_env_ini()
        app_id = app_id or ini_id
        app_secret = app_secret or ini_secret
    if not app_id or not app_secret:
        sys.stderr.write(
            "错误：login 需要 --app-id 和 --app-secret（或对应环境变量，"
            "或在 skill 根目录 env.ini 配置 appId / Secret）。\n"
        )
        sys.exit(1)
    status, resp = do_login(args.base_url, app_id, app_secret)
    _print_json(resp)
    if status in (401, 403):
        sys.exit(2)
    sys.exit(0 if status == 200 and resp.get("code") == 200 else 1)


def cmd_product_list(args):
    params = {"pageNum": args.page_num, "pageSize": args.page_size}
    call_api(args, "GET", "/iotapi/system/product/list", params=params)


def cmd_product_detail(args):
    call_api(args, "GET", f"/iotapi/system/product/{args.id}")


def cmd_device_list(args):
    params = {
        "project": args.project,
        "pageNum": args.page_num,
        "pageSize": args.page_size,
    }
    call_api(args, "GET", "/iotapi/system/device/list", params=params)


def cmd_device_detail(args):
    call_api(args, "GET", f"/iotapi/system/device/{args.id}")


def cmd_device_online(args):
    call_api(args, "GET", "/iotapi/system/device/online", params={"addr": args.addr})


def cmd_device_last(args):
    if getattr(args, "readable", False):
        _run_readable_data(
            args,
            "/iotapi/system/device/history/last",
            {"addr": args.addr},
            is_history=False,
        )
        return
    call_api(
        args,
        "GET",
        "/iotapi/system/device/history/last",
        params={"addr": args.addr},
    )


def _history_base_params(args):
    """构造 history/list 的公共查询参数（不含分页），处理 step=0 省略逻辑。"""
    params = {
        "addr": args.addr,
        "createTime[begin]": args.begin,
        "createTime[end]": args.end,
        "orderBy[desc]": args.order_by_desc,
        "step": args.step,
        "type": args.type,
    }
    # step 为聚合粒度（秒）：0=不聚合返回原始数据，>0 按该秒数聚合。
    # 本平台服务端对显式 step=0 会返回 500，而「不传 step」返回的就是原始未聚合数据，
    # 二者结果等价，故 step=0（不聚合）时省略该参数以规避服务端 bug。
    if not args.step:
        params.pop("step", None)
    return params


def _fetch_all_history(args, base_params, page_size, max_records):
    """
    自动翻页拉取 history/list 的全部记录，直到取完 total 或达到 max_records 上限。
    返回 (all_rows:list, total:int|None, truncated:bool)。
    任一页失败即抛 RuntimeError（由调用方处理）。
    """
    all_rows = []
    total = None
    page = 1
    while True:
        params = dict(base_params)
        params["pageNum"] = page
        params["pageSize"] = page_size
        status, resp = _auth_get(args, "/iotapi/system/history/list", params)
        if status in (401, 403):
            raise RuntimeError(f"鉴权失败(HTTP {status})")
        if not (status == 200 and resp.get("code") in (None, 200)):
            raise RuntimeError(
                f"查询失败: {resp.get('msg') if isinstance(resp, dict) else resp}"
            )
        if isinstance(resp.get("total"), int):
            total = resp["total"]
        rows = resp.get("rows") or (
            resp.get("data") if isinstance(resp.get("data"), list) else []
        )
        if not rows:
            break
        all_rows.extend(rows)
        if len(all_rows) >= max_records:
            return all_rows[:max_records], total, True
        if total is not None and len(all_rows) >= total:
            break
        # total 未知时，若本页不足 page_size 说明已到最后一页
        if len(rows) < page_size:
            break
        page += 1
    return all_rows, total, False


def cmd_history_list(args):
    base = _history_base_params(args)

    # --all：自动翻页全量拉取（带 max-records 上限）
    if getattr(args, "all", False):
        page_size = args.page_size if args.page_size else 100
        try:
            rows, total, truncated = _fetch_all_history(
                args, base, page_size, args.max_records
            )
        except RuntimeError as e:
            sys.stderr.write(str(e) + "\n")
            sys.exit(1)

        out = {"addr": args.addr, "code": 200, "total": total, "fetched": len(rows)}
        if truncated:
            out["truncated"] = True
            out["note"] = f"已达 --max-records={args.max_records} 上限，结果被截断"

        if getattr(args, "readable", False):
            product_row, device_row = _resolve_device_product(
                args, args.addr.split(",")[0].strip()
            )
            mapping = _thing_mapping(product_row)
            if product_row:
                out["product"] = {
                    "id": product_row.get("id"),
                    "name": product_row.get("name"),
                    "pk": product_row.get("pk"),
                    "protocol": product_row.get("protocol"),
                }
            if device_row:
                out["device"] = {"name": device_row.get("name"), "addr": device_row.get("addr")}
            records = []
            for rec in rows:
                if isinstance(rec, dict):
                    attrs, meta = _annotate_attrs(rec, mapping)
                    records.append({"attrs": attrs, **meta})
            out["records"] = records
        else:
            out["rows"] = rows
        _print_json(out)
        sys.exit(0)

    # 单页模式（默认，手动分页）
    params = dict(base)
    params["pageNum"] = args.page_num
    params["pageSize"] = args.page_size
    if getattr(args, "readable", False):
        _run_readable_data(
            args, "/iotapi/system/history/list", params, is_history=True
        )
        return
    call_api(args, "GET", "/iotapi/system/history/list", params=params)


def _coerce_control_value(raw, as_hex, value_type):
    """
    将 --value 转换为下发值，复刻前端「命令下发」弹窗逻辑：
      - --hex           ：按 16 进制解析为整数（如 FF00 -> 65280，0000 -> 0）
      - --type int      ：十进制整数
      - --type float    ：浮点数
      - --type string   ：原样作为字符串下发（默认）
    解析失败时打印错误并以退出码 1 结束。
    """
    try:
        if as_hex:
            return int(raw, 16)
        if value_type == "int":
            return int(raw)
        if value_type == "float":
            return float(raw)
    except (ValueError, TypeError):
        kind = "16进制整数" if as_hex else value_type
        sys.stderr.write(f"错误：无法将 --value '{raw}' 解析为 {kind}。\n")
        sys.exit(1)
    return raw


def cmd_device_control(args):
    value = _coerce_control_value(args.value, args.hex, args.type)
    body = {
        "msgType": "control_device",
        "name": args.name,
        "value": value,
    }
    call_api(
        args,
        "POST",
        "/iotapi/system/control/device",
        params={"addr": args.addr},
        body=body,
    )


# --------------------------------------------------------------------------- #
#  参数解析
# --------------------------------------------------------------------------- #
def _add_auth_args(p):
    """为需要鉴权的子命令添加通用凭证参数。"""
    g = p.add_argument_group("鉴权（任选其一）")
    g.add_argument("--token", help="已获取的鉴权 token；缺省读环境变量 UZYIOT_TOKEN")
    g.add_argument("--app-id", help="应用 appId；与 --app-secret 搭配，自动登录换 token")
    g.add_argument("--app-secret", help="应用 appSecret")


def build_parser():
    parser = argparse.ArgumentParser(
        description="有智云物联网平台 开发者接入 REST API CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help=(
            "平台接入地址。优先级：此参数 > 环境变量 UZYIOT_BASE_URL > env.ini 的 host "
            f"> 默认 {DEFAULT_BASE_URL}"
        ),
    )

    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    # login
    p = sub.add_parser("login", help="获取鉴权 Token")
    p.add_argument("--app-id", help="应用 appId；缺省读环境变量 UZYIOT_APP_ID")
    p.add_argument("--app-secret", help="应用 appSecret；缺省读环境变量 UZYIOT_APP_SECRET")
    p.set_defaults(func=cmd_login)

    # product-list
    p = sub.add_parser("product-list", help="查询产品列表")
    p.add_argument("--page-num", type=int, default=1, help="页码，默认 1")
    p.add_argument("--page-size", type=int, default=20, help="每页数量，默认 20")
    _add_auth_args(p)
    p.set_defaults(func=cmd_product_list)

    # product-detail
    p = sub.add_parser("product-detail", help="查询产品详情（按产品 ID）")
    p.add_argument("--id", required=True, help="产品 ID")
    _add_auth_args(p)
    p.set_defaults(func=cmd_product_detail)

    # device-list
    p = sub.add_parser("device-list", help="查询设备列表")
    p.add_argument("--project", help="项目 ID（登录响应中的 projectId）")
    p.add_argument("--page-num", type=int, default=1, help="页码，默认 1")
    p.add_argument("--page-size", type=int, default=20, help="每页数量，默认 20")
    _add_auth_args(p)
    p.set_defaults(func=cmd_device_list)

    # device-detail
    p = sub.add_parser("device-detail", help="查询设备详情（按设备 ID）")
    p.add_argument("--id", required=True, help="设备 ID")
    _add_auth_args(p)
    p.set_defaults(func=cmd_device_detail)

    # device-online
    p = sub.add_parser("device-online", help="批量查询设备在线状态")
    p.add_argument("--addr", required=True, help="设备地址，多个用逗号分隔，如 addr1,addr2")
    _add_auth_args(p)
    p.set_defaults(func=cmd_device_online)

    # device-last
    p = sub.add_parser("device-last", help="查询设备实时数据（最新一条上报）")
    p.add_argument("--addr", required=True, help="设备地址，多个用逗号分隔")
    p.add_argument(
        "--readable",
        action="store_true",
        help="查出设备所属产品物模型，把数据属性与物模型别名(title)/属性名(name)对应起来",
    )
    p.add_argument("--project", help="项目 ID；配合 --readable 加速设备匹配，可选")
    _add_auth_args(p)
    p.set_defaults(func=cmd_device_last)

    # history-list
    p = sub.add_parser("history-list", help="查询设备历史数据")
    p.add_argument("--addr", required=True, help="设备地址")
    p.add_argument("--begin", help="起始时间，格式 'YYYY-MM-DD HH:mm:ss'")
    p.add_argument("--end", help="结束时间，格式 'YYYY-MM-DD HH:mm:ss'")
    p.add_argument("--page-num", type=int, default=1, help="页码，默认 1")
    p.add_argument("--page-size", type=int, default=10, help="每页数量，默认 10")
    p.add_argument("--step", type=int, default=0, help="聚合粒度（秒）：0=不聚合返回原始数据，30=按30秒聚合，依此类推")
    p.add_argument("--type", default="table", choices=["table", "chart"], help="返回格式，默认 table")
    p.add_argument("--order-by-desc", default="createTime", help="降序排序字段，默认 createTime")
    p.add_argument(
        "--all",
        action="store_true",
        help="自动翻页拉取全部记录（忽略 --page-num），带 --max-records 上限保护",
    )
    p.add_argument(
        "--max-records",
        type=int,
        default=10000,
        help="--all 模式下最大拉取条数上限，默认 10000，超过则截断",
    )
    p.add_argument(
        "--readable",
        action="store_true",
        help="查出设备所属产品物模型，把每条历史记录属性与物模型别名(title)/属性名(name)对应起来",
    )
    p.add_argument("--project", help="项目 ID；配合 --readable 加速设备匹配，可选")
    _add_auth_args(p)
    p.set_defaults(func=cmd_history_list)

    # device-control
    p = sub.add_parser("device-control", help="向设备下发控制指令（物模型写）")
    p.add_argument("--addr", required=True, help="设备地址")
    p.add_argument("--name", required=True, help="物模型变量名（可从 product-detail 的 thing 查到）")
    p.add_argument("--value", required=True, help="下发值；配合 --hex / --type 决定解析方式")
    p.add_argument("--hex", action="store_true", help="将 --value 按 16 进制整数解析（如 FF00 -> 65280）")
    p.add_argument(
        "--type",
        default="string",
        choices=["string", "int", "float"],
        help="--value 的类型，默认 string；--hex 时忽略本项",
    )
    _add_auth_args(p)
    p.set_defaults(func=cmd_device_control)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    # 解析 base_url 优先级：--base-url > UZYIOT_BASE_URL > env.ini host > 默认
    if not args.base_url:
        args.base_url = (
            os.environ.get("UZYIOT_BASE_URL")
            or host_from_env_ini()
            or DEFAULT_BASE_URL
        )
    args.func(args)


if __name__ == "__main__":
    main()
