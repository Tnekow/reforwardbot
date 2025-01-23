import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler, 
    CallbackQueryHandler, 
    ContextTypes,
    MessageHandler,
    filters
)
import os
from datetime import datetime
import aiofiles
import aiohttp
from config import TELEGRAM_BOT_TOKEN, MEDIA_DIR, OUTPUT_DIR, WECHAT_ACCESS_TOKEN, WECHAT_APPID
from utils.file_handler import FileHandler
from telegraph import Telegraph
import asyncio
from extend.wechat import Wechat
from utils.telegraph_handler import TelegraphHandler
import tempfile
from PIL import Image
import io
from utils.template_manager import TemplateManager
import PIL
import lottie
from lottie import parsers
from lottie import exporters
import subprocess
import imageio
import numpy
from dotenv import load_dotenv
from io import BytesIO
import json
import requests

# 加载 .env 文件中的环境变量
load_dotenv()

# 从环境变量中获取 CHAT_ID
CHAT_ID = os.getenv("CHAT_ID")

# 初始化日志
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# 用于存储消息的字典，key是chat_id
message_store = {}

# 初始化文件处理器
file_handler = FileHandler(MEDIA_DIR)

# 在文件开头添加 Telegraph 初始化
telegraph = Telegraph()
telegraph.create_account(short_name='message_recorder_bot')

# 确保目录存在
os.makedirs(MEDIA_DIR, exist_ok=True)

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("抱歉，我无法理解您的命令或您无权访问该功能。")

async def restrict_access(update: Update) -> bool:
    """限制访问，仅允许特定用户和群组"""
    allowed_chat_ids = [CHAT_ID]  # 允许访问的用户或群组 ID 列表，CHAT_ID 来自 .env 配置

    chat_id = update.effective_chat.id
    print(allowed_chat_ids, chat_id)
    if str(chat_id) not in allowed_chat_ids:
        await update.message.reply_text('抱歉，你没有权限使用此机器人。')
        return False
    return True


async def upload_to_telegraph(html_content: str) -> str:
    """上传内容到 Telegraph 并返回链接"""
    formatted_content = html_content.replace('<html>', '').replace('</html>', '')
    formatted_content = formatted_content.replace('<body>', '').replace('</body>', '')
    
    response = await asyncio.to_thread(
        telegraph.create_page,
        title='消息记录',
        html_content=formatted_content
    )
    return f"https://telegra.ph/{response['path']}"

async def upload_to_telegram(file_data: BytesIO) -> str:
    """上传文件到 Telegram 并返回文件 URL"""
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument'
    files = {
        'document': ('sticker.gif', file_data.getvalue(), 'image/gif')
    }
    data = {
        'chat_id': CHAT_ID
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data, files=files) as response:
            if response.status == 200:
                result = await response.json()
                if result.get('ok'):
                    file_id = result['result']['document']['file_id']
                    file_path_response = await session.get(f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile', 
                                                           params={'file_id': file_id})
                    if file_path_response.status == 200:
                        file_path = (await file_path_response.json())['result']['file_path']
                        return f'https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}'
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await restrict_access(update):
        return  # 立即停止处理此命令
    chat_id = update.effective_chat.id
    # 初始化该用户的消息存储
    message_store[chat_id] = []
    # Reset the reminder flag when starting a new recording
    context.user_data['start_reminder_shown'] = False
    
    await update.message.reply_text('开始记录消息。请发送消息，完成后输入 /end 来结束。')

async def end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    
    if chat_id not in message_store:
        await update.message.reply_text('请先使用 /start 命令开始记录。')
        return
    
    messages = message_store[chat_id]
    message_count = len(messages)
    
    # 为微信创建消息的深拷贝，这样不会影响 Telegraph 的 URL
    wechat_messages = []
    telegraph_messages = []
    for msg in messages:
        # 为微信创建一个副本
        wechat_msg = msg.copy()
        wechat_messages.append(wechat_msg)
        
        # 为Telegraph创建一个副本
        telegraph_msg = msg.copy()
        if telegraph_msg['type'] == 'photo' and 'telegraph_url' in telegraph_msg:
            telegraph_msg['content'] = telegraph_msg['telegraph_url']
        telegraph_messages.append(telegraph_msg)
    
    # 初始化微信
    wechat = Wechat(WECHAT_ACCESS_TOKEN, WECHAT_APPID)
    
    # 先处理所有图片，上传到微信
    first_image_path = None
    for idx, msg in enumerate(wechat_messages):
        if msg['type'] == 'photo':
            try:
                logger.info(f"开始处理图片: {msg['content']}")
                
                # 检查是否是URL
                if msg['content'].startswith('http'):
                    # 下载图片到临时文件
                    temp_path = os.path.join(MEDIA_DIR, f"temp_{os.path.basename(msg['content'])}")
                    async with aiohttp.ClientSession() as session:
                        async with session.get(msg['content']) as response:
                            if response.status == 200:
                                with open(temp_path, 'wb') as f:
                                    f.write(await response.read())
                                msg['content'] = temp_path
                            else:
                                raise Exception(f"下载图片失败，状态码: {response.status}")
                
                # 如果是第一张图片，保存其路径作为封面
                if first_image_path is None:
                    first_image_path = msg['content']
                    logger.info(f"设置第一张图片作为封面: {first_image_path}")
                
                # 上传到微信
                wx_url = wechat.upload_image_to_wechat(msg['content'])[1]
                msg['content'] = wx_url
                
                # 如果是临时文件，删除它
                if 'temp_' in msg['content']:
                    try:
                        os.unlink(msg['content'])
                    except Exception as e:
                        logger.error(f"删除临时文件失败: {str(e)}")
                
            except Exception as e:
                logger.exception(f"处理图片时出错: {str(e)}")
                msg['type'] = 'text'
                msg['content'] = '[图片处理失败]'
    
    # 如果没有成功处理任何图片，使用一个默认图片作为封面
    if not first_image_path:
        logger.info("没有可用的图片作为封面，使用默认图片")
        default_image_path = os.path.join(os.path.dirname(__file__), 'assets', 'default_cover.jpg')
        if os.path.exists(default_image_path):
            first_image_path = default_image_path
        else:
            raise ValueError("需要至少一张图片作为封面，且默认封面图片不存在")
    
    # 初始化模板管理器
    template_manager = TemplateManager()
    
    # 生成 Telegraph HTML（使用带有Telegraph URL的消息）
    telegraph_html = template_manager.render_telegraph_template(telegraph_messages)
    
    # 上传到 Telegraph
    telegraph_url = await upload_to_telegraph(telegraph_html)
    
    try:
        # 如果有图片，上传第一张作为缩略图
        if first_image_path:
            thumb_media_id = wechat.upload_media(first_image_path, mediaType='thumb')
        else:
            # 如果没有图片，抛出异常
            raise ValueError("需要至少一张图片作为封面")
        
        # 使用模板生成微信文章 HTML（使用微信的图片URL）
        wechat_html = template_manager.render_wechat_template(wechat_messages)
        
        # 保存HTML到临时文件
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.html', encoding='utf-8') as tmp_file:
            tmp_file.write(wechat_html)
            html_path = tmp_file.name
        
        # 发送到微信草稿箱
        result = wechat.send_draft(html_path, thumb_media_id)
        
        # 清理临时文件
        os.unlink(html_path)
        if first_image_path:
            os.unlink(first_image_path)
        
        await update.message.reply_text(
            f'记录结束。共收到 {message_count} 条消息。\n'
            f'Telegraph URL: {telegraph_url}\n'
            f'已同步到微信公众号草稿箱'
        )
    except Exception as e:
        await update.message.reply_text(f'同步到微信时出错: {str(e)}')
    
    del message_store[chat_id]

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await restrict_access(update):
        return

    chat_id = update.effective_chat.id
    
    if chat_id not in message_store:
        # Check if we've already shown the reminder
        if not context.user_data.get('start_reminder_shown'):
            await update.message.reply_text('请先使用 /start 命令开始记录。')
            context.user_data['start_reminder_shown'] = True
        return
    
    message = {
        'time': update.message.date.strftime("%Y-%m-%d %H:%M:%S"),
        'type': 'text'
    }
    
    # 处理不同类型的消息
    if update.message.text:
        message['type'] = 'text'
        message['content'] = update.message.text
    elif update.message.sticker:
        file = await context.bot.get_file(update.message.sticker.file_id)
        logger.info(f"处理贴纸: animated={update.message.sticker.is_animated}, video={update.message.sticker.is_video}")
        # 检查 sticker 类型
        if update.message.sticker.is_animated or update.message.sticker.is_video:
            try:
                # 下载动态贴纸
                sticker_path = os.path.join(MEDIA_DIR, f"sticker_{file.file_id}")
                if update.message.sticker.is_animated:
                    sticker_path += '.tgs'
                    logger.info(f"下载动态贴纸到: {sticker_path}")
                elif update.message.sticker.is_video:
                    sticker_path += '.webm'
                    logger.info(f"下载视频贴纸到: {sticker_path}")
                await file.download_to_drive(sticker_path)
                
                # 处理动态贴纸
                if update.message.sticker.is_animated:
                    # 解析 TGS 文件
                    logger.info("开始解析 TGS 文件")
                    animation = parsers.tgs.parse_tgs(sticker_path)
                    # 导出为 GIF
                    gif_path = os.path.join(MEDIA_DIR, f"sticker_{file.file_id}.gif")
                    logger.info(f"导出 GIF 到: {gif_path}")
                    exporters.gif.export_gif(animation, gif_path)
                    logger.info("GIF 导出完成")
                    
                    message['type'] = 'photo'
                    message['content'] = gif_path  # 为微信使用本地 GIF 路径
                    
                    # 如果是第一个贴纸，还需要生成 PNG 作为封面
                    if len(message_store[chat_id]) == 0:
                        png_path = os.path.join(MEDIA_DIR, f"sticker_{file.file_id}.png")
                        exporters.png.export_png(animation, png_path)
                        message['is_first'] = True
                        message['cover_path'] = png_path
                    
                    # 为 Telegraph 上传 GIF 并获取 URL
                    try:
                        logger.info(f"开始上传GIF到Telegram: {gif_path}")
                        # 读取GIF文件到内存
                        with open(gif_path, 'rb') as f:
                            gif_data = BytesIO(f.read())
                        
                        # 上传到Telegram获取URL
                        url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument'
                        files = {
                            'document': ('sticker.gif', gif_data.getvalue(), 'image/gif')
                        }
                        data = {
                            'chat_id': CHAT_ID
                        }
                        
                        # 使用 requests 上传到 Telegram
                        response = await asyncio.to_thread(
                            requests.post,
                            url,
                            files=files,
                            data=data
                        )
                        
                        logger.info(f"Telegram 上传状态: {response.status_code}")
                        if response.status_code == 200:
                            result = response.json()
                            if result.get('ok'):
                                file_id = result['result']['document']['file_id']
                                file_path_response = await asyncio.to_thread(
                                    requests.get,
                                    f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile',
                                    params={'file_id': file_id}
                                )
                                if file_path_response.status_code == 200:
                                    file_path = file_path_response.json()['result']['file_path']
                                    telegram_url = f'https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}'
                                    
                                    # 创建Telegraph页面
                                    content = [
                                        {
                                            'tag': 'p',
                                            'children': [
                                                {
                                                    'tag': 'img',
                                                    'attrs': {'src': telegram_url}
                                                }
                                            ]
                                        }
                                    ]
                                    response = await asyncio.to_thread(
                                        telegraph.create_page,
                                        title='Sticker Test',
                                        author_name='Bot',
                                        content=content
                                    )
                                    if 'path' in response:
                                        message['telegraph_url'] = f"https://telegra.ph/{response['path']}"
                                        logger.info(f"Telegraph 页面 URL: {message['telegraph_url']}")
                                    else:
                                        logger.error(f"创建Telegraph页面失败: {response}")
                                else:
                                    logger.error("获取Telegram文件路径失败")
                            else:
                                logger.error(f"上传到Telegram失败: {result}")
                        else:
                            logger.error(f"上传到Telegram失败，状态码: {response.status_code}")
                    except Exception as e:
                        logger.error(f"处理动态贴纸上传失败: {str(e)}")
                    
                    # 如果是优化后的GIF，清理它
                    if 'optimized_' in gif_path:
                        try:
                            os.unlink(gif_path)
                        except Exception as e:
                            logger.error(f"删除优化后的GIF失败: {str(e)}")
                    
                elif update.message.sticker.is_video:
                    # 处理视频贴纸为 GIF
                    gif_path = os.path.join(MEDIA_DIR, f"sticker_{file.file_id}.gif")
                    reader = imageio.get_reader(sticker_path)
                    fps = reader.get_meta_data()['fps']
                    frames = []
                    for frame in reader:
                        frames.append(frame)
                    reader.close()
                    
                    # 写入 GIF，限制帧率以控制文件大小
                    target_fps = min(fps, 15)  # 限制最大帧率
                    imageio.mimsave(gif_path, frames, fps=target_fps)
                    logger.info(f"GIF 已保存到: {gif_path}")
                    
                    message['type'] = 'photo'
                    message['content'] = gif_path  # 为微信使用本地 GIF 路径
                    
                    # 如果是第一个贴纸，使用第一帧作为封面
                    if len(message_store[chat_id]) == 0:
                        png_path = os.path.join(MEDIA_DIR, f"sticker_{file.file_id}.png")
                        imageio.imwrite(png_path, frames[0])
                        message['is_first'] = True
                        message['cover_path'] = png_path
                    
                # 为 Telegraph 上传 GIF 并获取 URL
                try:
                    logger.info(f"开始上传GIF到Telegraph: {gif_path}")
                    # 检查文件大小
                    file_size = os.path.getsize(gif_path)
                    logger.info(f"GIF文件大小: {file_size / 1024:.2f} KB")
                    
                    # 总是优化GIF以确保上传成功
                    logger.info("优化GIF以确保上传成功")
                    optimized_gif_path = os.path.join(MEDIA_DIR, f"optimized_{os.path.basename(gif_path)}")
                    reader = imageio.get_reader(gif_path)
                    frames = []
                    for frame in reader:
                        # 使用PIL调整大小
                        frame_image = Image.fromarray(frame)
                        width, height = frame_image.size
                        new_width = min(width, 320)
                        new_height = int(height * (new_width / width))
                        frame_image = frame_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                        frames.append(numpy.array(frame_image))
                    reader.close()
                    
                    # 使用更低的帧率
                    imageio.mimsave(optimized_gif_path, frames, fps=10, optimize=True)
                    gif_path = optimized_gif_path
                    logger.info(f"优化后的GIF大小: {os.path.getsize(gif_path) / 1024:.2f} KB")
                    
                    # 尝试多次上传到Telegraph
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            async with aiohttp.ClientSession() as session:
                                form = aiohttp.FormData()
                                form.add_field('file', open(gif_path, 'rb'), filename='sticker.gif', content_type='image/gif')
                                async with session.post('https://telegra.ph/upload', data=form) as response:
                                    logger.info(f"Telegraph上传响应状态码: {response.status}")
                                    if response.status == 200:
                                        result = await response.json()
                                        logger.info(f"Telegraph上传响应: {result}")
                                        if result and isinstance(result, list) and len(result) > 0:
                                            telegraph_path = result[0].get('src')
                                            if telegraph_path:
                                                message['telegraph_url'] = f'https://telegra.ph{telegraph_path}'
                                                message['content'] = message['telegraph_url']  # 使用Telegraph URL作为内容
                                                logger.info(f"Telegraph 图片 URL: {message['telegraph_url']}")
                                                break
                                    else:
                                        response_text = await response.text()
                                        logger.error(f"Telegraph上传失败，状态码: {response.status}, 响应: {response_text}")
                        except Exception as e:
                            logger.error(f"第{attempt + 1}次上传失败: {str(e)}")
                            if attempt == max_retries - 1:
                                raise
                            await asyncio.sleep(1)  # 等待1秒后重试
                    
                    # 如果是优化后的GIF，清理它
                    if 'optimized_' in gif_path:
                        try:
                            os.unlink(gif_path)
                        except Exception as e:
                            logger.error(f"删除优化后的GIF失败: {str(e)}")
                            
                except Exception as e:
                    logger.exception(f"上传GIF到Telegraph时发生错误: {str(e)}")
                    
                # 在上传完成后，确认message中是否有telegraph_url
                logger.info(f"最终的message内容: {message}")
                
                # 删除原始文件
                os.unlink(sticker_path)
                
            except Exception as e:
                logger.exception(f"处理动态贴纸失败: {str(e)}")
                message['type'] = 'text'
                message['content'] = '[贴纸处理失败]'
        else:
            try:
                # 静态贴纸处理
                sticker_path = os.path.join(MEDIA_DIR, f"sticker_{file.file_id}.webp")
                await file.download_to_drive(sticker_path)
                
                # 转换为 PNG
                with Image.open(sticker_path) as img:
                    # 强制转换为 RGB
                    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                        bg = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P':
                            img = img.convert('RGBA')
                        bg.paste(img, mask=img.split()[3] if len(img.split()) > 3 else None)
                        img = bg
                    
                    # 保存为 PNG
                    png_path = os.path.join(MEDIA_DIR, f"sticker_{file.file_id}.png")
                    img.save(png_path, 'PNG')
                    
                    # 删除原始 webp 文件
                    os.unlink(sticker_path)
                    sticker_path = png_path

                # 为 Telegraph 保存原始 URL
                message['type'] = 'photo'
                
                # 上传到Telegraph
                try:
                    async with aiohttp.ClientSession() as session:
                        form = aiohttp.FormData()
                        form.add_field('file', open(sticker_path, 'rb'), filename='sticker.png', content_type='image/png')
                        async with session.post('https://telegra.ph/upload', data=form) as response:
                            logger.info(f"Telegraph上传响应状态码: {response.status}")
                            if response.status == 200:
                                result = await response.json()
                                logger.info(f"Telegraph上传响应: {result}")
                                if result and isinstance(result, list) and len(result) > 0:
                                    telegraph_path = result[0].get('src')
                                    if telegraph_path:
                                        message['telegraph_url'] = f'https://telegra.ph{telegraph_path}'
                                        message['content'] = message['telegraph_url']  # 使用Telegraph URL作为内容
                                        logger.info(f"Telegraph 图片 URL: {message['telegraph_url']}")
                except Exception as e:
                    logger.error(f"上传PNG到Telegraph失败: {str(e)}")
                    # 如果上传失败，使用Telegram URL作为备用
                    if file.file_path.startswith('http'):
                        message['content'] = file.file_path
                    else:
                        message['content'] = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file.file_path}"
            except Exception as e:
                logger.error(f"处理静态贴纸失败: {str(e)}")
                message['type'] = 'text'
                message['content'] = f"[贴纸处理失败 {update.message.sticker.emoji if update.message.sticker.emoji else ''}]"
    elif update.message.photo:
        message['type'] = 'photo'
        photo = update.message.photo[-1]  # Get the highest quality photo
        file = await context.bot.get_file(photo.file_id)
        
        # Download the photo to local storage first
        local_path = os.path.join(MEDIA_DIR, f"photo_{file.file_id}.jpg")
        await file.download_to_drive(local_path)
        
        # Upload to Telegraph
        try:
            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()
                form.add_field('file', open(local_path, 'rb'), filename='photo.jpg', content_type='image/jpeg')
                async with session.post('https://telegra.ph/upload', data=form) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result and isinstance(result, list) and len(result) > 0:
                            telegraph_path = result[0].get('src')
                            if telegraph_path:
                                message['telegraph_url'] = f'https://telegra.ph{telegraph_path}'
                                logger.info(f"Telegraph 图片 URL: {message['telegraph_url']}")
        except Exception as e:
            logger.error(f"上传图片到Telegraph失败: {str(e)}")
            
        # Set content as the original Telegram URL for WeChat
        if file.file_path.startswith('http'):
            message['content'] = file.file_path
        else:
            message['content'] = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file.file_path}"
            
        if update.message.caption:
            message['caption'] = update.message.caption
            
        # Clean up local file
        try:
            os.unlink(local_path)
        except Exception as e:
            logger.error(f"删除临时文件失败: {str(e)}")
    elif update.message.document:
        message['type'] = 'document'
        file = await context.bot.get_file(update.message.document.file_id)
        if file.file_path.startswith('http'):
            message['content'] = file.file_path
        else:
            message['content'] = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file.file_path}"
        message['filename'] = update.message.document.file_name
    elif update.message.video:
        message['type'] = 'video'
        file = await context.bot.get_file(update.message.video.file_id)
        if file.file_path.startswith('http'):
            message['content'] = file.file_path
        else:
            message['content'] = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file.file_path}"
    elif update.message.voice:
        message['type'] = 'voice'
        file = await context.bot.get_file(update.message.voice.file_id)
        if file.file_path.startswith('http'):
            message['content'] = file.file_path
        else:
            message['content'] = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file.file_path}"
    
    # 处理转发消息
    if hasattr(update.message, 'forward_from') and update.message.forward_from:
        message['forward_from'] = update.message.forward_from.full_name
        message['forward_date'] = update.message.forward_date.strftime("%Y-%m-%d %H:%M:%S")
    
    logger.info(f"添加消息到存储: type={message['type']}, content={message.get('content', '')}")
    message_store[chat_id].append(message)

async def start_telegraph(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """测试 Telegraph 上传功能的命令"""
    await update.message.reply_text('请发送一个动态贴纸，我将测试上传到 Telegraph。发送 /end_telegraph 结束测试。')
    context.user_data['testing_telegraph'] = True

async def end_telegraph(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """结束 Telegraph 测试"""
    if context.user_data.get('testing_telegraph'):
        del context.user_data['testing_telegraph']
        await update.message.reply_text('Telegraph 测试已结束。')
    else:
        await update.message.reply_text('请先使用 /start_telegraph 开始测试。')

async def test_telegraph_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 Telegraph 测试模式下的消息"""
    if not context.user_data.get('testing_telegraph'):
        return
        
    if not update.message.sticker or not (update.message.sticker.is_animated or update.message.sticker.is_video):
        await update.message.reply_text('请发送动态贴纸进行测试。')
        return
        
    try:
        file = await context.bot.get_file(update.message.sticker.file_id)
        sticker_path = os.path.join(MEDIA_DIR, f"sticker_{file.file_id}")
        
        # 下载贴纸
        if update.message.sticker.is_animated:
            sticker_path += '.tgs'
            logger.info(f"下载动态贴纸到: {sticker_path}")
        elif update.message.sticker.is_video:
            sticker_path += '.webm'
            logger.info(f"下载视频贴纸到: {sticker_path}")
        await file.download_to_drive(sticker_path)
        
        # 转换为 GIF
        gif_path = os.path.join(MEDIA_DIR, f"sticker_{file.file_id}.gif")
        if update.message.sticker.is_animated:
            animation = parsers.tgs.parse_tgs(sticker_path)
            exporters.gif.export_gif(animation, gif_path)
        elif update.message.sticker.is_video:
            reader = imageio.get_reader(sticker_path)
            fps = reader.get_meta_data()['fps']
            frames = []
            for frame in reader:
                frames.append(frame)
            reader.close()
            imageio.mimsave(gif_path, frames, fps=min(fps, 15))
            
        # 读取 GIF 到内存
        with open(gif_path, 'rb') as f:
            gif_data = BytesIO(f.read())
            
        # 上传到 Telegram
        url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument'
        files = {
            'document': ('sticker.gif', gif_data.getvalue(), 'image/gif')
        }
        data = {
            'chat_id': CHAT_ID
        }
        
        # 使用 requests 上传到 Telegram
        response = await asyncio.to_thread(
            requests.post,
            url,
            files=files,
            data=data
        )
        
        logger.info(f"Telegram 上传状态: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                file_id = result['result']['document']['file_id']
                file_path_response = await asyncio.to_thread(
                    requests.get,
                    f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile',
                    params={'file_id': file_id}
                )
                if file_path_response.status_code == 200:
                    file_path = file_path_response.json()['result']['file_path']
                    telegram_url = f'https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}'
                    
                    # 创建 Telegraph 页面
                    content = [
                        {
                            'tag': 'p',
                            'children': [
                                {
                                    'tag': 'img',
                                    'attrs': {'src': telegram_url}
                                }
                            ]
                        }
                    ]
                    response = await asyncio.to_thread(
                        telegraph.create_page,
                        title='Sticker Test',
                        author_name='Bot',
                        content=content
                    )
                    if 'path' in response:
                        telegraph_url = f"https://telegra.ph/{response['path']}"
                        await update.message.reply_text(
                            f'测试成功！\n'
                            f'Telegram URL: {telegram_url}\n'
                            f'Telegraph URL: {telegraph_url}'
                        )
                    else:
                        await update.message.reply_text(f'创建 Telegraph 页面失败: {response}')
                else:
                    await update.message.reply_text('获取 Telegram 文件路径失败')
            else:
                await update.message.reply_text(f'上传到 Telegram 失败: {result}')
        else:
            await update.message.reply_text(f'上传到 Telegram 失败，状态码: {response.status_code}')
                    
        # 清理文件
        os.unlink(sticker_path)
        os.unlink(gif_path)
        
    except Exception as e:
        logger.exception(f"测试过程中出错: {str(e)}")
        await update.message.reply_text(f'测试失败: {str(e)}')

def main() -> None:
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # 添加命令处理器
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('end', end))
    application.add_handler(CommandHandler('start_telegraph', start_telegraph))
    application.add_handler(CommandHandler('end_telegraph', end_telegraph))
    application.add_handler(MessageHandler(filters.COMMAND, unknown))

    # 添加消息处理器，根据测试状态选择不同的处理函数
    application.add_handler(MessageHandler(
        filters.ALL & ~filters.COMMAND,
        lambda u, c: test_telegraph_upload(u, c) if c.user_data.get('testing_telegraph') else handle_message(u, c)
    ))

    application.run_polling()

if __name__ == '__main__':
    main()
