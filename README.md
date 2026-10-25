# 延边州地理小助手 · WebGIS + LLM Agent

用自然语言指挥一张地图。

说一句「延吉到珲春多远」，它算出球面距离，并在图上画一条带着两端标记的虚线；
说一句「以延吉为中心画 30 公里缓冲区」，它画出一个圆和一个圆心点。

**在线演示** <https://yanbian-webgis.vercel.app>

前端是原生 HTML / CSS / JavaScript + Leaflet，没有用任何框架；后端是 FastAPI；大模型用千问 `qwen-plus`（走 OpenAI 兼容接口）负责意图理解与工具选择。前后端一并部署在 Vercel，同一个域名，所以线上不需要处理跨域。

---

## 它做到的四件事

| 能力 | 表现 |
| --- | --- |
| 县域可视化 | 延边州 8 个县级单元的边界渲染、悬停弹窗、自动缩放到数据范围 |
| 点选即介绍 | 点一个县，后端调用大模型生成一句话介绍，回填到侧栏 |
| 自然语言绘图 | 「延吉到珲春多远」→ 距离 + 虚线；「以延吉为中心画 30 公里缓冲区」→ 圆 + 圆心 |
| 不该调工具时不调 | 「延边州有几个县市」→ 直接回答 8 个，不产生任何绘图动作 |

---

## 技术栈

| 层 | 用了什么 |
| --- | --- |
| 前端 | HTML5 · CSS3（Flexbox、CSS 变量、媒体查询）· 原生 JavaScript（`async/await`、`fetch`、DOM 操作）· Leaflet 1.9 |
| 后端 | Python 3.12 · FastAPI · Uvicorn · Pydantic |
| 大模型 | 千问 `qwen-plus`，通过 OpenAI 兼容 SDK 调用，使用 **function calling（工具调用）** |
| 部署 | Vercel（前后端同域）· 环境变量管理密钥 · Git 版本控制 |

---

## 本地运行

```bash
# 1. 装依赖
pip install -r requirements.txt

# 2. 配密钥（放到项目根目录的 .env，这个文件已在 .gitignore 里）
#    DASHSCOPE_API_KEY=sk-xxxxxxxx

# 3. 启动（一条命令同时提供页面和接口）
uvicorn app:app --port 8001 --reload
```

打开 <http://localhost:8001> 就是完整页面，接口文档在 <http://localhost:8001/docs>。

> 早期是把前端用 `python -m http.server 8000` 单独起一个服务、后端另起 8001，靠 CORS 打通（代码里 `API_BASE` 那段判断就是为了兼容这种双端口模式）。现在 `app.py` 会自己把 4 个静态文件返回给浏览器，一个进程就够了。

---

## 项目结构

```
webgis-day/
├── index.html            页面骨架（地图容器 + 右侧三块面板）
├── style.css             全部样式（变量、卡片、气泡、窄屏堆叠）
├── app.js                全部前端逻辑（建图、取数、发问、画图）
├── app.py                后端：接口 + 工具实现 + 工具调用循环
├── yanbian.geojson       延边州 8 个县级单元边界（约 117 KB）
├── requirements.txt      Python 依赖
├── vercel.json           函数最长执行时间
├── api/                  Vercel 的函数入口（当前线上由 app.py 统一处理，这里保留作兜底）
├── notes/                每天的学习笔记 D1–D5（踩过的坑都记在里头）
└── exp_tool.py           学习期写的独立实验脚本，不参与线上运行
    hello_llm.py
```

---

## 接口

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/api/hello` | 联通性检查 |
| GET | `/api/stats` | 返回 `{"要素总数": 8, "县市列表": [...]}` |
| GET | `/api/version` | 项目名与版本号 |
| GET | `/api/chat?q=...` | 自然语言提问，返回 `{"回答": "...", "地图动作": [...]}` |
| GET | `/docs` | FastAPI 自动生成的接口文档（OpenAPI 3.1） |

`地图动作` 是一个指令数组，前端照着它画图，例如：

```json
[
  { "类型": "line",
    "坐标": [[129.51579, 42.906964], [130.365787, 42.871057]],
    "标注": "延吉市 → 珲春市：69.4 公里" }
]
```

**为什么不让模型直接返回坐标、而是返回「动作指令」**：让模型只决定「画什么、用哪个工具、参数是多少」，坐标一律由代码计算。模型容易算错数字，但不擅长出错的地方就不让它碰。

---

## 几个实现上值得说的点

### 1. 工具调用是「模型判断 + 代码循环」，不是魔法

模型本身不会执行任何函数。它输出的是一段结构化文本（`tool_calls`），说明「我想调 `calc_distance`，参数是 `{from_name: 延吉市, to_name: 珲春市}`」。真正执行的是下面这个循环，跑在我自己的 Python 里：

```python
for _ in range(6):                       # 步数上限，防止反复调用烧钱
    msg = ask_model(messages, tools=TOOLS)

    if not msg.tool_calls:               # 模型决定不调工具，直接答
        return msg.content

    messages.append(msg)                 # 把它的「调用意图」记进对话
    for tc in msg.tool_calls:
        args = json.loads(tc.function.arguments)   # 注意：这里是字符串
        result = TOOL_IMPL[tc.function.name](**args)
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,       # 必须和请求里的 id 对上
            "content": json.dumps(result, ensure_ascii=False),
        })
```

所以「什么时候调工具、调哪个、参数填什么」是模型决定的；「真的去执行、失败怎么办、最多转几轮」是代码保证的。这两件事分工，才是可用的 Agent。

### 2. 经纬度顺序：GeoJSON 是 `[经度, 纬度]`，Leaflet 要 `[纬度, 经度]`

后端按 GeoJSON 习惯返回 `[lng, lat]`，Leaflet 的 `L.circle` / `L.polyline` 要 `[lat, lng]`。搞反了不会报错，图会安静地画到南美洲去。代码里每次转换都写了注释：

```js
const [lng, lat] = a.经纬度;         // 先按 GeoJSON 的顺序拆
L.circle([lat, lng], { ... });      // 再按 Leaflet 的顺序装
```

### 3. 县市中心不是几何质心

一开始用所有顶点取平均算县市中心，结果延吉的中心点落到了山上，缓冲区圆心明显偏了。查了 GeoJSON 才发现数据里本来就带一个手工标注的 `properties.center`（真实城区位置）。

| 取法 | 延吉 → 珲春 |
| --- | --- |
| 顶点平均 | 112.1 公里 |
| 多边形质心 | 110.8 公里 |
| `properties.center` | **69.4 公里** ✅ |

三个数差 40 多公里——这不是精度问题，是**用错了数据源**。教训：先看数据里已经有什么，再决定自己算什么。

### 4. Vercel 上静态文件也要由应用返回

第一次部署后 `/api/*` 全部正常，但访问首页返回 `{"detail":"Not Found"}`。原因是 Vercel 把根目录的 `app.py` 认成了整个项目的入口，所有请求都交给 Python，静态文件没人发。

解决办法是在 `app.py` 里用白名单把 4 个文件交出去（没有整目录挂载，`app.py`、`notes/` 不会变成网页）：

```python
@app.get("/", include_in_schema=False)
def page_index():
    return FileResponse(os.path.join(BASE_DIR, "index.html"),
                        media_type="text/html; charset=utf-8")
```

---

## 已知限制

写下来是因为它们真实存在，而不是因为已经解决：

- **距离是球面直线距离**，不含路网。问「开车要多久」时模型会顺口给个估算，那是它的常识，不是本项目的计算能力——回答里用一句代码兜底声明了这一点。
- **只支持延边州一个区域**，8 个县市写死在数据里，换区域要换 GeoJSON 并重建县市中心索引。
- **没有数据库**，所有数据来自内存里的 GeoJSON；也没有用户系统、没有对话历史持久化。
- **没有鉴权**，接口是公开的，靠调用量上限控制成本。
- **不做 RAG**：目前模型的知识完全来自预训练，没有接任何文档检索。

---

## 数据来源

延边朝鲜族自治州县级行政区划边界（`yanbian.geojson`，8 个要素），已与高德地图底图（GCJ-02）对齐。底图瓦片来自高德地图开放接口。

---

## 作者

梁坤锋 · 中国地质大学（北京）地理学硕士在读 · [GitHub @GeoDevZero](https://github.com/GeoDevZero)

> `notes/` 目录里是逐日学习笔记，记录了这张地图从「白屏」到「能听懂人话」的每一步，包括所有踩过的坑。
