import os
from jinja2 import Environment, FileSystemLoader, select_autoescape

class TemplateManager:
    def __init__(self, templates_dir='templates'):
        self.env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape(['html'])
        )
    
    def render_telegraph_template(self, messages):
        template = self.env.get_template('telegraph/message_record.html')
        return template.render(messages=messages)
    
    def render_wechat_template(self, messages):
        template = self.env.get_template('wechat_template.html')
        
        # 处理消息中的 GIF
        for msg in messages:
            if msg['type'] == 'photo' and msg['content'].endswith('.gif'):
                # 为 GIF 添加特殊标记
                msg['is_gif'] = True
        
        return template.render(messages=messages) 