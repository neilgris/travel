"""给模板注入内联 JSON 的公共小工具。表现层关注点（非业务逻辑），故放 blueprints/ 下。"""
import json


def safe_json(obj):
    # 城市名、旅程标题等是用户自由文本，要进内联 <script>。转义 < > & 防止 </script>
    # 截断/注入，同时保留 ensure_ascii=False 让中文可读。Flask 的 |tojson 默认
    # ensure_ascii=True，中文会变成 \uXXXX，这份实现刻意保留可读性。
    return (json.dumps(obj, ensure_ascii=False)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))
