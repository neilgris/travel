import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # 默认 8000，避免 macOS AirPlay 接收器占用的 5000 端口；可用 PORT 环境变量覆盖。
    port = int(os.environ.get("PORT", 8000))
    app.run(debug=True, port=port)
