import os
from datetime import datetime
from typing import Optional

class FileHandler:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
    
    async def save_file(self, file, bot, filename: Optional[str] = None) -> str:
        """
        保存文件并返回相对路径
        :param file: Telegram file object
        :param bot: Telegram bot instance
        :param filename: 可选的文件名
        :return: 相对路径
        """
        file_obj = await bot.get_file(file.file_id)
        
        if not filename:
            file_ext = os.path.splitext(file_obj.file_path)[1]
            filename = f"media_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(file_obj.file_path)}{file_ext}"
        
        local_path = os.path.join(self.base_dir, filename)
        await file_obj.download_to_drive(local_path)
        
        return os.path.relpath(local_path, start=os.path.dirname(self.base_dir)) 