from flask import Flask, request, jsonify
from pyrogram import Client
from pyrogram.errors import PeerIdInvalid, UsernameNotOccupied, ChannelInvalid
from pyrogram.enums import ChatType
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from config import API_ID, API_HASH, BOT_TOKEN
import logging
import os
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
import functools

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables
bot = None
loop = None
executor = ThreadPoolExecutor(max_workers=4)

def run_async_in_thread(coro):
    """Run async function in a separate thread with its own event loop"""
    def run_in_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    
    future = executor.submit(run_in_loop)
    return future.result()

def async_route(f):
    """Decorator to handle async functions in Flask routes"""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        try:
            coro = f(*args, **kwargs)
            return run_async_in_thread(coro)
        except Exception as e:
            logger.error(f"Error in async route: {str(e)}")
            return jsonify({
                "success": False,
                "error": "Internal server error"
            }), 500
    return wrapper

async def get_bot_client():
    """Get or create bot client instance"""
    global bot
    if bot is None:
        bot = Client(
            name="info_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workdir="/tmp"
        )
        await bot.start()
        logger.info("Bot client started successfully")
    return bot

def get_dc_locations():
    """Get data center locations mapping"""
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
    """Calculate account age from creation date"""
    today = datetime.now()
    delta = relativedelta(today, creation_date)
    years = delta.years
    months = delta.months
    days = delta.days
    return f"{years} years, {months} months, {days} days"

def estimate_account_creation_date(user_id):
    """Estimate account creation date based on user ID"""
    reference_points = [
        (100000000, datetime(2013, 8, 1)),
        (1273841502, datetime(2020, 8, 13)),
        (1500000000, datetime(2021, 5, 1)),
        (2000000000, datetime(2022, 12, 1)),
    ]
    closest_point = min(reference_points, key=lambda x: abs(x[0] - user_id))
    closest_user_id, closest_date = closest_point
    id_difference = user_id - closest_user_id
    days_difference = id_difference / 20000000
    creation_date = closest_date + timedelta(days=days_difference)
    return creation_date

def map_user_status(status):
    """Map user status to readable format"""
    if not status:
        return "Unknown"
    status_str = str(status).upper()
    if "ONLINE" in status_str:
        return "Online"
    elif "OFFLINE" in status_str:
        return "Offline"
    elif "RECENTLY" in status_str:
        return "Recently online"
    elif "LAST_WEEK" in status_str:
        return "Last seen within week"
    elif "LAST_MONTH" in status_str:
        return "Last seen within month"
    return "Unknown"

def clean_username(username):
    """Clean and normalize username"""
    if not username:
        return None
    
    # Remove common prefixes and clean up
    username = username.strip()
    username = username.replace('https://', '').replace('http://', '')
    username = username.replace('t.me/', '').replace('telegram.me/', '')
    username = username.strip('@').strip('/').strip(':')
    
    return username

@app.route('/')
def welcome():
    """Welcome endpoint with API documentation"""
    return jsonify({
        "message": "Welcome to the SmartDevs Info API!",
        "status": "active",
        "usage": {
            "endpoint": "/info",
            "query_param": "username",
            "description": "Retrieve information about a Telegram user, bot, group, or channel.",
            "examples": [
                "/info?username=TestUser",
                "/info?username=@TestUser",
                "/info?username=t.me/TestUser",
                "/info?username=https://t.me/TestUser"
            ],
            "response": "JSON object containing entity details (user/bot/channel/group info, account age, data center, etc.)"
        },
        "note": "Ensure valid Telegram credentials are set in config.py."
    })

@app.route('/info')
@async_route
async def get_info():
    """Main endpoint to get Telegram entity information"""
    username = request.args.get('username')
    if not username:
        return jsonify({"error": "Username parameter is required"}), 400

    # Clean and validate username
    username = clean_username(username)
    if not username:
        return jsonify({"error": "Invalid username format"}), 400

    logger.info(f"Fetching info for: {username}")

    try:
        # Get bot client
        client = await get_bot_client()
        DC_LOCATIONS = get_dc_locations()

        # First try to get as user/bot
        try:
            user = await client.get_users(username)
            logger.info(f"User/bot found: {username}")
            
            # Extract user information
            premium_status = "Yes" if getattr(user, 'is_premium', False) else "No"
            dc_location = DC_LOCATIONS.get(user.dc_id, "Unknown")
            account_created = estimate_account_creation_date(user.id)
            account_created_str = account_created.strftime("%B %d, %Y")
            account_age = calculate_account_age(account_created)
            verified_status = "Yes" if getattr(user, 'is_verified', False) else "No"
            status = map_user_status(getattr(user, 'status', None))
            
            # Check flags
            flags = []
            if getattr(user, 'is_scam', False):
                flags.append("Scam")
            if getattr(user, 'is_fake', False):
                flags.append("Fake")
            flags_str = ", ".join(flags) if flags else "Clean"

            # Build full name
            full_name_parts = []
            if user.first_name:
                full_name_parts.append(user.first_name)
            if user.last_name:
                full_name_parts.append(user.last_name)
            full_name = " ".join(full_name_parts) if full_name_parts else "Unknown"

            return jsonify({
                "success": True,
                "type": "bot" if user.is_bot else "user",
                "full_name": full_name,
                "id": user.id,
                "username": f"@{user.username}" if user.username else "None",
                "context_id": user.id,
                "data_center": f"{user.dc_id} ({dc_location})" if user.dc_id else "Unknown",
                "premium": premium_status,
                "verified": verified_status,
                "flags": flags_str,
                "status": status,
                "account_created_on": account_created_str,
                "account_age": account_age
            })

        except (PeerIdInvalid, UsernameNotOccupied):
            logger.info(f"Username '{username}' not found as user/bot. Checking for chat...")
            
            # Try to get as chat (group/channel)
            try:
                chat = await client.get_chat(username)
                logger.info(f"Chat found: {username}")
                
                dc_location = DC_LOCATIONS.get(chat.dc_id, "Unknown")
                
                # Map chat type
                chat_type_map = {
                    ChatType.SUPERGROUP: "Supergroup",
                    ChatType.GROUP: "Group",
                    ChatType.CHANNEL: "Channel"
                }
                chat_type = chat_type_map.get(chat.type, "Unknown")

                return jsonify({
                    "success": True,
                    "type": chat_type.lower(),
                    "title": chat.title or "Unknown",
                    "id": chat.id,
                    "type_description": chat_type,
                    "member_count": chat.members_count if hasattr(chat, 'members_count') and chat.members_count else "Unknown",
                    "data_center": f"{chat.dc_id} ({dc_location})" if chat.dc_id else "Unknown",
                    "username": f"@{chat.username}" if hasattr(chat, 'username') and chat.username else "None",
                    "description": chat.description if hasattr(chat, 'description') and chat.description else "None"
                })

            except UsernameNotOccupied:
                logger.error(f"Username '{username}' does not exist")
                return jsonify({
                    "success": False,
                    "error": f"Username '@{username}' does not exist"
                }), 404
                
            except (ChannelInvalid, PeerIdInvalid):
                error_message = "Bot lacks permission to access this channel or group"
                logger.error(f"Permission error for '{username}': {error_message}")
                return jsonify({
                    "success": False,
                    "error": error_message
                }), 403
                
            except Exception as chat_error:
                logger.error(f"Error fetching chat info for '{username}': {str(chat_error)}")
                return jsonify({
                    "success": False,
                    "error": f"Failed to fetch chat info: {str(chat_error)}"
                }), 500

        except Exception as user_error:
            logger.error(f"Error fetching user info for '{username}': {str(user_error)}")
            return jsonify({
                "success": False,
                "error": f"Failed to fetch user info: {str(user_error)}"
            }), 500

    except Exception as e:
        logger.error(f"Unhandled exception for '{username}': {str(e)}")
        return jsonify({
            "success": False,
            "error": "Internal Server Error"
        }), 500

@app.route('/health')
@async_route
async def health_check():
    """Health check endpoint"""
    try:
        client = await get_bot_client()
        return jsonify({
            "status": "healthy",
            "bot_connected": client.is_connected if client else False,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        "success": False,
        "error": "Endpoint not found"
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({
        "success": False,
        "error": "Internal server error"
    }), 500

# Initialize bot on startup
def init_bot():
    """Initialize bot in a separate thread"""
    try:
        run_async_in_thread(get_bot_client())
        logger.info("Bot initialization completed")
    except Exception as e:
        logger.error(f"Failed to initialize bot: {e}")

# Start bot initialization in background
init_thread = threading.Thread(target=init_bot, daemon=True)
init_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
