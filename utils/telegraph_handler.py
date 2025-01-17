import aiohttp
from bs4 import BeautifulSoup
import os
import asyncio
from typing import Tuple, List

class TelegraphHandler:
    def __init__(self):
        self.session = None
    
    async def get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def download_page(self, url: str) -> Tuple[str, List[str]]:
        """
        下载 Telegraph 页面内容并返回 HTML 和图片 URL 列表
        返回: (HTML内容, 图片URL列表)
        """
        session = await self.get_session()
        async with session.get(url) as response:
            content = await response.text()
            
        soup = BeautifulSoup(content, 'html.parser')
        
        # 获取文章内容
        article = soup.find('article')
        if not article:
            raise ValueError("无法找到文章内容")
            
        # 获取所有图片URL
        img_urls = []
        for img in article.find_all('img'):
            if img.get('src'):
                img_urls.append(img['src'])
                
        return str(article), img_urls 