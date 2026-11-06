# Local Dream Studio

面向手机端 **Local Dream「受控模式」** 的可视化交互式生图前端。

单文件 HTML，零构建、零依赖；配一个 Python 同源代理解决浏览器跨域问题。

```
localdream-studio/
├── index.html   # 全部界面与逻辑（原生 JS，无框架、无 CDN）
├── serve.py     # 静态服务 + 8808/8081 反向代理（含 SSE 透传）
└── README.md
```

---

## 一、先决条件：打开受控模式

受控模式的服务在 `AndroidManifest.xml` 里是 `exported="false"`，**没有任何外部方式可以唤起**，必须手动点：

> Local Dream → 模型列表右上角 **⋮** → **设备互联** → 受控模式区块 → **「进入受控模式」**

打开后暴露两个端口：

| 端口 | 性质 | 本前端用到的端点 |
|---|---|---|
| `8808` | 控制口（JSON API） | `GET /info`、`GET /models`、`GET /status`、`POST /select` |
| `8081` | 生成口（native 后端） | `POST /generate`（SSE）、`POST /tokenize` |

自检（在电脑上执行，把 IP 换成手机局域网地址）：

```bash
curl -s --max-time 6 http://192.168.1.100:8808/info
# {"app":"localdream","protocol":1,"version":"...","device":"..."}
```

没有响应就是受控模式没开、或被系统回收了 —— 回 App 里重新点一次，**重试不会让它自己起来**。

---

## 二、启动

```bash
cd localdream-studio
python serve.py --host 192.168.1.100    # 换成你手机的局域网 IP
```

浏览器打开 **http://127.0.0.1:8777/** 即可。页面会自动从服务端读到地址并连接，不用手填。

手机 IP 可以在页面「设置 → 手机地址」里随时改，改完立刻生效，无需重启。

### 为什么必须经过 serve.py

受控模式的两个端口是裸 HTTP 服务，**不带任何 CORS 响应头**。如果页面直接 `fetch` 到另一个源：

- 页面在 `http://localhost` → 被同源策略拦（预检 `OPTIONS` 无人应答）；
- 页面在 `https://` → 直接被混合内容策略拦死。

`serve.py` 把页面与接口放在同一个源下（`/p/8808/*`、`/p/8081/*`），并原样逐块转发 SSE 流，这两个问题都不存在。

「直连手机」模式（`http://<ip>:8808`）只适合调试 —— 除非你在浏览器侧关掉了 Web 安全策略，否则它一定失败。

---

## 二·五、连不上时怎么查

### 排查顺序（照这个走，别猜）

```bash
# 1. 设备在不在
ping 192.168.0.50

# 2. 控制口通不通（这条最关键）
curl -sS --noproxy '*' http://192.168.0.50:8808/info
# {"app":"localdream","protocol":1,"version":"3.0.0-alpha.7","device":"AAK-AN00"}

# 3. 生成口通不通
curl -sS --noproxy '*' -m 5 http://192.168.0.50:8081/health
```

页面上的「测试连接」调的是 `serve.py` 的 `/api/diag`，会分别报告两个端口的 TCP 可达性并给出结论，等价于上面第 2、3 步。

### 三个真实踩过的坑

**坑一：`http_proxy` 环境变量劫持。**

如果本机设了 `http_proxy` / `HTTPS_PROXY` / `all_proxy`，Python 的 `urllib` 会**默认**把所有请求塞进代理。表现是：

- 打开发往 `192.168.0.50:8081` 的请求，收到的却是一个 `502 Bad Gateway`，错误文本是中文 Windows 报错 `os error 10061` —— 这是**本机代理**伪装出来的响应，不是设备返回的；
- 更糟的是它会把一个「端口没开」误报成「HTTP 502」，把排查带偏。

`serve.py` 已经用 `ProxyHandler({})` 显式禁用代理，转发永远直连局域网设备。自己写脚本排障时记得加 `curl --noproxy '*'`。

**坑二：8081 只在选定模型后才监听。**

这是设计如此，不是故障。`/status` 报 `{"state":"idle","serving_model_id":null}` 时，8081 就是关着的。选一个模型后 native 后端才会拉起。

**坑三：`state` 已经 `running`，8081 还有短暂空窗。**

实测存在：`/status` 返回 `running` 的瞬间 TCP 连接仍会被拒（`WinError 10061`），几百毫秒后才真正可用。前端已处理——选完模型会主动探活到能响应为止，生成时遇到网络错误还会等待重试一次。

---

## 二·六、没有设备时

设置里切到 **演示模式**：模型列表、扩散过程、进度、耗时全部由浏览器本地合成，用于预览界面与交互流程，不会发出任何请求。

---

## 三、接口依据

所有端点、字段、取值范围都来自下列来源，没有猜测。

| 界面功能 | 实现 | 文档出处 |
|---|---|---|
| 连接探测、设备信息（版本/设备名/protocol） | `GET :8808/info` | `ld-api` README；`src/device.ts` 的 `Info`；dsh-localdream 自检示例 |
| 模型列表、NPU/CPU 标签、分辨率集合、每模型默认参数 | `GET :8808/models` → `{use_img2img, models[], upscalers[]}`，`Module` 含 `run_on_cpu / is_sdxl / is_anima / dit_kind / is_custom / generation_size / defaults{steps,cfg,scheduler} / resolutions` | `ld-api` `src/device.ts` 的 `Module`、`Models` |
| 点模型卡片 → 载入并等待就绪 | `POST :8808/select {model_id,width,height}` → `{ok}`，再轮询 `/status` 至 `state==='running'` | `ld-api` `src/device.ts`；状态机 `idle/starting/running/error` 见 Local Dream 技术解析 |
| 后端状态灯、当前挂载模型与尺寸 | `GET :8808/status` → `{serving_model_id,state,message,width,height}` | 同上 |
| 提示词 / 反向提示词 / 步数 / CFG / 采样器 / 种子 / 尺寸 | `POST :8081/generate` JSON body | 官方 *HTTP API 参考* 请求字段表；`ld-api` README 完整参数表 |
| 采样器下拉 9 项 | `dpm` / `dpm_karras` / `dpm_sde` / `dpm_sde_karras` / `euler_a` / `euler_a_karras` / `euler` / `euler_karras` / `lcm`，未知值回退 `dpm`，`lcm` 不支持 Karras 后缀 | 官方 *HTTP API 参考*「scheduler 取值列表」 |
| SDXL 宽高比芯片 | 仅当 `is_sdxl` 时发 `aspect_ratio`（`"1:1"`…），长边 1024、短边**向上取整到 8 的倍数** | 官方参考「SDXL — NPU 模式」；dsh-localdream 明确指出 `width/height` 对 SDXL 无效 |
| 随机种子 / 锁定 / 固种重跑 | `seed` 省略=随机；传 `-1` 会变成固定种子 `4294967295`，所以留空时**不发送该字段** | `ld-api` README 及 v0.1.1 提交说明 |
| 扩散过程实时预览 | `show_diffusion_process:true` + `show_diffusion_stride:N`，逐帧解 `progress` 事件的 `image` | 官方参考「流式响应」；`ld-api` README「扩散过程预览」 |
| 进度条、步数、剩余时间 | `progress` → `{step,total_steps,image?,format?}`；首步耗时用于校正 ETA | `ld-api` `src/generation.ts` 的 `ProgressEvent` |
| 结果图、seed 回填、耗时统计、下载 PNG | `complete` → `{image,seed,width,height,channels:3,format,generation_time_ms,first_step_time_ms}` | 官方参考 `complete` 事件；`ld-api` `CompleteEvent` |
| 取消生成 | 对 `fetch` 挂 `AbortController`，中断 SSE 流 | `ld-api` README「取消生成」 |
| token 计数（77 上限，超限标红） | `POST /tokenize {prompt}` → `{count,max_length,overflow_offset}` | 官方参考 `POST /tokenize`；`ld-api` `TokenizeResult` |
| 图生图 | 传 `image` = base64 编码的 **PNG/JPG 字节**（不是裸 RGB），并附 `denoise_strength` | 官方参考 `image` / `denoise_strength` 字段 |
| 局部重绘 | 同时传 `image` + `mask`（base64 PNG） | 官方参考 `mask` 字段 |
| 错误提示（400 非流式 / 流内 error） | 两条路径都处理：`Content-Type` 不是 `text/event-stream` 时按 JSON 错误体解析；否则监听 `error` 事件 | `ld-api` `generateImage` 的错误分支实现 |
| OpenCL 开关（仅 CPU 模型显示） | `use_opencl`，NPU 下该字段被接受但不起作用 | 官方参考「SD1.5 — CPU / NPU 模式」 |

**来源清单**

1. Local Dream 官方指南 · *HTTP API 参考* — <https://ld-guide.chino.icu/zh/features/http-api>
2. `@kongxiangyiren/ld-api` README — <https://github.com/kongxiangyiren/ld-api>
3. 同上仓库类型定义：`src/device.ts`（`Info`/`Module`/`Models`/`Status`）、`src/generation.ts`（`ProgressEvent`/`CompleteEvent`/SSE 解析）
4. dsh-localdream 插件文档（受控模式入口、双端口分工、实践坑位）— <https://dshpluginhub.ai/zh/plugins/dsh-localdream>
5. Local Dream 技术解析（`/status` 四态、控制口/生成口协议职责）— <https://blog.gitcode.com/c2e57b38aee7dc6aa8e6e89839af77bb.html>
6. 原始接口说明 — <https://github.com/xororz/local-dream/issues/45>

---

## 四、几个实现上的关键点

**`complete.image` 是裸 RGB，不是 PNG。**
`progress` 与 `complete` 的 `image` 都是 base64 编码的**原始 RGB 字节**（`channels=3`），必须先 reshape 成 `(h,w,3)` 再转 RGBA 才能上屏。前端用 `ImageData` 逐像素展开，直接 `putImageData`。

**预览图尺寸靠推断。**
`progress` 事件不携带中间帧的宽高，只有字节数。解码器先按当前请求尺寸比对 `len/3 == w*h`；不匹配则按同一宽高比反解、并验证整除与比例误差；再退回平方数与因数分解。实测可稳定还原 512×768、768×512 等非方图。

**尺寸到底由哪个字段决定 —— 分模型族，实测为准。**

文档说「NPU 模式下生成尺寸必须与选中分辨率一致」，但**不同固件/不同模型族并不统一**。在 `3.0.0-alpha.7` 上实测：

| 模型族 | 例 | 生效字段 | 实测结果 |
|---|---|---|---|
| SD1.5 | `anythingv5` | `width` / `height` | 传 640×640（不在分辨率表里）**成功**，返回 640×640；`aspect_ratio` 被忽略 |
| SDXL | `illustrious_v16` | `aspect_ratio` | 16:9 → 1024×576；传 512×512 被忽略，仍输出 1024×1024 |
| DiT | `z_image_turbo` | `width` / `height` | 768×1024 生效；`aspect_ratio` 被忽略，退回 512×512 |

所以前端的判断是：`is_sdxl` → 只发 `aspect_ratio`；其余 → 只发 `width`/`height`。**两个字段永远不同时发**，避免后端自行取舍。

`resolutions` 字段只是可选预设，不一定是硬约束（`anythingv5` 声明了 7 种，实测任意 8 的倍数都行）。因此界面把预设做成芯片，另给一个「自定义」入口。

**切换分辨率时仍会重新 `/select`。** 虽然 alpha.7 不强制，但别的固件会强制（不一致直接报错而非缩放），重挂一次成本很低，换来跨固件一致。

**`cfg == 1.0` 会跳过无条件 UNet 分支**，此时反向提示词写了也不生效 —— 这是后端优化，不是 bug。

**图生图尺寸必须等于目标尺寸**，否则报 `Img size mismatch`。上传时会比对并在尺寸不符时给出提示。

**SSE 解析按行、只认 `data:`**，容忍 `\r\n`、跨 chunk 的半行、`[DONE]` 与心跳。完整事件立即释放流，避免连接继续下载。

---

## 五、边界与假设

- **未实现 `upscale` / `ultrafix`。** 这两个能力只在第三方插件里被提及，官方 HTTP API 参考未收录（`POST /upscale` 为 raw RGB body），不属于「受控模式已文档化接口」，因此本前端不接入。
- **不会自动挂载模型。** 设备上可能存在加载失败的模型（实测 `anima_base_v1_turbo` 在 alpha.7 上直接 `Backend process exited with code: 1`）。自动挂载会平白触发一次后端崩溃，所以启动后只同步 `/status` 里已经在跑的模型，其余等用户点。
- **不同模型的速度差异极大。** 同一台机器 6 步实测：`anythingv5` 2.6 秒、`illustrious_v16` 19.5 秒、`z_image_turbo` 186 秒。前端不做超时限制，长任务靠「取消生成」中断。
- **蒙版极性是经验约定。** 官方只写「base64 编码的 PNG/JPG 蒙版」，未规定黑白语义。当前实现导出**白 = 重绘区、黑 = 保留**。若你的后端相反，改 `exportMaskB64()` 里 `const on = src[i+3] > 24 ? 255 : 0;` 一行即可翻转。
- **同时只允许一个生成任务。** 手机 NPU 扛不住并发，生成中按钮变为「取消生成」。
- **`serve.py` 默认只监听 `127.0.0.1`。** 想让手机自己开页面用 `--bind 0.0.0.0`，但请注意受控模式本来就是对整个局域网开放的。

---

## 六、快捷键

| 键 | 作用 |
|---|---|
| `Ctrl/⌘ + Enter` | 生成 / 再生成 |
| `Esc` | 取消生成、关闭弹层 |

---

## 七、配置

设置面板是二级菜单结构：左侧导航，右侧是当前分区的表单。五个分区：

| 分区 | 内容 |
|---|---|
| **连接** | 实时连接状态条（设备 / 地址 / 刷新）、连接方式、手机地址、控制口与生成口、**保存并测试连接** |
| **生成** | 默认反向提示词、默认开启过程预览、默认预览步幅、历史保留上限 |
| **外观** | 主题（深色 / OLED 纯黑 / 浅色 / 跟随系统）、强调色 + 色板 + 从图片取色、减少动效 |
| **配置** | 生成后自动保存（目录授权）、配置 JSON 导出 / 导入、本地存储统计、清空历史 |
| **关于** | 运行时信息（连接方式 / 设备 / App 版本 / 协议 / 可用模型 / 当前挂载 / 后端状态）、接口依据链接 |

底部固定「恢复默认 / 取消 / 保存」。「保存并测试连接」会先落盘再逐个探测 8808 与 8081，直接告诉你哪个口不通。

配置存在浏览器 `localStorage`（键 `ldstudio.config.v1`），导出 / 导入走同一份 JSON。窄屏（<760px）下左侧导航自动折叠成顶部横向标签。

### 生成后自动保存

在「配置 → 生成后自动保存」里点「选择文件夹」，浏览器会弹出目录授权框（`showDirectoryPicker`）。授权后每张出图都会自动写入该目录，文件名 `LD_YYYYMMDD_HHMMSS_<seed>.png`。

- 目录句柄存在 IndexedDB 里，刷新页面不用重选；但浏览器可能在重启后要求再确认一次权限，届时会提示「目录权限已失效」。
- 页面只能写进你亲手点选的那个文件夹，读不到其中其他内容。
- 仅 Chromium 系（Chrome / Edge）支持。Firefox / Safari 没有该 API，设置里会直接标注不支持并禁用按钮。

### 主题与配色

- **OLED 纯黑**：背景、面板、画布全部压到 `#000`，并把顶部装饰光晕关掉（`--glow:0`），保证 OLED 屏像素真正熄灭。
- **跟随系统**：读 `prefers-color-scheme`，系统切换时实时响应。
- **动态配色**：浏览器**拿不到**操作系统级强调色——Windows 主题色、Android Material You 都没有对应 Web API，这一条做不到。替代方案是「从图片取色」：选一张壁纸或参考图，按色相 20° 分桶、用「饱和度 × 明度居中」加权取主色，思路与 Material You 的壁纸取色一致，只是简化版。

---

## 七·五、画布交互

图片区域支持完整的查看操作：

| 操作 | 效果 |
|---|---|
| 滚轮 | 以光标为锚点缩放（50%–2000%） |
| 拖拽 | 平移画布（局部重绘模式下改用中键 / 右键 / 空格 + 拖拽，避免和涂抹冲突） |
| 下拉框 | 适应窗口 / 25% / 50% / 75% / 100% / 150% / 200% / 300% / 400% |
| 重置按钮 | 回到「适应窗口」并清零平移 |
| 双击 | 在「适应窗口」与 100% 之间切换 |

尺寸适配由 JS 计算「contain 比例」后施加 `transform: scale()`，而不是依赖 CSS 的 `max-width/max-height` 百分比——后者在 flex 容器里遇到内容尺寸不确定的情况会失效，导致宽高比与窗口不符的图片直接显示不出来。现在任意比例都会正确铺满且保持比例。

---

## 七·六、模型分类

模型列表按架构分组，顶部有筛选芯片：**全部 / SD 1.5 / SDXL / DiT / Anima**，芯片上带数量。

判定顺序：`dit_kind` 非空 → DiT；否则 `is_sdxl` → SDXL；否则 `is_anima` → Anima；剩下的归 SD 1.5。之所以把 `dit_kind` 放最前，是因为它来自后端、最具体，而 SDXL 标志位在部分 DiT 模型上也会同时为真。

### 种子行为

生成结束后，若**未锁定**种子，输入框会自动换成一个新的随机值——不用再手动点骰子。本次实际用的种子显示在结果栏，点「固种重跑」会把它填回输入框再跑一遍。锁定后则完全不动，适合固定构图只改提示词。
