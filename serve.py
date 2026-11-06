#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local Dream Studio — 静态服务 + 受控模式反向代理

为什么需要它：
  受控模式的两个端口（8808 控制口 / 8081 生成口）是裸 HTTP 服务，不带 CORS 头。
  浏览器若从 http://localhost:8777 直接 fetch 到 http://192.168.x.x:8808，
  会被同源策略拦截；若页面本身跑在 HTTPS 上，还会被混合内容策略拦。
  本脚本把页面与接口放到同一个源下，顺便原样透传 SSE 流。

用法：
  python serve.py                       # 默认 127.0.0.1:8777，浏览器打开该地址
  python serve.py --host 192.168.1.100  # 预置手机地址（页面里仍可改）
  python serve.py --port 9000

代理路径约定：
  /p/8808/<path>  ->  http://<X-LD-Host>:8808/<path>
  /p/8081/<path>  ->  http://<X-LD-Host>:8081/<path>
  X-LD-Host 请求头缺省时使用 --host 指定的地址。
"""

import argparse
import http.server
import os
import socket
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_HOST = ""

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}

# 逐跳头，不应转发
HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
    "x-ld-host",
}

# 关键：urllib 默认会读取 http_proxy / HTTP_PROXY / all_proxy 环境变量，
# 把发往局域网设备的请求塞进本机代理，导致连不上或收到代理伪造的 502。
# 转发目标永远是局域网裸设备，因此显式禁用所有代理。
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "LDStudio/1.0"

    # ── 日志 ──
    def log_message(self, fmt, *args):
        msg = fmt % args
        if "/p/" in msg:
            sys.stderr.write("  \033[36mproxy\033[0m %s\n" % msg)
        elif " 200 " in msg or " 304 " in msg:
            return
        else:
            sys.stderr.write("  \033[33m%s\033[0m\n" % msg)

    # ── CORS 预检 ──
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept, X-LD-Host")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept, X-LD-Host")

    # ── 路由 ──
    def do_GET(self):
        if self.path.startswith("/p/"):
            self.handle_proxy("GET")
        elif self.path.startswith("/api/diag"):
            self.handle_diag()
        elif self.path == "/api/ping":
            self.send_json({"ok": True, "default_host": DEFAULT_HOST})
        else:
            self.serve_static()

    # ── 诊断：分别探测控制口与生成口 ──
    def handle_diag(self):
        import json
        import urllib.parse as up

        q = up.parse_qs(up.urlparse(self.path).query)
        host = (q.get("host", [""])[0] or self.headers.get("X-LD-Host") or DEFAULT_HOST or "").strip()
        host = host.replace("http://", "").replace("https://", "").rstrip("/").split(":")[0]
        if not host:
            self.send_json({"error": {"message": "未指定 host"}})
            return

        def tcp(port):
            try:
                s = socket.create_connection((host, port), timeout=2.0)
                s.close()
                return True
            except OSError:
                return False

        ctl_up = tcp(8808)
        gen_up = tcp(8081)
        info = None
        if ctl_up:
            try:
                with OPENER.open("http://%s:8808/info" % host, timeout=3) as r:
                    info = json.loads(r.read().decode("utf-8", "replace"))
            except Exception:
                info = None

        if not ctl_up:
            hint = "控制口 8808 不可达：确认受控模式已开启、手机与电脑同一网段、App 未被系统回收。"
        elif not gen_up:
            hint = "控制口正常，但生成口 8081 未监听。这是正常状态 —— 受控模式只在选定模型后才启动 native 后端，回到 App 或在本页选一个模型即可。"
        else:
            hint = "两个端口都就绪。"

        self.send_json({
            "host": host,
            "ctl": {"port": 8808, "tcp": ctl_up, "info": info},
            "gen": {"port": 8081, "tcp": gen_up},
            "hint": hint,
        })

    def do_POST(self):
        if self.path.startswith("/p/"):
            self.handle_proxy("POST")
        else:
            self.send_error(404, "Not Found")

    # ── 静态文件 ──
    def serve_static(self):
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if path in ("/", ""):
            path = "/index.html"
        # 防目录穿越
        rel = os.path.normpath(path.lstrip("/")).replace("\\", "/")
        if rel.startswith("..") or os.path.isabs(rel):
            self.send_error(403, "Forbidden")
            return
        full = os.path.join(ROOT, rel)
        if not os.path.isfile(full):
            self.send_error(404, "Not Found: %s" % rel)
            return
        ext = os.path.splitext(full)[1].lower()
        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_json(self, obj):
        import json
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    # ── 代理 ──
    def handle_proxy(self, method):
        # /p/<port>/<rest>
        parts = self.path.split("/", 3)
        if len(parts) < 3 or not parts[2].isdigit():
            self.send_error(400, "Bad proxy path, expect /p/<port>/<path>")
            return
        port = parts[2]
        rest = parts[3] if len(parts) > 3 else ""
        target_host = (self.headers.get("X-LD-Host") or DEFAULT_HOST or "").strip()
        if target_host:
            target_host = target_host.replace("http://", "").replace("https://", "").rstrip("/")

        if not target_host:
            self.send_json({
                "error": {"type": "request_error",
                          "message": "未指定目标地址。请在页面「设置 → 手机地址」填写局域网 IP，"
                                     "或用 serve.py --host <IP> 启动。"}
            })
            return

        url = "http://%s:%s/%s" % (target_host, port, rest)

        # 读请求体
        body = None
        length = self.headers.get("Content-Length")
        if length:
            try:
                body = self.rfile.read(int(length))
            except (ValueError, OSError):
                body = b""

        fwd = {}
        for k, v in self.headers.items():
            if k.lower() not in HOP:
                fwd[k] = v
        if "Accept" not in fwd and port == "8081":
            fwd["Accept"] = "text/event-stream"

        req = urllib.request.Request(url, data=body, headers=fwd, method=method)

        try:
            resp = OPENER.open(req, timeout=600)
        except urllib.error.HTTPError as e:
            resp = e
        except urllib.error.URLError as e:
            self.send_json({
                "error": {"type": "request_error",
                          "message": "无法连接 %s:%s —— %s" % (target_host, port, e.reason)}
            })
            return
        except socket.timeout:
            self.send_json({"error": {"type": "request_error", "message": "连接超时"}})
            return

        ctype = resp.headers.get("Content-Type", "application/json")
        is_sse = "text/event-stream" in ctype.lower()

        self.send_response(getattr(resp, "status", 200) or 200)
        self.send_header("Content-Type", ctype)
        self._cors()
        self.send_header("Cache-Control", "no-cache")

        if is_sse:
            # SSE：逐块透传，用 chunked 编码保持长连接
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            try:
                while True:
                    chunk = resp.read1(8192) if hasattr(resp, "read1") else resp.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(b"%X\r\n" % len(chunk) + chunk + b"\r\n")
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                try:
                    resp.close()
                except Exception:
                    pass
            return

        # 普通响应：整块读回
        try:
            data = resp.read()
        except Exception as e:
            self.send_json({"error": {"type": "request_error", "message": str(e)}})
            return
        finally:
            try:
                resp.close()
            except Exception:
                pass

        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass


class ThreadedServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    global DEFAULT_HOST
    ap = argparse.ArgumentParser(description="Local Dream Studio 本地服务")
    ap.add_argument("--host", default="", help="预置手机局域网 IP，例如 192.168.1.100")
    ap.add_argument("--port", type=int, default=8777, help="本服务监听端口，默认 8777")
    ap.add_argument("--bind", default="127.0.0.1", help="本服务绑定地址，默认 127.0.0.1；用 0.0.0.0 可让手机自己开页面")
    args = ap.parse_args()

    DEFAULT_HOST = args.host.strip()

    srv = ThreadedServer((args.bind, args.port), Handler)
    url = "http://127.0.0.1:%d/" % args.port
    print("")
    print("  \033[1mLocal Dream Studio\033[0m")
    print("  服务地址  %s" % url)
    print("  目标设备  %s" % (DEFAULT_HOST or "(未预置，页面设置里填写)"))
    print("  控制口    8808   生成口  8081")
    print("")
    print("  提示：先在手机 App 里  ⋮ → 设备互联 → 受控模式 → 进入受控模式")
    print("        Ctrl+C 停止")
    print("")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止\n")
        srv.shutdown()


if __name__ == "__main__":
    main()
