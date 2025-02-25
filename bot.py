import discord
from discord import app_commands
import google.generativeai as genai
import json
import os
import asyncio
import logging
from textblob import TextBlob  # Sentiment & Language Detection
from deep_translator import GoogleTranslator  # Language Translation

# Setup logging
logging.basicConfig(level=logging.INFO, filename="bot.log", filemode="a",
                    format="%(asctime)s - %(levelname)s - %(message)s")

# Load environment variables
DISCORD_BOT_TOKEN = "MTI1NDQ0MjU3MDQ1NzgwODk3Ng.GygWmr.NqYZeWLUB5zjR2Devs7T5FzqUjVfdrdNjT_45k"

# List of API keys
API_KEYS = ["AIzaSyDlIkK0bs5A3ZBvRmdHdun1aN9MOAgvOL0", "AIzaSyCD6h0NUP-4CdopViPcfPapN2s1smOwOFY"]
current_api_index = 0

# Configure Gemini API
def configure_gemini():
    global current_api_index
    if not API_KEYS:
        logging.error("No API keys available!")
        return
    genai.configure(api_key=API_KEYS[current_api_index])
    logging.info(f"✅ Using API Key {current_api_index + 1}")

# Rotate API Key Every 10 Minutes
async def rotate_api_key():
    global current_api_index
    while True:
        await asyncio.sleep(600)
        current_api_index = (current_api_index + 1) % len(API_KEYS)
        configure_gemini()

# Intents
intents = discord.Intents.default()
intents.message_content = True  
intents.dm_messages = True  
intents.guilds = True  
intents.reactions = True  

# Create bot
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# File paths
SETTINGS_FILE = "server_settings.json"
TRAINING_FILE = "ai_training.json"
USER_PERSONALITIES_FILE = "user_personalities.json"

# Load settings
def load_json(file):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return {}

# Save settings
def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)

# Get user personality (Overrides server AI personality)
def get_user_personality(user_id, server_id):
    user_personalities = load_json(USER_PERSONALITIES_FILE)
    return user_personalities.get(str(user_id), None) or f"Default AI Personality (Server {server_id})"

# Set user personality
def set_user_personality(user_id, description):
    user_personalities = load_json(USER_PERSONALITIES_FILE)
    user_personalities[str(user_id)] = description
    save_json(USER_PERSONALITIES_FILE, user_personalities)

# Detect message language
def detect_language(text):
    return TextBlob(text).detect_language()

# Translate AI response to match user’s language
def translate_response(response, target_language):
    if target_language == "en":  # Skip translation for English
        return response
    try:
        return GoogleTranslator(source="auto", target=target_language).translate(response)
    except Exception as e:
        logging.error(f"Translation failed: {e}")
        return response  # Return original response if translation fails

# AI Response Generation (Includes Auto-Training & Multi-Language)
def generate_gemini_response(prompt, user_id, server_id):
    global current_api_index
    model = genai.GenerativeModel("gemini-pro")

    personality = get_user_personality(user_id, server_id)

    # Sentiment Analysis
    sentiment = TextBlob(prompt).sentiment.polarity
    tone = "Positive" if sentiment > 0.2 else "Negative" if sentiment < -0.2 else "Neutral"

    # Detect Language
    user_language = detect_language(prompt)

    # Load AI Training Data
    training_data = load_json(TRAINING_FILE)
    past_responses = training_data.get(str(user_id), [])

    # Build AI Prompt
    full_prompt = f"AI Personality: {personality}\nSentiment: {tone}\nLanguage: {user_language}\nUser History:\n{past_responses}\nUser: {prompt}"

    try:
        response = model.generate_content(full_prompt, generation_config={"safety_settings": []})
        
        if response.text:
            # Store response for training
            training_data[str(user_id)] = (past_responses + [prompt + " → " + response.text])[-10:]
            save_json(TRAINING_FILE, training_data)

            # Translate AI response to match user language
            translated_response = translate_response(response.text, user_language)
            return translated_response

        return "I couldn't generate a response."
    
    except Exception as e:
        logging.error(f"API Key {current_api_index + 1} failed: {e}")
        current_api_index = (current_api_index + 1) % len(API_KEYS)
        configure_gemini()
        return "⚠️ API issue detected. Trying another key, please wait."

# Bot Ready
@bot.event
async def on_ready():
    logging.info(f'✅ Logged in as {bot.user}')
    await tree.sync()
    bot.loop.create_task(rotate_api_key())

# Slash Commands
@tree.command(name="setmypersonality", description="Set your own AI personality.")
async def setmypersonality(interaction: discord.Interaction, description: str):
    set_user_personality(interaction.user.id, description)
    await interaction.response.send_message(f"✅ Your AI personality has been updated!", ephemeral=True)

# AI Chat Handling (Auto-Training + Multi-Language)
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return  

    server_id = str(message.guild.id)

    # AI Toggle Check
    settings = load_json(SETTINGS_FILE)
    if not settings.get(server_id, {}).get("ai_enabled", True):
        return  

    response = generate_gemini_response(message.content, message.author.id, server_id)
    await message.channel.send(response)

# Run bot
bot.run(DISCORD_BOT_TOKEN)
