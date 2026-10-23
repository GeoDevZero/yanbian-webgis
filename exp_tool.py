import os, json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(
    api_key=os.environ["DASHSCOPE_API_KEY"],
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# ① 一份"工具清单"：告诉模型它有哪些工具可用
tools = [{
    "type": "function",
    "function": {
        "name": "calc_distance",
        "description": "计算延边州两个县市之间的直线距离（公里）",
        "parameters": {
            "type": "object",
            "properties": {
                "from_name": {"type": "string", "description": "起点县市名，如 延吉市"},
                "to_name":   {"type": "string", "description": "终点县市名，如 珲春市"},
            },
            "required": ["from_name", "to_name"],
        },
    },
}]

messages = [{"role": "user", "content": "延边州有几个县市？"}]


resp = client.chat.completions.create(
    model="qwen-plus", messages=messages, tools=tools,
)

msg = resp.choices[0].message
print("=== 模型的原话（content）===")
print(repr(msg.content))
print()
print("=== 模型要调用的工具（tool_calls）===")
print(msg.tool_calls)
