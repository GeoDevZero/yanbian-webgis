"""Vercel 入口 → /api/chat

Vercel 的 Python 运行时**按文件名路由**：

    api/hello.py   →  https://你的域名/api/hello
    api/chat.py    →  https://你的域名/api/chat

所以每个接口都需要一个入口文件。但这些文件里没有一行业务逻辑，
它们只做一件事：把根目录 app.py 里的那个 FastAPI 应用引进来复用。

这样做的好处是——同一个 app.py：
    本地  uvicorn app:app --port 8001
    线上  Vercel 自动挂到这个函数上
两边跑的是同一份代码，不存在「线上版本」和「本地版本」两个东西。
"""

import os
import sys

# 把仓库根目录加进模块搜索路径，才能 import 到根目录的 app.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402,F401  （Vercel 认的就是这个 app 变量）
