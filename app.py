import math
import json

import os
from dotenv import load_dotenv
from openai import OpenAI


from fastapi import FastAPI

# 用「本文件所在目录」拼绝对路径，不依赖启动时的工作目录（部署到云端必须这样写）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GEOJSON_PATH = os.path.join(BASE_DIR, "yanbian.geojson")

app = FastAPI(title="延边州地理小助手 API")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # 学习阶段先全放开；正式项目要写具体域名
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.get("/api/hello")
def hello():
    return {"message": "你好，延边", "status": "ok"}


@app.get("/api/stats")
def stats():
    # 读同目录下的 GeoJSON
    with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    features = data["features"]
    names = [feat["properties"].get("name", "未命名") for feat in features]

    return {
        "要素总数": len(features),
        "县市列表": names,
    }
@app.get("/api/version")
def version():
    return {"项目":"延边州地理小助手","版本":"0.1","作者":"梁坤锋"}

load_dotenv()


API_KEY = os.environ.get("DASHSCOPE_API_KEY")
if not API_KEY:
    raise RuntimeError(
        "缺少环境变量 DASHSCOPE_API_KEY。"
            "本地：检查项目目录下的 .env；线上：到平台的 Environment / Secrets 里配置。"
            )

client = OpenAI(api_key=API_KEY, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
            



# @app.get("/api/chat")
# def chat(q: str):
#     resp = client.chat.completions.create(
#         model="qwen-plus",
#         messages=[{"role": "user", "content": q}],
#     )
#     return {"问题": q, "回答": resp.choices[0].message.content}
 
@app.get("/api/chat")
def chat(q: str):
    """对外接口：出错时把错误原样返回，而不是丢一个光秃秃的 500。
    线上排查时，浏览器里就能直接看到卡在哪一步。"""
    try:
        return _chat(q)
    except Exception as e:
        return {
            "问题": q,
            "回答": f"（后端错误）{type(e).__name__}: {str(e)[:300]}",
            "地图动作": [],
        }


def _chat(q: str):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": q},
    ]
    map_actions = []

    for _ in range(5):         # 最多来回 5 轮
        resp = client.chat.completions.create(
            model="qwen-plus",
            messages=messages,
            tools=TOOLS,
        )
        msg = resp.choices[0].message
        messages.append(msg)

        # 没有工具调用 → 这就是最终回答
        if not msg.tool_calls:
            回答 = msg.content or ""
            # 【代码兜底】只要调过距离工具，就强制带上这句，不靠模型自觉
            if any(a.get("类型") == "line" for a in map_actions):
                回答 += "\n\n（以上为球面直线距离，不含道路与路况信息；驾车距离与时间请以导航为准。）"
            return {
                "问题": q,
                "回答": 回答,
                "地图动作": map_actions,
            }

        # 有工具调用 → 一个个执行，把结果喂回去
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}

            fn = TOOL_IMPL.get(name)
            result = fn(**args) if fn else {"错误": f"未知工具 {name}"}

            # 把绘图指令抽出来（不要给模型看，它看不懂也用不上）
            map_actions.extend(result.pop("_地图动作", []))

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

    # 循环用尽仍未收尾 → 兜底返回。绝不能走到函数末尾（那样会 return None，前端收到 null）
    return {"问题": q, "回答": "（工具调用次数过多，已停止）", "地图动作": map_actions}



EARTH_R = 6371.0        # 地球平均半径（公里）

# ========== 工具 1：找县市中心 ==========
# def county_center(name):
#     """
#     输入：'延吉市'
#     返回：[经度, 纬度]，例如 [129.51, 42.90]
#     找不到返回 None
#     """
    
#     with open("yanbian.geojson" ,"r" ,encoding="utf-8") as f:
#         features = json.load(f)["features"]

#     # 2) 遍历 features，找 properties['name'] == name 的那个
#     for feat in features:
#         if feat["properties"].get("name") != name:
#             continue

#         pts = []

#         def collect(node):
#             if isinstance(node[0], (int,float)):
#                 pts.append(node)
#             else:
#                 for sub in node:
#                     collect(sub)
#         collect(feat["geometry"]["coordinates"])

#         lng = sum(p[0] for p in pts) / len(pts)
#         lat = sum(p[1] for p in pts) / len(pts)
#         return [round(lng, 6), round(lat, 6)]

#     return None


def county_center(name):
    """返回县市政府驻地经纬度 [lng, lat]，找不到返回 None"""
    with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
        features = json.load(f)["features"]

    for feat in features:
        if feat["properties"].get("name") != name:
            continue
        p = feat["properties"]
        return p.get("center") or p.get("centroid")   # center 优先，缺了退一步

    return None
# ========== 工具 2：球面距离 ==========
def haversine(a, b):
    """
    a, b 都是 [经度, 纬度]
    返回：两点的球面距离（公里），保留 1 位小数
    """
    lon1, lat1 = a
    lon2, lat2 = b

    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = p2 - p1
    dlon = math.radians(lon2 - lon1)

    h = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return round(2 * EARTH_R * math.asin(math.sqrt(h)), 1)


# ========== 两个工具的"包装"（给模型用的版本）==========
def tool_calc_distance(from_name, to_name):
    a = county_center(from_name)
    b = county_center(to_name)

    if a is None or b is None:
        return {"错误": f"找不到县市：{from_name if a is None else to_name}"}

    km = haversine(a, b)
    return {
        "起点": from_name,
        "终点": to_name,
        "距离公里": km,
        "起点经纬度": a,
        "终点经纬度": b,
        "_地图动作": [{
            "类型": "line",
            "坐标": [a, b],
            "标注": f"{from_name} → {to_name}：{km} 公里",
        }],
    }


def tool_make_buffer(name, radius_km):
    c = county_center(name)
    if c is None:
        return {"错误": f"找不到县市：{name}"}

    return {
        "中心": name,
        "半径公里": radius_km,
        "圆心经纬度": c,
        "_地图动作": [{
            "类型": "circle",
            "经纬度": c,
            "半径公里": radius_km,
            "标注": f"{name} {radius_km} 公里缓冲区",
        }],
    }

def tool_estimate_drive_time(distance_km, avg_speed_kmh=60):
    # 代码兜底：参数不合法就退回默认值，绝不信任模型填的数
    if not isinstance(avg_speed_kmh, (int, float)) or not (30 <= avg_speed_kmh <= 120):
        avg_speed_kmh = 60
    try:
        distance_km = float(distance_km)
    except Exception:
        return {"错误": "距离必须是数字"}
    if distance_km <= 0:
        return {"错误": "距离必须大于 0"}

    hours = distance_km / avg_speed_kmh
    return {
        "驾车时间_小时": round(hours, 2),
        "估算依据": f"按平均 {avg_speed_kmh} km/h 估算，不含红绿灯、限速与路况"
    }

# ========== 工具清单 + 调度表 ==========
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calc_distance",
            "description": "计算延边州两个县市之间的直线距离，单位公里。当用户问『多远』『距离』『到…有多远』时使用。只计算两点直线距离，不包含路况、限速和驾车时间，不能用于回答行驶时长",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_name": {"type": "string", "description": "起点县市名，必须是延边州下辖县市，例如 延吉市"},
                    "to_name": {"type": "string", "description": "终点县市名，例如 珲春市"},
                },
                "required": ["from_name", "to_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "make_buffer",
            "description": "以某个县市的中心为圆心生成缓冲区，并画在地图上。当用户说『缓冲区』『周边多少公里』『画个圈』时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "县市名，例如 延吉市"},
                    "radius_km": {"type": "number", "description": "缓冲半径，单位公里，例如 30"},
                },
                "required": ["name", "radius_km"],
            },
        },
    },
    {
    "type": "function",
    "function": {
        "name": "estimate_drive_time",
        "description": "按给定的平均车速估算驾车耗时。仅在用户明确询问行车时间时使用；结果只是粗估，不代表真实路况。",
        "parameters": {
            "type": "object",
            "properties": {
                "distance_km": {
                    "type": "number",
                    "description": "距离，单位公里"
                },
                "avg_speed_kmh": {
                    "type": "number",
                    "description": "平均车速，单位 km/h，取值范围 30-120。未指明时默认 60"
                            }
                        },
                        "required": ["distance_km"]
                    }
                }
            }

]

TOOL_IMPL = {
    "calc_distance": tool_calc_distance,
    "make_buffer": tool_make_buffer,
    "estimate_drive_time": tool_estimate_drive_time,
}

SYSTEM_PROMPT = (
    "你是延边州地理小助手。延边州下辖 8 个县市："
    "延吉市、图们市、敦化市、珲春市、龙井市、和龙市、汪清县、安图县。\n"
    "当问题涉及距离或缓冲区这类空间计算时，必须调用工具，不要凭记忆编造数字。\n"
    "凡是涉及行车/驾车时间的问题，必须调用 estimate_drive_time 工具，不要自己估算。\n"
    "其他问题直接回答。回答简洁，用中文。"
)


# ========== 部署自检 ==========
# 线上出现 500 时，打开 /api/diag 就能看到卡在哪一步：
# 密钥有没有读到、模型接口连不连得上、每次调用要多久。
@app.get("/api/diag")
def diag():
    import platform
    import time

    key = os.environ.get("DASHSCOPE_API_KEY") or ""
    info = {
        "python 版本": platform.python_version(),
        "密钥已注入": bool(key),
        "密钥前 6 位": (key[:6] + "…") if key else "",
        "密钥长度": len(key),
        "密钥后 4 位": key[-4:] if key else "",
        "末尾是否有换行或空格": bool(key) and key != key.strip(),
        "模型地址": str(client.base_url),
    }

    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model="qwen-plus",
            messages=[{"role": "user", "content": "只回一个字：好"}],
            timeout=20,
        )
        info["模型调用"] = "成功"
        info["耗时秒"] = round(time.time() - t0, 2)
        info["模型回复"] = (resp.choices[0].message.content or "")[:50]
    except Exception as e:
        info["模型调用"] = "失败"
        info["耗时秒"] = round(time.time() - t0, 2)
        info["错误类型"] = type(e).__name__
        info["错误信息"] = str(e)[:500]

    return info
