"""Vercel 入口 → /api/diag（部署自检）

线上报 500 时打开 https://你的域名/api/diag，
它会告诉你密钥有没有读到、模型接口连不连得上、一次调用要多久。

业务逻辑在根目录 app.py，这里只是入口。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402,F401
