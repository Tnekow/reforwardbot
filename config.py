import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# Bot 配置
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# 文件存储配置
MEDIA_DIR = os.getenv('MEDIA_DIR', 'output/media')
OUTPUT_DIR = os.getenv('OUTPUT_DIR', 'output')

# 微信配置
WECHAT_ACCESS_TOKEN = os.getenv('WECHAT_ACCESS_TOKEN')
WECHAT_APPID = os.getenv('WECHAT_APPID') 