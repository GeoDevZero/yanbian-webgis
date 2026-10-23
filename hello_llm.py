import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()   # 读取同目录下的 .env

client = OpenAI(
    api_key=os.environ["DASHSCOPE_API_KEY"],
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

resp = client.chat.completions.create(
    model="qwen-plus",
    messages=[
        {"role": "user", "content": "用一句话解释什么是遥感影像的 NDVI"}
    ],
)

print(resp.choices[0].message.content)
