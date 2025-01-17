import requests
import json
import urllib.request as urllib2
import os
from pprint import pprint
import logging


# 参考文档： https://developers.weixin.qq.com/doc/offiaccount/Draft_Box/Add_draft.html

logger = logging.getLogger(__name__)

class Wechat:
    def __init__(self, token, wechat_appid):
        self.access_token = token
        self.wechat_appid = wechat_appid
        self.access_token_2 = ""
        self.get_access_token()
    def get_access_token(self):
        url = 'https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={}&secret={}'.format(self.wechat_appid, self.access_token)
        response = requests.get(url)
        data = response.json()
        # pprint(data)
        self.access_token_2 = data['access_token']
        return data['access_token']

    def post_article(self, cookie,  data):
        url = 'https://mp.weixin.qq.com/cgi-bin/operate_appmsg?token={}⟨=zh_CN&t=ajax-response⊂=create&ajax=1'.format(self.access_token_2)
        headers = {'cookie': cookie}
        response = requests.post(url, data=data, headers=headers)
        return response.json()

    def upload_image_to_wechat(self, imgpath):
        logger.info(f"开始上传图片到微信: {imgpath}")
        try:
            return self.upload_media(imgpath, mediaType='image')
        except Exception as e:
            logger.exception(f"上传图片到微信时发生错误: {str(e)}")
            raise
    
    def upload_tmp_image(self, imgpath):
        resp = requests.post('https://api.weixin.qq.com/cgi-bin/media/upload',
                            params=dict(access_token=self.access_token_2,type='thumb'),
                            files=dict(media=open(imgpath,'rb'))).json()

        if 'errcode' in resp:
            raise ValueError(resp['errmsg'])
        return  resp['media_id']
    
    def upload_media(self, file_path, mediaType='image'):
        logger.info(f"开始上传媒体文件: {file_path}, 类型: {mediaType}")
        
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            raise FileNotFoundError(f"File not found: {file_path}")
        
        url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={self.access_token_2}&type={mediaType}"
        logger.info(f"上传URL: {url}")
        
        try:
            with open(file_path, 'rb') as f:
                files = {'media': f}
                logger.info("开始发送请求...")
                response = requests.post(url, files=files)
                logger.info(f"请求响应状态码: {response.status_code}")
                
                if response.status_code != 200:
                    logger.error(f"上传失败，HTTP状态码: {response.status_code}")
                    logger.error(f"响应内容: {response.text}")
                    raise Exception(f"Upload failed with status code: {response.status_code}")
                
                result = response.json()
                logger.info(f"上传响应: {result}")
                
                if 'media_id' not in result:
                    if result.get('errcode') == 40001:
                        logger.info("Token 过期，尝试刷新...")
                        self.get_access_token()
                        return self.upload_media(file_path, mediaType)
                    logger.error(f"上传失败，返回结果中没有 media_id: {result}")
                    raise Exception(f"Upload failed: {result.get('errmsg', 'Unknown error')}")
                
                logger.info(f"上传成功，media_id: {result['media_id']}")
                return result['media_id'], result.get('url', '')
                
        except Exception as e:
            logger.exception(f"上传媒体文件时发生错误: {str(e)}")
            raise

    def send_draft(self, html_file, thumb_media_id):
        logger.info(f"开始发送草稿: {html_file}, 缩略图ID: {thumb_media_id}")
        
        if not os.path.exists(html_file):
            logger.error(f"HTML文件不存在: {html_file}")
            raise FileNotFoundError(f"HTML file not found: {html_file}")
        
        url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={self.access_token_2}"
        logger.info(f"发送草稿URL: {url}")
        
        try:
            self.get_access_token()
            with open(html_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if isinstance(thumb_media_id, tuple):
                logger.info(f"从元组中提取 media_id: {thumb_media_id[0]}")
                thumb_media_id = thumb_media_id[0]
            
            data = {
                "articles": [{
                    "title": "消息记录",
                    "author": "Bot",
                    "content": content,
                    "digest": "消息记录",
                    "thumb_media_id": thumb_media_id
                }]
            }
            
            logger.info("开始发送草稿请求...")
            logger.info(f"发送的数据: {data}")
            response = requests.post(url, json=data)
            logger.info(f"草稿请求响应状态码: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"发送草稿失败，HTTP状态码: {response.status_code}")
                logger.error(f"响应内容: {response.text}")
                raise Exception(f"Send draft failed with status code: {response.status_code}")
            
            result = response.json()
            logger.info(f"发送草稿响应: {result}")
            
            if result.get('errcode', 0) != 0:
                logger.error(f"发送草稿失败: {result}")
                raise Exception(f"Send draft failed: {result.get('errmsg', 'Unknown error')}")
            
            logger.info("草稿发送成功")
            return result
            
        except Exception as e:
            logger.exception(f"发送草稿时发生错误: {str(e)}")
            raise

if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv('.env')
    wechat_access_token= os.environ.get('WECHAT_ACCESS_TOKEN')
    wechat_appid = os.environ.get('WECHAT_APPID')
    wechat = Wechat(wechat_access_token, wechat_appid)
    wechat.upload_media('/home/nnn/code/upload_vx/downloaded_images/247a6e91f2819ab544e1521e8a32296a41a5f0969b122c11e332d52e3d2a7c8e.jpg')
    # access_token = wechat.get_access_token()
    # results = wechat.upload_image_to_wechat( "/home/nnn/code/upload_vx/test.jpg")

    # print(results)
    pass