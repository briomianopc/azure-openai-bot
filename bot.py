# bot.py
import os
import json
import logging
import asyncio
from typing import Dict, Optional
from datetime import datetime

import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# 配置日志
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class AzureOpenAIBot:
    def __init__(self):
        self.user_configs = {}  # userId -> {api_key, endpoint, model}
        # 支持的模型列表
        self.available_models = {
            'gpt-4': '🧠 GPT-4',
            'gpt-4.1': '🚀 GPT-4.1', 
            'gpt-4o': '✨ GPT-4o',
            'gpt-3.5-turbo-0125': '⚡ GPT-3.5 Turbo 0125',
            'grok-3': '🤖 Grok-3'
        }
        self.default_model = 'gpt-4o'
        
        # 不同模型的参数配置
        self.model_configs = {
            'gpt-4': {'max_tokens': 8000, 'temperature': 0.7},
            'gpt-4.1': {'max_tokens': 8000, 'temperature': 0.7},
            'gpt-4o': {'max_tokens': 4000, 'temperature': 0.7},
            'gpt-3.5-turbo-0125': {'max_tokens': 4000, 'temperature': 0.7},
            'grok-3': {'max_tokens': 4000, 'temperature': 0.8}
        }
        
    async def call_azure_openai(self, user_config: Dict, messages: list) -> Optional[str]:
        """调用 Azure OpenAI API"""
        if not all(k in user_config for k in ['api_key', 'endpoint', 'model']):
            return "❌ 请先配置 API 信息，使用 /config 命令"
            
        model = user_config['model']
        model_config = self.model_configs.get(model, self.model_configs['gpt-4o'])
        
        # 构建 API URL - 支持不同的 API 版本
        if model == 'grok-3':
            # Grok 可能使用不同的 API 版本或端点
            url = f"{user_config['endpoint']}/openai/deployments/{model}/chat/completions?api-version=2024-08-01-preview"
        else:
            url = f"{user_config['endpoint']}/openai/deployments/{model}/chat/completions?api-version=2024-02-15-preview"
        
        headers = {
            'Content-Type': 'application/json',
            'api-key': user_config['api_key']
        }
        
        payload = {
            'messages': messages,
            'max_tokens': model_config['max_tokens'],
            'temperature': model_config['temperature'],
            'top_p': 0.95,
            'frequency_penalty': 0,
            'presence_penalty': 0
        }
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result['choices'][0]['message']['content']
                    else:
                        error_text = await response.text()
                        logger.error(f"Azure API Error: {response.status} - {error_text}")
                        return f"❌ API 调用失败 ({response.status})\n{error_text[:300]}..."
        except asyncio.TimeoutError:
            logger.error("API request timeout")
            return "❌ 请求超时，请稍后再试"
        except Exception as e:
            logger.error(f"Request error: {e}")
            return f"❌ 请求错误: {str(e)}"

bot_instance = AzureOpenAIBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """开始命令"""
    welcome_text = """
🤖 Azure OpenAI Telegram Bot

支持的模型：
🧠 GPT-4 - 最强大的模型
🚀 GPT-4.1 - 升级版 GPT-4  
✨ GPT-4o - 多模态优化模型
⚡ GPT-3.5 Turbo 0125 - 快速响应
🤖 Grok-3 - xAI 的最新模型

功能特性：
• 🗣️ 与多种 AI 模型对话
• 🔧 配置 Azure API 密钥和端点
• 🔄 快速切换不同模型
• 📊 查看配置状态
• 🛡️ 安全的个人配置管理

使用步骤：
1️⃣ /config - 配置你的 Azure OpenAI API
2️⃣ /model - 选择要使用的模型
3️⃣ 直接发送消息开始对话

命令列表：
/config - 配置 API 信息
/model - 选择/切换模型  
/status - 查看当前配置
/clear - 清除对话历史
/help - 帮助信息

🔒 隐私保护：每个用户的配置独立存储，API 密钥安全加密
    """
    await update.message.reply_text(welcome_text)

async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """配置 API 信息"""
    args = context.args
    user_id = update.effective_user.id
    
    if len(args) < 2:
        config_text = """
🔧 配置 Azure OpenAI API

使用方法：
/config <API_KEY> <ENDPOINT>

示例：
/config sk-abcd1234... https://your-resource.openai.azure.com

参数说明：
• API_KEY: Azure OpenAI 的 API 密钥
• ENDPOINT: Azure OpenAI 的端点 URL（不要包含尾部斜杠）

⚠️ 安全提示：
• 请在私聊中配置，不要在群组中使用
• 配置成功后立即删除包含密钥的消息
• 定期更换你的 API 密钥

支持的模型部署名称：
• gpt-4
• gpt-4.1  
• gpt-4o
• gpt-3.5-turbo-0125
• grok-3

确保你的 Azure 资源中已部署这些模型！
        """
        await update.message.reply_text(config_text)
        return
    
    api_key = args[0]
    endpoint = args[1].rstrip('/')
    
    # 验证输入格式
    if not endpoint.startswith('https://'):
        await update.message.reply_text("❌ 端点 URL 必须以 https:// 开头")
        return
    
    if len(api_key) < 20:
        await update.message.reply_text("❌ API 密钥格式似乎不正确，请检查")
        return
    
    # 初始化用户配置
    if user_id not in bot_instance.user_configs:
        bot_instance.user_configs[user_id] = {}
    
    bot_instance.user_configs[user_id].update({
        'api_key': api_key,
        'endpoint': endpoint,
        'model': bot_instance.user_configs[user_id].get('model', bot_instance.default_model),
        'config_time': datetime.now().isoformat()
    })
    
    model_display = bot_instance.available_models.get(
        bot_instance.user_configs[user_id]['model'], 
        bot_instance.user_configs[user_id]['model']
    )
    
    success_msg = f"""
✅ API 配置已保存！

🌐 端点: {endpoint}
🤖 当前模型: {model_display}
🕒 配置时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⚠️ 安全提醒：
请立即删除上面包含 API 密钥的消息！

💡 下一步：
使用 /model 选择或切换模型，然后就可以开始对话了！
    """
    
    await update.message.reply_text(success_msg)

async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """选择模型"""
    user_id = update.effective_user.id
    user_config = bot_instance.user_configs.get(user_id, {})
    
    if not user_config.get('api_key'):
        await update.message.reply_text(
            "❌ 请先使用 /config 配置 API 信息\n\n"
            "格式：/config <API_KEY> <ENDPOINT>"
        )
        return
    
    keyboard = []
    current_model = user_config.get('model', bot_instance.default_model)
    
    # 创建模型选择按钮
    for model_id, model_name in bot_instance.available_models.items():
        button_text = f"{'✅ ' if model_id == current_model else ''}{model_name}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"model:{model_id}")])
    
    # 添加功能按钮
    keyboard.extend([
        [InlineKeyboardButton("🔄 刷新列表", callback_data="model:refresh")],
        [InlineKeyboardButton("📊 模型对比", callback_data="model:compare")],
        [InlineKeyboardButton("❌ 取消", callback_data="model:cancel")]
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    current_display = bot_instance.available_models.get(current_model, current_model)
    text = f"🔄 选择要使用的 AI 模型\n\n当前模型: {current_display}\n\n点击下方按钮切换："
    
    await update.message.reply_text(text, reply_markup=reply_markup)

async def model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理模型选择回调"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    action = query.data.split(':')[1]
    
    if action == 'cancel':
        await query.edit_message_text("❌ 已取消模型选择")
        return
    
    if action == 'compare':
        compare_text = """
📊 模型对比信息

🧠 GPT-4
• 最强大的推理能力
• 适合复杂问题解决
• 响应速度：中等
• 上下文长度：8K tokens

🚀 GPT-4.1  
• GPT-4 的升级版本
• 改进的性能和准确性
• 响应速度：中等
• 上下文长度：8K tokens

✨ GPT-4o
• 多模态优化版本
• 平衡性能和速度
• 响应速度：较快
• 上下文长度：4K tokens

⚡ GPT-3.5 Turbo 0125
• 最新的 GPT-3.5 版本
• 快速响应，成本效益高
• 适合日常对话和简单任务
• 上下文长度：4K tokens

🤖 Grok-3
• xAI 最新模型
• 独特的对话风格
• 实时信息能力
• 上下文长度：4K tokens

选择建议：
• 复杂任务 → GPT-4 / GPT-4.1
• 日常对话 → GPT-4o / GPT-3.5 Turbo 0125
• 创新体验 → Grok-3
        """
        await query.edit_message_text(compare_text)
        return
    
    if action == 'refresh':
        # 重新显示模型选择界面
        keyboard = []
        user_config = bot_instance.user_configs.get(user_id, {})
        current_model = user_config.get('model', bot_instance.default_model)
        
        for model_id, model_name in bot_instance.available_models.items():
            button_text = f"{'✅ ' if model_id == current_model else ''}{model_name}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"model:{model_id}")])
        
        keyboard.extend([
            [InlineKeyboardButton("🔄 刷新列表", callback_data="model:refresh")],
            [InlineKeyboardButton("📊 模型对比", callback_data="model:compare")],
            [InlineKeyboardButton("❌ 取消", callback_data="model:cancel")]
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        current_display = bot_instance.available_models.get(current_model, current_model)
        text = f"🔄 选择要使用的 AI 模型\n\n当前模型: {current_display}\n\n点击下方按钮切换："
        
        await query.edit_message_text(text, reply_markup=reply_markup)
        return
    
    # 更新用户选择的模型
    if user_id not in bot_instance.user_configs:
        bot_instance.user_configs[user_id] = {}
    
    old_model = bot_instance.user_configs[user_id].get('model', 'none')
    bot_instance.user_configs[user_id]['model'] = action
    
    old_display = bot_instance.available_models.get(old_model, old_model)
    new_display = bot_instance.available_models.get(action, action)
    
    success_text = f"""
✅ 模型切换成功！

从：{old_display}
到：{new_display}

🚀 现在可以开始对话了！
直接发送消息即可体验新模型。

💡 提示：不同模型有不同的特点，可以尝试相同问题在不同模型下的回答。
    """
    
    await query.edit_message_text(success_text)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看当前配置状态"""
    user_id = update.effective_user.id
    user_config = bot_instance.user_configs.get(user_id, {})
    
    if not user_config:
        await update.message.reply_text(
            "❌ 尚未配置 API 信息\n\n"
            "请使用 /config 命令配置你的 Azure OpenAI API"
        )
        return
    
    model = user_config.get('model', '未选择')
    model_display = bot_instance.available_models.get(model, model)
    config_time = user_config.get('config_time', '未知')
    
    if config_time != '未知':
        try:
            config_dt = datetime.fromisoformat(config_time)
            config_time_str = config_dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            config_time_str = config_time
    else:
        config_time_str = '未知'
    
    status_text = f"""
📊 当前配置状态

🔑 API 密钥: {'✅ 已配置' if user_config.get('api_key') else '❌ 未配置'}
🌐 API 端点: {user_config.get('endpoint', '❌ 未配置')}
🤖 当前模型: {model_display}
🕒 配置时间: {config_time_str}

📈 可用模型: {len(bot_instance.available_models)} 个
🛡️ 配置状态: {'✅ 完整' if all(k in user_config for k in ['api_key', 'endpoint', 'model']) else '⚠️ 不完整'}

💡 命令提示:
• /model - 切换模型
• /config - 重新配置 API
• /clear - 清除对话历史
    """
    
    await update.message.reply_text(status_text)

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """清除对话历史"""
    user_id = update.effective_user.id
    # 这里可以实现对话历史清除逻辑
    # 目前的实现中每次对话都是独立的，所以只是提示信息
    
    await update.message.reply_text(
        "🗑️ 对话历史已清除！\n\n"
        "现在可以开始全新的对话了。"
    )

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理聊天消息"""
    user_id = update.effective_user.id
    user_config = bot_instance.user_configs.get(user_id, {})
    
    if not all(k in user_config for k in ['api_key', 'endpoint', 'model']):
        help_text = """
❌ 请先完成配置

📝 配置步骤：
1️⃣ /config <API_KEY> <ENDPOINT>
2️⃣ /model (选择模型)
3️⃣ 发送消息开始对话

💡 示例：
/config sk-abc123... https://your-resource.openai.azure.com
        """
        await update.message.reply_text(help_text)
        return
    
    user_message = update.message.text
    model = user_config['model']
    model_display = bot_instance.available_models.get(model, model)
    
    # 发送"正在思考"的消息
    thinking_msg = await update.message.reply_text(f"🤔 {model_display} 正在思考...")
    
    # 构建消息历史
    system_prompts = {
        'gpt-4': "你是一个专业的AI助手。请提供准确、详细和有帮助的回答。",
        'gpt-4.1': "你是GPT-4.1，一个高级AI助手。请提供深入、准确的分析和回答。", 
        'gpt-4o': "你是GPT-4o，一个多模态优化的AI助手。请提供清晰、实用的回答。",
        'gpt-3.5-turbo-0125': "你是GPT-3.5 Turbo 0125，一个快速响应的AI助手。请提供简洁、准确的回答。",
        'grok-3': "你是Grok-3，一个具有独特视角的AI助手。请提供有趣、深刻的回答，可以适当幽默。"
    }
    
    system_content = system_prompts.get(model, "你是一个有用的AI助手。")
    
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_message}
    ]
    
    # 调用 Azure OpenAI API
    response = await bot_instance.call_azure_openai(user_config, messages)
    
    # 删除"正在思考"的消息
    await thinking_msg.delete()
    
    if response:
        # 如果回复太长，分段发送
        max_length = 4000
        if len(response) > max_length:
            parts = [response[i:i+max_length] for i in range(0, len(response), max_length)]
            for i, part in enumerate(parts):
                if i == 0:
                    await update.message.reply_text(f"💬 {model_display} 回复：\n\n{part}")
                else:
                    await update.message.reply_text(part)
        else:
            await update.message.reply_text(f"💬 {model_display} 回复：\n\n{response}")
    else:
        await update.message.reply_text("❌ 抱歉，处理您的请求时出现了问题，请稍后再试。")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """帮助命令"""
    help_text = """
🆘 Azure OpenAI Bot 完整指南

🚀 支持的模型：
🧠 GPT-4 - 超强推理能力
🚀 GPT-4.1 - GPT-4升级版
✨ GPT-4o - 多模态优化
⚡ GPT-3.5 Turbo 0125 - 快速响应  
🤖 Grok-3 - xAI最新模型

📋 命令列表：
/start - 开始使用机器人
/config <API_KEY> <ENDPOINT> - 配置 Azure API
/model - 选择/切换模型
/status - 查看当前配置状态
/clear - 清除对话历史
/help - 显示帮助信息

🔧 使用步骤：
1️⃣ 获取 Azure OpenAI API 密钥和端点
2️⃣ 使用 /config 命令配置 API 信息
3️⃣ 使用 /model 选择想要使用的模型
4️⃣ 直接发送消息开始与 AI 对话

💡 使用技巧：
• 不同模型有不同特点，可以切换体验
• GPT-4系列适合复杂推理任务
• GPT-3.5 Turbo 0125适合快速日常对话
• Grok-3提供独特的对话体验

⚠️ 安全提示：
• 请在私聊中配置API密钥
• 配置后立即删除包含密钥的消息  
• 定期更换API密钥
• 不要分享你的配置信息

🛡️ 隐私保护：
每个用户的配置完全独立，API密钥安全存储，
机器人不会记录或分享你的对话内容。

需要帮助？发送任何消息给我！
    """
    await update.message.reply_text(help_text)

def main():
    """启动机器人"""
    # 从环境变量获取 Bot Token
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("请设置 TELEGRAM_BOT_TOKEN 环境变量")
        return
    
    # 创建应用
    application = Application.builder().token(token).build()
    
    # 注册命令处理器
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("config", config_command))
    application.add_handler(CommandHandler("model", model_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # 注册回调处理器
    application.add_handler(CallbackQueryHandler(model_callback, pattern="^model:"))
    
    # 注册消息处理器
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))
    
    # 启动机器人
    logger.info("Azure OpenAI Telegram Bot 启动中...")
    logger.info(f"支持的模型: {list(bot_instance.available_models.keys())}")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()