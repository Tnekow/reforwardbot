import logging

class ImageProcessFilter(logging.Filter):
    def filter(self, record):
        # 只显示错误和关键信息
        if record.levelno >= logging.ERROR:
            return True
        
        # 关键处理步骤
        important_messages = [
            "开始处理图片",
            "处理图片时出错",
            "下载贴纸失败",
            "无法识别的图片格式"
        ]
        
        return any(msg in record.msg for msg in important_messages)

# 在 bot.py 中应用过滤器
logger = logging.getLogger(__name__)
logger.addFilter(ImageProcessFilter()) 