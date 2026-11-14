# Localdream Web UI Studio

A browser front end for **Local Dream** on Android, driving the app's *Controlled Mode* to run text-to-image, image-to-image, inpainting and upscaling from a desktop browser.

- Single `index.html`, no build step, no front-end dependencies, no CDN
- Three resizable columns; separate layouts for wide and narrow viewports
- Live diffusion preview with cancellation
- Optional auto-save to a chosen folder, with metadata sidecars that can be re-imported
- Exportable diagnostics log for connection troubleshooting
- Interface available in Chinese, English and Russian

---

## 1. Requirements

| Item | Requirement |
|---|---|
| Server | Python 3.8 or newer |
| Browser | Chromium-based (Chrome / Edge); the File System Access API is Chromium-only |
| Device | Android phone running Local Dream 3.0.0-alpha.3 or newer |
| Network | Phone and computer on the same LAN |

---

## 2. Quick start

```bash
python serve.py --host <phone LAN IP>
```

Then open <http://127.0.0.1:8777>. The device address can also be changed in *Settings → Connection*; changes take effect immediately.

`serve.py` serves the page and acts as a reverse proxy:

| Path | Purpose |
|---|---|
| `/` | Serves `index.html` |
| `/p/8808/*` | Forwards to `http://<phone IP>:8808/*` (control port) |
| `/p/8081/*` | Forwards to `http://<phone IP>:8081/*` (generation port, including SSE and binary responses) |
| `/api/diag?host=` | TCP reachability probe for both ports |
| `/api/ping` | Returns the default device address passed at start-up |

Options: `--host` presets the device address, `--port` sets the listening port (default 8777), `--bind` sets the bind address (default `127.0.0.1`).

### The page must be served by serve.py

The two ports exposed by Controlled Mode are plain HTTP services that return no CORS headers. A page on a different origin will be blocked by the same-origin policy; a page served over HTTPS will also be blocked by mixed-content rules. `serve.py` puts the page and the API on the same origin, sidestepping both.

**Opening `index.html` directly does not work.** Under the `file://` protocol, `/p/8808/info` resolves to a local path, the request is never sent, and the browser reports a `Failed to fetch` within milliseconds. The page shows a warning banner when this is detected.

| Symptom | Cause | Action |
|---|---|---|
| Log header shows a `file:///` page address and `/p/...` requests fail instantly | Page was not opened through `serve.py` | Start `serve.py` and open `http://127.0.0.1:8777` |
| Requests abort after exactly 8000 ms | Device unreachable: IP changed, different subnet, or Controlled Mode was reclaimed | Verify the IP; re-enter Controlled Mode in the app |
| Control port responds, generation port refuses | No model selected yet, so 8081 is not listening | Select a model in the page or in the app |

---

## 3. Device preparation

Controlled Mode is declared `exported="false"` in `AndroidManifest.xml` and cannot be started externally. It must be enabled by hand:

> Local Dream → **⋮** at the top right of the model list → **Device interop** → Controlled Mode → **Enter Controlled Mode**

Two ports are then exposed:

| Port | Kind | Endpoints |
|---|---|---|
| 8808 | Control (JSON) | `GET /info`, `GET /models`, `GET /status`, `POST /select`, `POST /stop` |
| 8081 | Generation (native) | `POST /generate` (SSE), `POST /tokenize`, `POST /upscale` |

Self-check:

```bash
curl -s --max-time 6 http://<phone IP>:8808/info
# {"app":"localdream","protocol":1,"version":"...","device":"..."}
```

Android may reclaim the background process when the screen is off or after long idle periods. Enabling *Black screen (keep running)* in the app and disabling battery optimisation for Local Dream is recommended.

---

## 4. Interface

### Layout

| Viewport width | Layout |
|---|---|
| ≥ 1200 px | Three columns: models and history / canvas / parameters, with two draggable dividers; double-click resets |
| < 1200 px | Single stacked column, ordered canvas → parameters → models |

Column widths and other preferences are stored in the browser and survive reloads.

The interface language is selected in *Settings → Appearance → Language*. Chinese, English and Russian are available; the choice applies immediately and is stored locally. When no choice has been made, the browser language is used.

### Canvas

| Action | Effect |
|---|---|
| Wheel | Zoom anchored at the pointer |
| Drag | Pan (in inpaint mode use the middle button, right button, or Space + drag) |
| Dropdown | Fit to window / 25%–400% |
| Double-click | Toggle between fit and 100% |
| *Image to image* (top right) | Uses the current canvas as the img2img base, cropped to the target size |
| *Upscale* (top right) | Opens the upscale panel |

### Shortcuts

| Key | Action |
|---|---|
| `Ctrl / ⌘ + Enter` | Generate |
| `Esc` | Cancel generation, close overlays |

### Generation parameters

| Parameter | Range | Notes |
|---|---|---|
| Steps | 1 – 60 | Click the value to type an exact number |
| CFG | 0 – 20 | Below 1 the negative prompt barely applies; the panel warns about it |
| Batch | 1 – 20 | Runs several generations in sequence, each with its own seed |
| Denoise strength | 0 – 1 | img2img and inpaint only, 0.01 step |

### Models

Grouped by architecture with filter chips: All / SD 1.5 / SDXL / DiT / Anima. Classification order: non-empty `dit_kind` → DiT, then `is_sdxl` → SDXL, then `is_anima` → Anima, everything else SD 1.5.

### Image to image and inpaint

- Input images are centre-cropped to the current target size before upload, which avoids the backend's `Img size mismatch`; a note appears when the aspect ratio differs.
- *Use current preview* takes the canvas as the base image without saving and re-uploading.
- After an inpaint run the page switches back to the img2img tab so the mask overlay does not obscure the result.

### Results and history

The result bar shows seed, size, first-step time and total time. The seed can be clicked to copy; the prompt occupies its own row with expand and copy actions. Clicking a history thumbnail restores that image and its parameters onto the canvas.

---

## 5. Settings

The settings dialog is a left navigation with seven sections:

| Section | Contents |
|---|---|
| Connection | Live status, mode, device address and both ports, Save / Test connection |
| Generation | Default negative prompt, process preview, preview stride |
| Appearance | Language, theme (dark / OLED black / light / system), accent colour, reduced motion |
| History | Thumbnail size, retention limit, storage usage, clear history |
| Save | Auto-save folder, metadata toggle and format, naming pattern |
| Config | Configuration import/export, diagnostics log export |
| About | Project links, runtime information, API references |

The ⓘ icon next to each option explains it on hover or click.

### Auto-save

After a folder is authorised through the File System Access API, every generated image is written to it. A sidecar metadata file (JSON or TXT) can be enabled or disabled. File names follow a pattern supporting the placeholders:

`{date}` `{time}` `{seed}` `{model}` `{w}` `{h}` `{index}`

Upscaled results are saved as well, with an `_up` suffix and without metadata.

### Metadata

JSON and TXT share one field definition, in the same order and with the same values:

```
prompt / negative_prompt / seed / steps / cfg / scheduler / model / width / height / created / generator
```

TXT writes one `key: value` pair per line. Both formats can be imported from the *Metadata* section of the right column, filling prompt, seed, steps, CFG, sampler and size. Files can also be dropped onto the page. Import never switches the model; if the metadata names a different model a notice is shown.

A third format matches **Local Dream native parameters**, the `_localdream_params` structure exported by the app:

```json
{"_localdream_params":true,"v":1,"model_id":"...","prompt":"...","negative_prompt":"...",
 "steps":9,"cfg":1,"seed":1941100032,"scheduler":"lcm","mode":"TXT2IMG"}
```

Exporting in this format produces a file that can be fed straight back into the app. On import, the `mode` field switches to the matching generation mode (`TXT2IMG` / `IMG2IMG` / `INPAINT`). The same section also offers a paste box: paste metadata of any supported format and press *Apply metadata*.

---

## 6. API references

| Feature | Endpoint | Source |
|---|---|---|
| Connection and device info | `GET :8808/info` | Official HTTP API reference; `ld-api` type definitions |
| Models and upscalers | `GET :8808/models` | `ld-api` `Module` / `Models` |
| Load model and wait until ready | `POST :8808/select` + polling `GET /status` | `ld-api` `src/device.ts` |
| Backend status | `GET :8808/status` | Same (`idle` / `starting` / `running` / `error`) |
| Generation (SSE) | `POST :8081/generate` | Official HTTP API reference |
| Prompt token count | `POST :8081/tokenize` | Official HTTP API reference |
| Upscaling | `POST :8081/upscale` | Not in the official reference; determined empirically, see section 7 |

Further reading:

- Local Dream guide · HTTP API reference — <https://ld-guide.chino.icu/zh/features/http-api>
- `@kongxiangyiren/ld-api` — <https://github.com/kongxiangyiren/ld-api>
- Controlled Mode and the two ports — <https://dshpluginhub.ai/zh/plugins/dsh-localdream>

### Implementation notes

- The `image` field in `complete` and `progress` events is Base64-encoded raw RGB (`channels = 3`); it must be rebuilt as `width × height × 3` before drawing.
- Progress events carry no frame dimensions, so they are derived from the byte count: match the request size first, then the aspect ratio, then fall back to factorisation.
- Omitting `seed` means random; passing `-1` is treated as the fixed seed `4294967295`, so the field is not sent when empty.
- `cfg = 1.0` skips the unconditional UNet pass, so the negative prompt has no effect.
- Some backends (DiT / Anima) do not count CLIP tokens and return `max_length = 0`, meaning unlimited length.

---

## 7. Upscale API

This endpoint is not in the official documentation; the contract was established by probing the error messages step by step:

```
POST http://<phone IP>:8081/upscale
Content-Type: application/octet-stream
X-Image-Width: <width>
X-Image-Height: <height>
X-Upscaler-Path: <upscaler path>

<raw RGB24 bytes, length must equal width × height × 3>
```

- The response is `image/jpeg` at a fixed **×4** scale; headers such as `X-Scale` have no effect.
- The body must be raw RGB; PNG or JPEG payloads return `Image data size mismatch`.
- The upscaler path comes from `upscalers[].path` in `GET :8808/models`; it is empty when no upscaler is installed.
- The 2× and 3× options are produced by downscaling the native ×4 result in the browser.
- A progress indicator and elapsed time are shown during the run. Outputs above roughly 8 MP, or with an edge beyond 4096, require a second confirmation.

---

## 8. Known limitations

- **Port 8081 only listens after a model is selected.** While `state` is `idle` the generation port is closed; this is expected.
- **A short gap remains after `state` becomes `running`.** The client probes until the backend answers; generation also retries once on a network error.
- **Size fields differ by model family** (measured on 3.0.0-alpha.7):

  | Family | Effective field | Notes |
  |---|---|---|
  | SD 1.5 | `width` / `height` | `aspect_ratio` is ignored; `resolutions` are presets, not constraints |
  | SDXL | `aspect_ratio` | `width` / `height` are ignored |
  | DiT | `width` / `height` | `aspect_ratio` is ignored |

- **Direct mode is limited.** Custom request headers trigger a CORS preflight, and the device only allows `Content-Type` and `Authorization`, so upscaling must go through the same-origin proxy. In direct mode the page falls back to the proxy automatically when the local service is reachable.
- **UltraFix (tiled repaint) is not implemented.** It is supported by only some backends and is absent from the official reference.
- **Inpainting treats white as the repaint area.** The polarity is not specified officially; adjust `exportMaskB64()` if a backend expects the opposite.
- **Only one generation runs at a time.** The button becomes a cancel action while generating.

---

## 9. Configuration and storage

| Item | Location |
|---|---|
| Interface and generation preferences | `localStorage`, key `ldstudio.config.v1` |
| Auto-save folder handle | IndexedDB, database `ldstudio`, store `kv` |
| Diagnostics log | In memory, up to 800 entries, exportable |

The log records the method, path, status code and timing of every request, along with connection, model loading, generation and upscaling events and page errors. The exported file includes the page address, connection mode, device model and version, current model and canvas size, which is usually enough to diagnose a problem.

---

## 10. Project layout

```
Localdream-Web-UI-Studio/
├── index.html      # Entire interface and logic (vanilla JS)
├── serve.py        # Static server and reverse proxy (SSE passthrough)
├── README.md       # Chinese documentation
├── README.en.md    # This file
└── LICENSE
```

---

## 11. License

MIT
