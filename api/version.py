"""Vercel 入口 → /api/version（项目信息）

业务逻辑在根目录 app.py，这里只是入口。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402,F401
