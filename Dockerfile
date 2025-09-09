FROM s390x/python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY bot.py .

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 启动机器人
CMD ["python", "bot.py"]