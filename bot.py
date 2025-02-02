import os
import telebot
from tavily import TavilyClient
import google.generativeai as genai
import requests
from dotenv import load_dotenv
from telebot import types
import traceback
import json
from datetime import datetime

# Load environment variables first
load_dotenv()
print("✅ [INIT] Environment variables loaded")

# Configuration with validation
try:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    HF_API_TOKEN = os.getenv("HF_API_TOKEN")
    
    if not all([TELEGRAM_TOKEN, TAVILY_API_KEY, GEMINI_API_KEY, HF_API_TOKEN]):
        raise ValueError("Missing one or more required environment variables")
        
    print("🔑 [INIT] Environment variables validated successfully")
    print(f"  Telegram Token: {'****' + TELEGRAM_TOKEN[-4:] if TELEGRAM_TOKEN else 'MISSING'}")
    print(f"  Tavily Key: {'****' + TAVILY_API_KEY[-4:] if TAVILY_API_KEY else 'MISSING'}")
    print(f"  Gemini Key: {'****' + GEMINI_API_KEY[-4:] if GEMINI_API_KEY else 'MISSING'}")
    print(f"  HF Token: {'****' + HF_API_TOKEN[-4:] if HF_API_TOKEN else 'MISSING'}")

except Exception as e:
    print(f"❌ [INIT] Configuration error: {str(e)}")
    exit(1)

# Initialize bot
try:
    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    print("🤖 [INIT] Telegram bot initialized successfully")
except Exception as e:
    print(f"❌ [INIT] Failed to initialize Telegram bot: {str(e)}")
    exit(1)

user_sessions = {}

# Initialize APIs
try:
    tavily = TavilyClient(api_key=TAVILY_API_KEY)
    genai.configure(api_key=GEMINI_API_KEY)
    gemini = genai.GenerativeModel('gemini-pro')
    print("🌐 [INIT] API clients initialized successfully")
except Exception as e:
    print(f"❌ [INIT] API initialization failed: {str(e)}")
    exit(1)

def generate_image(prompt):
    print(f"\n🖼️ [IMAGE] Generation started at {datetime.now().isoformat()}")
    API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
    headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
    
    try:
        print(f"🖼️ [IMAGE] Sending request with prompt: {prompt[:100]}...")
        start_time = datetime.now()
        response = requests.post(API_URL, headers=headers, json={"inputs": prompt}, timeout=120)
        duration = (datetime.now() - start_time).total_seconds()
        
        print(f"🖼️ [IMAGE] Response received in {duration:.2f}s | Status: {response.status_code}")
        
        if response.status_code == 200:
            print(f"✅ [IMAGE] Successfully generated image ({len(response.content)} bytes)")
            return response.content
        else:
            print(f"❌ [IMAGE] Generation failed: {response.text[:200]}...")
            return None
    except Exception as e:
        print(f"❌ [IMAGE] Error during generation: {str(e)}")
        return None

@bot.message_handler(commands=['search'])
def handle_search(message):
    print(f"\n🔍 [SEARCH] New request at {datetime.now().isoformat()}")
    try:
        query = message.text.split(' ', 1)[1].strip()
        chat_id = message.chat.id
        print(f"🧑 [USER] {chat_id} | Query: '{query}'")

        # Show searching status
        msg = bot.send_message(chat_id, "🔍 Searching the web...")
        print("🌐 [SEARCH] Initiating Tavily search...")

        try:
            start_time = datetime.now()
            search_response = tavily.search(query=query, search_depth="advanced")
            duration = (datetime.now() - start_time).total_seconds()
            
            print(f"🌐 [SEARCH] Completed in {duration:.2f}s | Response keys: {list(search_response.keys())}")
            
            results = search_response.get('results', [])[:25]
            print(f"🌐 [SEARCH] Found {len(results)} results")
            
            if not results:
                print("⚠️ [SEARCH] No results found")
                bot.reply_to(message, "⚠️ No relevant results found. Try a different query.")
                return
                
            # Log first result structure
            print("🌐 [SEARCH] First result metadata:")
            print(json.dumps({k: v for k, v in results[0].items() if k != 'content'}, indent=2)[:300] + "...")
            print(f"📄 [SEARCH] First result content length: {len(results[0].get('content', ''))} chars")

        except Exception as e:
            print(f"❌ [SEARCH] Tavily error: {str(e)}")
            bot.reply_to(message, "⚠️ Search failed. Please try again later.")
            return

        # Store results in user session
        user_sessions[chat_id] = {
            'results': results,
            'search_query': query,
            'timestamp': datetime.now().isoformat()
        }
        print(f"💾 [SESSION] Stored session for {chat_id}")

        # Create buttons for web results
        markup = types.InlineKeyboardMarkup()
        for idx, result in enumerate(results):
            btn_text = f"🌐 {result.get('title', 'No Title')[:20]}..."
            url = result.get('url', '')
            markup.add(types.InlineKeyboardButton(text=btn_text, url=url))
            print(f"🔗 [RESULT {idx}] {btn_text} | URL: {url[:50]}...")

        markup.add(types.InlineKeyboardButton(
            text="✅ Generate Content",
            callback_data="generate_content"
        ))

        print("🔄 [UI] Updating message with results...")
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg.message_id,
            text="*Web Search Results:*\n" + "\n\n".join(
                [f"• [{res['title']}]({res['url']})" for res in results]
            ),
            parse_mode='Markdown',
            reply_markup=markup
        )
        print("✅ [SEARCH] Flow completed successfully")

    except IndexError:
        error_msg = "⚠️ Please provide a search query. Usage: /search [your query]"
        print(error_msg)
        bot.reply_to(message, error_msg)
    except Exception as e:
        error_msg = f"⚠️ Critical error: {str(e)}"
        print(f"❌ [SEARCH] {error_msg}")
        print(traceback.format_exc())
        bot.reply_to(message, "⚠️ An unexpected error occurred. Please try again.")

@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    print(f"\n🔄 [CALLBACK] Received: {call.data} at {datetime.now().isoformat()}")
    try:
        chat_id = call.message.chat.id
        print(f"🧑 [USER] {chat_id} | Message ID: {call.message.message_id}")
        
        # Session validation
        if chat_id not in user_sessions:
            print(f"❌ [SESSION] No session found for {chat_id}")
            bot.answer_callback_query(call.id, "❌ Session expired. Start a new search.")
            return
            
        session = user_sessions[chat_id]
        print(f"💾 [SESSION] Last updated: {session.get('timestamp', 'unknown')}")

        if call.data == 'generate_content':
            print("📝 [CONTENT] Starting generation process...")
            
            # Add platform selection
            markup = types.InlineKeyboardMarkup()
            markup.row(
                types.InlineKeyboardButton("🐦 Twitter", callback_data="platform_twitter"),
                types.InlineKeyboardButton("📸 Instagram", callback_data="platform_instagram"),
                types.InlineKeyboardButton("🔗 LinkedIn", callback_data="platform_linkedin")
            )
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text="Select the platform for which you want to generate content:",
                reply_markup=markup
                )
   
            elif call.data.startswith('platform_'):
            platform = call.data.split('_')[1]
            print(f"📱 [PLATFORM] Selected: {platform}")
            
            if 'results' not in session or not session['results']:
                print(f"❌ [CONTENT] Missing results in session")
                bot.answer_callback_query(call.id, "❌ Missing data. Start new search.")
                return
                
            results = session['results']
            print(f"📚 [CONTENT] Processing {len(results)} results")
            
            # Build context
            context = "\n\n".join([f"Source {i+1}:\n{res.get('content', '')}" for i, res in enumerate(results)])
            print(f"📄 [CONTENT] Context length: {len(context)} characters")
            
            # Create enhanced prompt
            prompt = f"""Create engaging social media content based on these research findings:
            
            {context[:5000]}
            
            Format for these platforms:
            1. Twitter: 280-character post with 3 relevant hashtags
            2. Instagram: Caption under 2200 chars with 5 emojis
            3. LinkedIn: Professional post under 3000 chars with key insights
            
            Structure with clear platform headings. Ensure factual accuracy."""
            
            print(f"📝 [GEMINI] Sending prompt ({len(prompt)} chars):\n{prompt[:300]}...")
            
            try:
                start_time = datetime.now()
                response = gemini.generate_content(prompt)
                duration = (datetime.now() - start_time).total_seconds()
                
                print(f"✅ [GEMINI] Response received in {duration:.2f}s")
                
                if not response.text:
                    print("❌ [GEMINI] Empty response received")
                    raise ValueError("Empty response from Gemini")
                    
                print(f"📄 [CONTENT] Generated text ({len(response.text)} chars):\n{response.text[:300]}...")
                
                # Store generated content
                session['content'] = response.text
                session['timestamp'] = datetime.now().isoformat()
                
                # Prepare buttons
                markup = types.InlineKeyboardMarkup()
                markup.row(
                    types.InlineKeyboardButton("🔄 Regenerate", callback_data="regenerate"),
                    types.InlineKeyboardButton("📤 Post", callback_data="post_content")
                )
                
                # Update message
                try:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=call.message.message_id,
                        text=f"*Generated Content:*\n\n{response.text}",
                        parse_mode='Markdown',
                        reply_markup=markup
                    )
                    print("✅ [CONTENT] Message updated successfully")
                except Exception as e:
                    print(f"❌ [TELEGRAM] Message edit failed: {str(e)}")
                    bot.answer_callback_query(call.id, "⚠️ Message too long. Try a different query.")
                    
            except Exception as e:
                print(f"❌ [GEMINI] Error: {str(e)}")
                bot.answer_callback_query(call.id, "⚠️ Content generation failed")
                raise

        elif call.data == 'create_thumbnail':
            print("🖼️ [THUMBNAIL] Starting creation process...")
            
            # Add image generation options
            markup = types.InlineKeyboardMarkup()
            markup.row(
                types.InlineKeyboardButton("🖼️ Default Prompt", callback_data="default_prompt"),
                types.InlineKeyboardButton("🖼️ Custom Prompt", callback_data="custom_prompt")
            )
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text="Choose an option for image generation:",
                reply_markup=markup
            )
            return
            
            if 'content' not in session or not session['content']:
                print(f"❌ [THUMBNAIL] Missing content in session")
                bot.answer_callback_query(call.id, "❌ No content available")
                return
                
            content = session['content']
            print(f"📄 [THUMBNAIL] Using content: {content[:100]}...")
            
            # Generate image prompt
            image_prompt = f"Social media thumbnail image for: {content[:500]}"
            print(f"🖼️ [THUMBNAIL] Image prompt: {image_prompt[:200]}...")
            
            image_data = generate_image(image_prompt)
            
            if image_data:
                try:
                    # Prepare buttons
                    markup = types.InlineKeyboardMarkup()
                    markup.row(
                        types.InlineKeyboardButton("🐦 Twitter", url="https://twitter.com/intent/tweet"),
                        types.InlineKeyboardButton("📸 Instagram", url="https://www.instagram.com/")
                    )
                    
                    # Send image
                    bot.send_photo(
                        chat_id,
                        photo=image_data,
                        caption="*Your post is ready!*",
                        parse_mode='Markdown',
                        reply_markup=markup
                    )
                    print("✅ [THUMBNAIL] Image sent successfully")
                except Exception as e:
                    print(f"❌ [TELEGRAM] Failed to send photo: {str(e)}")
                    bot.answer_callback_query(call.id, "⚠️ Failed to send image")
            else:
                print("❌ [THUMBNAIL] No image data received")
                bot.answer_callback_query(call.id, "⚠️ Image generation failed")

        elif call.data == 'regenerate':
            print("\n🔄 [REGENERATE] Starting regeneration process...")
            
            if 'results' not in session or not session['results']:
                print(f"❌ [REGENERATE] Missing results in session")
                bot.answer_callback_query(call.id, "❌ Missing data. Start new search.")
                return
                
            results = session['results']
            print(f"📚 [REGENERATE] Reprocessing {len(results)} results")
            
            # Build context with different prompt
            context = "\n\n".join([f"Source {i+1}:\n{res.get('content', '')}" for i, res in enumerate(results)])
            print(f"📄 [REGENERATE] Context length: {len(context)} characters")
            
            # Create alternate prompt
            prompt = f"""Regenerate the social media content with a different style:
            
            Original context:
            {context[:5000]}
            
            Requirements:
            - More casual/informal tone
            - Use different emojis/hashtags
            - Alternative structure
            - Keep platform-specific formatting"""
            
            print(f"📝 [REGENERATE] Sending new prompt ({len(prompt)} chars):\n{prompt[:300]}...")
            
            try:
                start_time = datetime.now()
                response = gemini.generate_content(prompt)
                duration = (datetime.now() - start_time).total_seconds()
                
                print(f"✅ [REGENERATE] Response received in {duration:.2f}s")
                
                if not response.text:
                    print("❌ [REGENERATE] Empty response received")
                    raise ValueError("Empty regeneration response from Gemini")
                    
                print(f"📄 [REGENERATE] New text ({len(response.text)} chars):\n{response.text[:300]}...")
                
                # Update stored content
                session['content'] = response.text
                session['timestamp'] = datetime.now().isoformat()
                
                # Prepare buttons
                markup = types.InlineKeyboardMarkup()
                markup.row(
                    types.InlineKeyboardButton("🔄 Regenerate", callback_data="regenerate"),
                    types.InlineKeyboardButton("📤 Post", callback_data="create_thumbnail")
                )
                
                # Update message
                try:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=call.message.message_id,
                        text=f"*Revised Content:*\n\n{response.text}",
                        parse_mode='Markdown',
                        reply_markup=markup
                    )
                    print("✅ [REGENERATE] Message updated successfully")
                except Exception as e:
                    print(f"❌ [REGENERATE] Message edit failed: {str(e)}")
                    bot.answer_callback_query(call.id, "⚠️ Regenerated content too long")
                    
            except Exception as e:
                print(f"❌ [REGENERATE] Error: {str(e)}")
                bot.answer_callback_query(call.id, "⚠️ Regeneration failed")
                raise

        else:
            print(f"⚠️ [CALLBACK] Unknown command: {call.data}")
            bot.answer_callback_query(call.id, "⚠️ Unknown command")
            
    except Exception as e:
        print(f"❌ [CALLBACK] Critical error: {str(e)}")
        print(traceback.format_exc())
        bot.answer_callback_query(call.id, "⚠️ An error occurred")

if __name__ == "__main__":
    print("\n🚀 [MAIN] Starting bot polling...")
    try:
        bot.polling(none_stop=True, interval=2, timeout=60)
        print("🤖 [MAIN] Bot is running")
    except Exception as e:
        print(f"❌ [MAIN] Polling failed: {str(e)}")
        print(traceback.format_exc())