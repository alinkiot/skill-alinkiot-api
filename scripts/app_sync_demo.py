#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app_sync_demo.py — 应用数据同步演示脚本（仅依赖 Python 标准库）

演示「应用数据同步机制」，两种模式，每一步都打印日志：

  active   主动同步：登录后按项目 ID 立即同步所有设备、产品、场景，同步完成后退出
  passive  被动同步：登录后连接 MQTT 并订阅 app/in/{projectId}/{appId}；收到平台的同步消息
           （在平台「应用接入」页面手动触发）就打印，并和主动模式一样执行同步，同步前后向
           p/in 回报 doing / succ（失败 fail）；断线自动重连；
           默认 --interval 30 即「定时 + 事件」（每 30 秒循环同步）；--interval 0 为纯事件驱动：
           连接后不主动同步，只在收到平台事件时同步。
           「定时 + 事件」：连接订阅后先同步一次并启动定时器，到期自动同步；
           收到同步事件时取消定时器，同步完成后再重启定时器

同步顺序（与「应用数据同步机制」一致）：
  syncBaseData     先拉设备（分页）→ 再按设备的产品（去重）同步产品 → 同步场景及场景设备
  syncDeviceStatus 用 device-online 批量刷新本地设备的在线状态

用法：
  python3 scripts/app_sync_demo.py active
  python3 scripts/app_sync_demo.py passive

凭证与平台地址的来源与 uzyiot_api.py 一致：命令行 > 环境变量 > skill 根目录 env.ini。
"""

import argparse
import json
import os
import random
import socket
import ssl
import struct
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uzyiot_api as api  # noqa: E402  复用登录与 HTTP 封装

PAGE_SIZE = 100
BATCH = 50  # 批量接口每次最多传的 ID / addr 个数


def log(msg=""):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------- #
#  REST 客户端（自动登录 / 401 重登）
# --------------------------------------------------------------------------- #
class Platform:
    def __init__(self, base_url, app_id, app_secret):
        self.base_url = base_url
        self.app_id = app_id
        self.app_secret = app_secret
        self.token = None
        self.project_id = None

    def login(self):
        status, resp = api.do_login(self.base_url, self.app_id, self.app_secret)
        if status != 200 or resp.get("code") != 200 or not resp.get("token"):
            raise RuntimeError(f"登录失败: {json.dumps(resp, ensure_ascii=False)}")
        self.token = resp["token"]
        self.project_id = resp.get("projectId")
        log(f"登录成功 projectId={self.project_id} expire={resp.get('expire')}s")
        return resp

    def get(self, path, params=None):
        """GET；token 失效时重新登录并重试一次。"""
        for attempt in (1, 2):
            url = api._build_url(self.base_url, path, params)
            status, resp = api._request("GET", url, headers={"token": self.token})
            if status in (401, 403) and attempt == 1:
                log(f"HTTP {status}，token 失效，重新登录")
                self.login()
                continue
            if status != 200 or (isinstance(resp, dict) and resp.get("code") not in (None, 200)):
                raise RuntimeError(f"GET {path} 失败: HTTP {status} {resp}")
            return resp

    def list_all(self, label, path, params, unit="条"):
        """分页拉取 rows，逐页打印日志，直到取完 total。"""
        first = self.get(path, dict(params, pageNum=1, pageSize=PAGE_SIZE))
        total = first.get("total", len(first.get("rows") or []))
        pages = max(1, -(-total // PAGE_SIZE)) if total else 0
        log(f"  {label}: 查询到 {total} {unit}，每页 {PAGE_SIZE}，共 {pages} 页")
        rows = list(first.get("rows") or [])
        if pages:
            log(f"  {label}: 同步第 1/{pages} 页，本页 {len(rows)} {unit}，累计 {len(rows)}/{total}")
        for page in range(2, pages + 1):
            part = self.get(path, dict(params, pageNum=page, pageSize=PAGE_SIZE)).get("rows") or []
            rows.extend(part)
            log(f"  {label}: 同步第 {page}/{pages} 页，本页 {len(part)} {unit}，累计 {len(rows)}/{total}")
            if not part:
                break
        log(f"  {label}: 分页同步完成，共取得 {len(rows)} {unit}")
        return rows


def chunks(items, n):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def as_list(data):
    """单个 ID 返回对象、多个 ID 返回数组，统一成列表。"""
    if data is None:
        return []
    return data if isinstance(data, list) else [data]


# --------------------------------------------------------------------------- #
#  本地库（内存模拟）与比对
# --------------------------------------------------------------------------- #
class LocalStore:
    def __init__(self):
        self.devices = {}        # 设备 id -> 设备
        self.products = {}       # 产品 id -> 产品
        self.scenes = {}         # 场景 id -> 场景
        self.scene_devices = {}  # 场景 id -> [设备 id]
        self.online = {}         # 设备 addr -> 0/1

    @staticmethod
    def diff(old, new):
        added = [k for k in new if k not in old]
        removed = [k for k in old if k not in new]
        changed = [k for k in new if k in old and new[k] != old[k]]
        return added, removed, changed

    def apply(self, label, attr, new_map, name_of):
        old_map = getattr(self, attr)
        added, removed, changed = self.diff(old_map, new_map)
        setattr(self, attr, new_map)
        log(f"  {label}: 共 {len(new_map)}  新增 {len(added)}  更新 {len(changed)}  "
            f"平台已不存在(本地应标记删除) {len(removed)}")
        for k in added[:3]:
            log(f"    + {name_of(new_map[k])}")
        for k in removed[:3]:
            log(f"    - {name_of(old_map[k])}")


# --------------------------------------------------------------------------- #
#  同步逻辑
# --------------------------------------------------------------------------- #
def sync_base_data(pf, store):
    project = pf.project_id
    log(f"【1/3】开始同步设备（项目 {project}）")
    devices = pf.list_all("设备", "/iotapi/system/device/list", {"project": project})
    store.apply("设备", "devices", {d["id"]: d for d in devices},
                lambda d: f"{d.get('name')} (addr={d.get('addr')}, product={d.get('product')})")
    log(f"【1/3】设备同步完成：共 {len(devices)} 台")

    product_ids = sorted({d["product"] for d in devices if d.get("product") is not None})
    batches = list(chunks(product_ids, BATCH))
    log(f"【2/3】开始同步产品：设备用到 {len(product_ids)} 个产品（已去重）{product_ids}，"
        f"分 {len(batches)} 批，每批最多 {BATCH} 个")
    products = []
    for n, part in enumerate(batches, 1):
        resp = pf.get("/iotapi/system/product/" + ",".join(str(i) for i in part))
        got = as_list(resp.get("data"))
        products.extend(got)
        log(f"  产品: 同步第 {n}/{len(batches)} 批 {part}，取得 {len(got)} 个，累计 {len(products)}/{len(product_ids)}")
    store.apply("产品", "products", {p["id"]: p for p in products},
                lambda p: f"{p.get('name')} (id={p.get('id')}, protocol={p.get('protocol')})")
    log(f"【2/3】产品同步完成：共 {len(products)} 个")

    log(f"【3/3】开始同步场景（项目 {project}）")
    scenes = pf.list_all("场景", "/iotapi/system/scene/list", {"project": project}, unit="个")
    store.apply("场景", "scenes", {s["id"]: s for s in scenes},
                lambda s: f"{s.get('title')} (id={s.get('id')}, viewType={s.get('viewType')})")
    relations = {}
    for n, sc in enumerate(scenes, 1):
        log(f"  开始同步第 {n}/{len(scenes)} 个场景「{sc.get('title')}」(id={sc['id']}) 的设备")
        rows = pf.list_all(f"场景{sc['id']}设备", "/iotapi/system/scene_device/list", {"scene": sc["id"]})
        relations[sc["id"]] = sorted(r["device"] for r in rows)
        log(f"  场景「{sc.get('title')}」绑定设备 {len(relations[sc['id']])} 台: {relations[sc['id']]}")
    store.scene_devices = relations
    log(f"【3/3】场景同步完成：共 {len(scenes)} 个")


def sync_device_status(pf, store):
    if not store.devices:
        log("本地没有设备，先执行一次基础数据同步")
        sync_base_data(pf, store)
    addrs = sorted({d["addr"] for d in store.devices.values() if d.get("addr")})
    log(f"① 批量查询在线状态 device-online：{len(addrs)} 台")
    online = {}
    for part in chunks(addrs, BATCH):
        resp = pf.get("/iotapi/system/device/online", {"addr": ",".join(part)})
        for item in as_list(resp.get("data")):
            online[item["addr"]] = item.get("online", 0)
    changed = {a: v for a, v in online.items() if store.online.get(a) != v}
    store.online = online  # 以平台返回结果覆盖本地在线状态
    on = sum(1 for v in online.values() if v == 1)
    log(f"② 覆盖本地在线状态：在线 {on}  离线 {len(online) - on}  状态有变化 {len(changed)}")
    for a, v in list(changed.items())[:5]:
        log(f"    {a}: {'在线' if v == 1 else '离线'}")


def handle_event(event, pf, store, report):
    handlers = {"syncBaseData": sync_base_data, "syncDeviceStatus": sync_device_status}
    fn = handlers.get(event)
    if not fn:
        log(f"忽略未知同步事件: {event}")
        return
    log(f"━━ 开始处理同步事件 {event} ━━")
    report("doing")
    try:
        fn(pf, store)
    except Exception as e:  # noqa: BLE001  演示脚本：任何失败都回报 fail
        log(f"同步失败: {e}")
        report("fail")
        return
    report("succ")
    log(f"━━ 同步完成 {event} ━━")


class SyncTimer:
    """定时同步计时器（单线程轮询式）：due 为下次触发的时间戳，None 表示已取消。"""

    def __init__(self, interval):
        self.interval = interval
        self.due = None

    def start(self):
        self.due = time.time() + self.interval
        log(f"  [定时器] 已启动，{self.interval} 秒后定时同步")

    def cancel(self):
        if self.due is not None:
            self.due = None
            log("  [定时器] 已取消")


# --------------------------------------------------------------------------- #
#  极简 MQTT 3.1.1 客户端（QoS 0，标准库实现）
# --------------------------------------------------------------------------- #
def _enc_len(n):
    out = bytearray()
    while True:
        b, n = n % 128, n // 128
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _enc_str(s):
    b = s.encode("utf-8")
    return struct.pack("!H", len(b)) + b


class Mqtt:
    def __init__(self, host, port, use_tls, client_id, username, password, keepalive=60):
        self.host, self.port, self.use_tls = host, port, use_tls
        self.client_id, self.username, self.password = client_id, username, password
        self.keepalive = keepalive
        self.sock = None
        self.pid = 0

    def _send(self, data):
        self.sock.sendall(data)

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("连接被关闭")
            buf += chunk
        return buf

    def _read_packet(self):
        """读一个完整报文，返回 (type, flags, body)；首字节读取超时抛 socket.timeout。"""
        first = self.sock.recv(1)
        if not first:
            raise ConnectionError("连接被关闭")
        self.sock.settimeout(15)
        mult, length = 1, 0
        while True:
            b = self._recv_exact(1)[0]
            length += (b & 0x7F) * mult
            if not b & 0x80:
                break
            mult *= 128
        body = self._recv_exact(length) if length else b""
        return first[0] >> 4, first[0] & 0x0F, body

    def connect(self):
        raw = socket.create_connection((self.host, self.port), timeout=15)
        if self.use_tls:
            ctx = api.SSL_CONTEXT or ssl.create_default_context()
            self.sock = ctx.wrap_socket(raw, server_hostname=self.host)
        else:
            self.sock = raw
        payload = (_enc_str("MQTT") + b"\x04" + bytes([0xC2]) + struct.pack("!H", self.keepalive)
                   + _enc_str(self.client_id) + _enc_str(self.username) + _enc_str(self.password))
        self._send(b"\x10" + _enc_len(len(payload)) + payload)
        ptype, _, body = self._read_packet()
        if ptype != 2 or len(body) < 2 or body[1] != 0:
            raise ConnectionError(f"MQTT 连接被拒绝: type={ptype} body={body!r}"
                                  "（认证失败时请检查 appId 与 token 是否匹配、token 是否过期）")

    def subscribe(self, topic):
        self.pid += 1
        payload = struct.pack("!H", self.pid) + _enc_str(topic) + b"\x00"
        self._send(b"\x82" + _enc_len(len(payload)) + payload)
        ptype, _, body = self._read_packet()
        if ptype != 9 or body[-1] == 0x80:
            raise ConnectionError(f"订阅失败: type={ptype} body={body!r}")

    def publish(self, topic, payload):
        data = _enc_str(topic) + payload
        self._send(b"\x30" + _enc_len(len(data)) + data)

    def ping(self):
        self._send(b"\xc0\x00")

    def loop(self, on_message, timer=None, on_timer=None):
        """阻塞收消息；空闲时按 keepalive 发送心跳。
        timer.due 到期时调用 on_timer（定时同步）；on_message / on_timer 里可取消、重启 timer。
        连接断开抛异常。"""
        while True:
            if timer is not None and timer.due is not None and time.time() >= timer.due:
                timer.due = None  # 触发即取消；on_timer 同步完成后自行重启
                on_timer()
            timeout = self.keepalive / 2
            if timer is not None and timer.due is not None:
                timeout = max(1.0, min(timeout, timer.due - time.time()))
            self.sock.settimeout(timeout)
            try:
                ptype, flags, body = self._read_packet()
            except socket.timeout:
                self.ping()
                continue
            if ptype == 3:  # PUBLISH
                tlen = struct.unpack("!H", body[:2])[0]
                topic = body[2:2 + tlen].decode("utf-8")
                off = 2 + tlen + (2 if (flags >> 1) & 3 else 0)
                on_message(topic, body[off:])

    def close(self):
        try:
            self._send(b"\xe0\x00")
            self.sock.close()
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- #
#  主流程
# --------------------------------------------------------------------------- #
def resolve_args():
    ap = argparse.ArgumentParser(description="应用数据同步演示：active 主动同步 / passive 被动同步")
    ap.add_argument("mode", choices=["active", "passive"],
                    help="active=登录后立即同步所有数据；passive=订阅 MQTT 等平台触发同步")
    ap.add_argument("--base-url", help="平台 API 地址；缺省读 UZYIOT_BASE_URL / env.ini host / 默认地址")
    ap.add_argument("--app-id")
    ap.add_argument("--app-secret")
    ap.add_argument("--mqtt-host", help="（passive）MQTT 主机；缺省与 API 主机一致")
    ap.add_argument("--mqtt-port", type=int, help="（passive）MQTT 端口；缺省 1883（--tls 时 8883）")
    ap.add_argument("--tls", action="store_true", help="（passive）MQTT 使用 TLS")
    ap.add_argument("--page-size", type=int, default=PAGE_SIZE, help="分页大小，默认 100")
    ap.add_argument("--interval", type=int, default=30, metavar="秒",
                    help="（passive）开启「定时 + 事件」模式：连接后先同步一次，之后每隔多少秒定时同步；收到同步事件时取消定时器、同步完成后重启。默认 30；0=纯事件驱动；最小 5")
    ap.add_argument("--insecure", action="store_true",
                    help="不校验 HTTPS / TLS 证书（仅限证书过期等临时排查，不安全，默认关闭）")
    args = ap.parse_args()
    if args.interval and args.interval < 5:
        sys.exit("错误：--interval 最小为 5 秒（0 表示关闭定时同步）。")
    if args.insecure:
        api.enable_insecure()

    args.base_url = (args.base_url or os.environ.get("UZYIOT_BASE_URL")
                     or api.host_from_env_ini() or api.DEFAULT_BASE_URL)
    ini_id, ini_secret = api.creds_from_env_ini()
    args.app_id = args.app_id or os.environ.get("UZYIOT_APP_ID") or ini_id
    args.app_secret = args.app_secret or os.environ.get("UZYIOT_APP_SECRET") or ini_secret
    if not (args.app_id and args.app_secret):
        sys.exit("错误：缺少 appId / appSecret（命令行、环境变量或 env.ini）。")
    return args


def run_active(pf, store):
    log("【主动同步】登录成功，按项目 ID 开始同步所有设备、产品、场景")
    start = time.time()
    sync_base_data(pf, store)
    log(f"【主动同步】全部完成，耗时 {time.time() - start:.1f}s："
        f"设备 {len(store.devices)}、产品 {len(store.products)}、场景 {len(store.scenes)}")


def run_passive(args, pf, store):
    host = args.mqtt_host or urllib.parse.urlparse(args.base_url).hostname
    port = args.mqtt_port or (8883 if args.tls else 1883)
    backoff = 2
    while True:
        topic = f"app/in/{pf.project_id}/{pf.app_id}"
        client_id = f"app_{pf.app_id}_{random.randint(0, 0xFFFFFF):06x}"
        mqtt = Mqtt(host, port, args.tls, client_id, pf.app_id, pf.token)
        try:
            log(f"连接 MQTT {host}:{port} clientId={client_id}")
            mqtt.connect()
            mqtt.subscribe(topic)
            log(f"已订阅 {topic}，等待平台触发同步（在平台「应用接入」页面手动触发；Ctrl+C 退出）")
            backoff = 2

            def report(status):
                mqtt.publish("p/in", json.dumps(
                    {"msgType": "sync", "data": {"status": status}}).encode("utf-8"))
                log(f"  [回报状态] p/in ← {{\"msgType\":\"sync\",\"data\":{{\"status\":\"{status}\"}}}}")

            timer = SyncTimer(args.interval) if args.interval else None

            def on_message(t, payload):
                text = payload.decode("utf-8", errors="replace")
                log(f"收到平台消息 topic={t} payload={text}")
                try:
                    msg = json.loads(text)
                except ValueError:
                    return
                if msg.get("msgType") != "sync":
                    return
                event = (msg.get("data") or {}).get("event")
                if timer:
                    timer.cancel()  # 收到同步事件：取消定时器，同步完成后再重启
                handle_event(event, pf, store, report)
                if timer:
                    timer.start()
                log("继续等待平台触发同步……")

            def on_timer():
                log(f"定时器到期（每 {args.interval} 秒），开始定时同步")
                handle_event("syncBaseData", pf, store, report)
                timer.start()

            if timer:
                log(f"【定时 + 事件模式】--interval={args.interval}：连接建立后先同步一次，之后每 "
                    f"{args.interval} 秒定时同步；收到同步事件时取消定时器、同步完成后重启")
                handle_event("syncBaseData", pf, store, report)
                timer.start()
            else:
                log("【纯事件驱动模式】--interval 0：只在收到平台同步事件时才同步")
            mqtt.loop(on_message, timer, on_timer)
        except KeyboardInterrupt:
            mqtt.close()
            log("已退出")
            return
        except (ConnectionError, OSError, socket.timeout) as e:
            log(f"MQTT 连接中断: {e}；{backoff}s 后重连")
            mqtt.close()
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            try:
                pf.login()  # 重连前重新登录，避免 token 过期导致认证失败
            except RuntimeError as le:
                log(str(le))


def main():
    global PAGE_SIZE
    args = resolve_args()
    PAGE_SIZE = args.page_size
    pf = Platform(args.base_url, args.app_id, args.app_secret)
    store = LocalStore()

    log(f"平台地址 {args.base_url}，模式 {args.mode}")
    pf.login()
    if args.mode == "active":
        run_active(pf, store)
    else:
        run_passive(args, pf, store)


if __name__ == "__main__":
    main()
