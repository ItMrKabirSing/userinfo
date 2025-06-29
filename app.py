# Flask API with Pyrogram Client for Telegram Information
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from pyrogram import Client
from pyrogram.enums import ParseMode, ChatType, UserStatus
from pyrogram.errors import PeerIdInvalid, UsernameNotOccupied, ChannelInvalid
from flask import Flask, request, jsonify
import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

# Telegram API credentials
API_ID = 28239710
API_HASH = "7fc5b35692454973318b86481ab5eca3"
BOT_TOKEN = "7941865929:AAEf7o5f-_VQKKWQKLs0qMOFHYwTi8Pjgwg"

# Flask app
app = Flask(__name__)

# Global variables for client and event loop
client = None
client_loop = None
client_thread = None

def get_dc_locations():
    """Returns a dictionary mapping Data Center IDs to their locations"""
    return {
        1: "MIA, Miami, USA, US",
        2: "AMS, Amsterdam, Netherlands, NL",
        3: "MBA, Mumbai, India, IN",
        4: "STO, Stockholm, Sweden, SE",
        5: "SIN, Singapore, SG",
        6: "LHR, London, United Kingdom, GB",
        7: "FRA, Frankfurt, Germany, DE",
        8: "JFK, New York, USA, US",
        9: "HKG, Hong Kong, HK",
        10: "TYO, Tokyo, Japan, JP",
        11: "SYD, Sydney, Australia, AU",
        12: "GRU, São Paulo, Brazil, BR",
        13: "DXB, Dubai, UAE, AE",
        14: "CDG, Paris, France, FR",
        15: "ICN, Seoul, South Korea, KR",
    }

def calculate_account_age(creation_date):
    """Calculate account age accurately"""
    today = datetime.now()
    delta = relativedelta(today, creation_date)
    years = delta.years
    months = delta.months
    days = delta.days
    return f"{years} years, {months} months, {days} days"

def estimate_account_creation_date(user_id):
    """Estimate account creation date based on user ID"""
    reference_points = [
        (100000000, datetime(2013, 8, 1)),  # Telegram's launch date
        (1273841502, datetime(2020, 8, 13)),  # Example reference point
        (1500000000, datetime(2021, 5, 1)),  # Another reference point
        (2000000000, datetime(2022, 12, 1)),  # Another reference point
    ]
    
    closest_point = min(reference_points, key=lambda x: abs(x[0] - user_id))
    closest_user_id, closest_date = closest_point
    
    id_difference = user_id - closest_user_id
    days_difference = id_difference / 20000000
    creation_date = closest_date + timedelta(days=days_difference)
    
    return creation_date

def format_user_status(status):
    """Format user status to readable string"""
    if not status:
        return "Unknown"
    
    if status == UserStatus.ONLINE:
        return "Online"
    elif status == UserStatus.OFFLINE:
        return "Offline"
    elif status == UserStatus.RECENTLY:
        return "Recently online"
    elif status == UserStatus.LAST_WEEK:
        return "Last seen within week"
    elif status == UserStatus.LAST_MONTH:
        return "Last seen within month"
    else:
        return "Unknown"

async def get_user_info(username):
    """Get user or bot information"""
    try:
        DC_LOCATIONS = get_dc_locations()
        user = await client.get_users(username)
        
        premium_status = user.is_premium if hasattr(user, 'is_premium') else False
        dc_location = DC_LOCATIONS.get(user.dc_id, "Unknown")
        account_created = estimate_account_creation_date(user.id)
        account_created_str = account_created.strftime("%B %d, %Y")
        account_age = calculate_account_age(account_created)
        verified_status = getattr(user, 'is_verified', False)
        status = format_user_status(getattr(user, 'status', None))
        
        # Determine flags
        flags = "Clean"
        if getattr(user, 'is_scam', False):
            flags = "Scam"
        elif getattr(user, 'is_fake', False):
            flags = "Fake"
        
        user_data = {
            "success": True,
            "type": "bot" if user.is_bot else "user",
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
            "dc_id": user.dc_id,
            "dc_location": dc_location,
            "is_premium": premium_status,
            "is_verified": verified_status,
            "is_bot": user.is_bot,
            "flags": flags,
            "status": status,
            "account_created": account_created_str,
            "account_age": account_age,
            "links": {
                "android": f"tg://openmessage?user_id={user.id}",
                "ios": f"tg://user?id={user.id}",
                "permanent": f"tg://user?id={user.id}"
            }
        }
        
        return user_data
        
    except (PeerIdInvalid, UsernameNotOccupied, IndexError):
        return {"success": False, "error": "User not found"}
    except Exception as e:
        LOGGER.error(f"Error fetching user info: {str(e)}")
        return {"success": False, "error": "Failed to fetch user information"}

async def get_chat_info(username):
    """Get chat (group/channel) information"""
    try:
        DC_LOCATIONS = get_dc_locations()
        chat = await client.get_chat(username)
        
        chat_type = "unknown"
        if chat.type == ChatType.SUPERGROUP:
            chat_type = "supergroup"
        elif chat.type == ChatType.GROUP:
            chat_type = "group"
        elif chat.type == ChatType.CHANNEL:
            chat_type = "channel"
        
        dc_location = DC_LOCATIONS.get(chat.dc_id, "Unknown")
        
        chat_data = {
            "success": True,
            "type": chat_type,
            "id": chat.id,
            "title": chat.title,
            "username": chat.username,
            "dc_id": chat.dc_id,
            "dc_location": dc_location,
            "members_count": chat.members_count,
            "description": getattr(chat, 'description', None),
            "links": {
                "join": f"t.me/c/{str(chat.id).replace('-100', '')}/100" if chat.id < 0 else f"t.me/{chat.username}",
                "permanent": f"t.me/c/{str(chat.id).replace('-100', '')}/100" if chat.id < 0 else f"t.me/{chat.username}"
            }
        }
        
        return chat_data
        
    except (ChannelInvalid, PeerIdInvalid):
        return {"success": False, "error": "Chat not found or access denied"}
    except Exception as e:
        LOGGER.error(f"Error fetching chat info: {str(e)}")
        return {"success": False, "error": "Failed to fetch chat information"}

async def get_telegram_info(username):
    """Get information for any Telegram entity (user, bot, group, channel)"""
    # Clean the username
    username = username.strip('@').replace('https://', '').replace('http://', '').replace('t.me/', '').replace('/', '').replace(':', '')
    
    LOGGER.info(f"Fetching info for: {username}")
    
    # Try to get user/bot info first
    user_info = await get_user_info(username)
    if user_info["success"]:
        return user_info
    
    # If user not found, try to get chat info
    chat_info = await get_chat_info(username)
    if chat_info["success"]:
        return chat_info
    
    # If both failed
    return {"success": False, "error": "Entity not found or access denied"}

def run_async_in_client_loop(coro):
    """Run async function in the client's event loop"""
    future = asyncio.run_coroutine_threadsafe(coro, client_loop)
    return future.result(timeout=30)  # 30 second timeout

@app.route('/info', methods=['GET'])
def info_endpoint():
    """API endpoint to get Telegram entity information"""
    username = request.args.get('username')
    
    if not username:
        return jsonify({
            "success": False,
            "error": "Username parameter is required"
        }), 400
    
    try:
        # Run the async function in the client's event loop
        result = run_async_in_client_loop(get_telegram_info(username))
        
        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 404
            
    except Exception as e:
        LOGGER.error(f"API error: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Internal server error"
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "success": True,
        "status": "API is running",
        "bot_status": "connected" if client and client.is_connected else "disconnected"
    })

@app.route('/', methods=['GET'])
def root():
    """Root endpoint with API documentation"""
    return jsonify({
        "success": True,
        "message": "Telegram Info API",
        "endpoints": {
            "/info": "GET - Get telegram entity info (requires 'username' parameter)",
            "/health": "GET - Health check",
            "/": "GET - This documentation"
        },
        "usage": {
            "example": "/info?username=telegram",
            "supported": [
                "Usernames (@username or username)",
                "User IDs",
                "Channel usernames",
                "Group usernames",
                "Bot usernames",
                "Telegram links (t.me/username)"
            ]
        }
    })

async def run_client():
    """Run the Pyrogram client"""
    global client, client_loop
    client_loop = asyncio.get_event_loop()
    
    LOGGER.info("Creating Bot Client From BOT_TOKEN")
    client = Client(
        "GetUserInfo",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN
    )
    LOGGER.info("Bot Client Created Successfully!")
    
    await client.start()
    LOGGER.info("Pyrogram client started successfully!")
    
    # Keep the client running
    try:
        await client.idle()
    except KeyboardInterrupt:
        LOGGER.info("Received interrupt signal")
    finally:
        await client.stop()
        LOGGER.info("Pyrogram client stopped!")

def start_client():
    """Start the client in a separate thread"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_client())

if __name__ == '__main__':
    # Start the Pyrogram client in a separate thread
    client_thread = threading.Thread(target=start_client, daemon=True)
    client_thread.start()
    
    # Wait a bit for client to initialize
    import time
    time.sleep(5)
    
    try:
        # Run Flask app
        LOGGER.info("Starting Flask API server...")
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        LOGGER.info("Shutting down...")
    finally:
        if client:
            # Send stop signal to client
            if client_loop and not client_loop.is_closed():
                asyncio.run_coroutine_threadsafe(client.stop(), client_loop)
