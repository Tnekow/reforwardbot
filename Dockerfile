# 使用 Python 3.10 作为基础镜像
FROM python:3.10.10-slim

# 设置工作目录
WORKDIR /app

# 安装依赖项所需的工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
 && rm -rf /var/lib/apt/lists/*

# 将项目的依赖安装文件（如 requirements.txt）复制到容器中
COPY requirements.txt .

# 安装依赖项
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件到容器中
COPY . .

# 设置启动命令
CMD ["python", "bot.py"]
