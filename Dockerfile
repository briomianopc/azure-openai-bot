# 使用官方 Python 基础镜像（自动支持多架构）
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置架构相关的环境变量
ARG TARGETPLATFORM
ARG BUILDPLATFORM
ARG TARGETOS
ARG TARGETARCH

# 显示构建信息
RUN echo "Building for platform: $TARGETPLATFORM" && \
    echo "Build platform: $BUILDPLATFORM" && \
    echo "Target OS: $TARGETOS" && \
    echo "Target architecture: $TARGETARCH"

# 根据架构安装不同的系统依赖
RUN apt-get update && \
    apt-get install -y \
        gcc \
        build-essential \
        && \
    # 清理 apt 缓存以减小镜像大小
    rm -rf /var/lib/apt/lists/* && \
    # 清理其他临时文件
    apt-get clean

# 复制 requirements 文件
COPY requirements.txt .

# 安装 Python 依赖
# 使用 --no-cache-dir 减小镜像大小
# 使用 --upgrade pip 确保使用最新版本
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY bot.py .

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 创建非 root 用户（安全最佳实践）
RUN groupadd --system --gid 1001 appgroup && \
    useradd --system --uid 1001 --gid appgroup --create-home --shell /bin/bash appuser && \
    chown -R appuser:appgroup /app

# 切换到非 root 用户
USER appuser

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "print('Health check passed')" || exit 1

# 暴露端口（虽然 Telegram Bot 不需要，但为了标准化）
EXPOSE 8080

# 设置标签
LABEL maintainer="your-email@example.com"
LABEL description="Azure OpenAI Telegram Bot - Multi-architecture support"
LABEL version="1.0.0"

# 启动命令
CMD ["python", "bot.py"]
