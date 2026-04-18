# Time Tagger Local Setup

这个目录用于放置本地下载的 Swabian `Time Tagger` 软件包文件。

本仓库不再跟踪以下内容：

- `driver/`
- `documentation/`
- `examples/`
- `Time Tagger Lab/`

请从 Swabian 官方网站下载：

- Download:
  `https://www.swabianinstruments.com/time-tagger/downloads/`
- Installation guide:
  `https://www.swabianinstruments.com/static/documentation/TimeTagger/gettingStarted/installation.html`

下载后，请把需要的目录放到当前目录下，使结构类似：

```text
Time Tagger/
├─ README.md
├─ driver/
│  ├─ firmware/
│  ├─ python/
│  ├─ x64/
│  └─ x86/
├─ documentation/
└─ Time Tagger Lab/
```

`TDC_SPAD_Analyzer.py` 会优先从这里加载本地驱动和固件。
