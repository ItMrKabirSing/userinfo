# FastAPI + Pyrogram Telegram Info API
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from pyrogram import Client
from pyrogram.enums import ParseMode, ChatType, UserStatus
from pyrogram.errors import PeerIdInvalid, UsernameNotOccupied, ChannelInvalid
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import asyncio
import logging
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

# Telegram API credentials
API_ID = 28239710
API_HASH = "7fc5b35692454973318b86481ab5eca3"
BOT_TOKEN = "7941865929:AAEf7o5f-_VQKKWQKLs0qMOFHYwTi8Pjgwg"

# Global client variable
client = None

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

def format_user_status(status):
    """Format user status to readable string"""
    if not status:
        return "Unknown"
    
    status_map = {
        UserStatus.ONLINE: "Online",
        UserStatus.OFFLINE: "Offline",
        UserStatus.RECENTLY: "Recently online",
        UserStatus.LAST_WEEK: "Last seen within week",
        UserStatus.LAST_MONTH: "Last seen within month"
    }
    return status_map.get(status, "Unknown")

async def get_user_info(username):
    """Get user or bot information"""
    try:
        DC_LOCATIONS = get_dc_locations()
        user = await client.get_users(username)
        
        premium_status = getattr(user, 'is_premium', False)
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
        return {"success": False, "error": f"Failed to fetch user information: {str(e)}"}

async def get_chat_info(username):
    """Get chat (group/channel) information"""
    try:
        DC_LOCATIONS = get_dc_locations()
        chat = await client.get_chat(username)
        
        chat_type_map = {
            ChatType.SUPERGROUP: "supergroup",
            ChatType.GROUP: "group",
            ChatType.CHANNEL: "channel"
        }
        chat_type = chat_type_map.get(chat.type, "unknown")
        
        dc_location = DC_LOCATIONS.get(getattr(chat, 'dc_id', None), "Unknown")
        
        # Generate appropriate links
        if chat.username:
            join_link = f"t.me/{chat.username}"
            permanent_link = f"t.me/{chat.username}"
        elif chat.id < 0:
            chat_id_str = str(chat.id).replace('-100', '')
            join_link = f"t.me/c/{chat_id_str}/1"
            permanent_link = f"t.me/c/{chat_id_str}/1"
        else:
            join_link = f"tg://resolve?domain={chat.id}"
            permanent_link = f"tg://resolve?domain={chat.id}"
        
        chat_data = {
            "success": True,
            "type": chat_type,
            "id": chat.id,
            "title": chat.title,
            "username": chat.username,
            "dc_id": getattr(chat, 'dc_id', None),
            "dc_location": dc_location,
            "members_count": getattr(chat, 'members_count', None),
            "description": getattr(chat, 'description', None),
            "links": {
                "join": join_link,
                "permanent": permanent_link
            }
        }
        
        return chat_data
        
    except (ChannelInvalid, PeerIdInvalid):
        return {"success": False, "error": "Chat not found or access denied"}
    except Exception as e:
        LOGGER.error(f"Error fetching chat info: {str(e)}")
        return {"success": False, "error": f"Failed to fetch chat information: {str(e)}"}

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the lifespan of the FastAPI app"""
    global client
    
    # Startup
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
    
    yield
    
    # Shutdown
    if client:
        await client.stop()
        LOGGER.info("Pyrogram client stopped!")

# Create FastAPI app with lifespan
app = FastAPI(
    title="Telegram Info API",
    description="Get information about Telegram users, bots, channels, and groups",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/info")
async def info_endpoint(username: str = Query(..., description="Username, user ID, or Telegram link")):
    """API endpoint to get Telegram entity information"""
    try:
        result = await get_telegram_info(username)
        
        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=404, detail=result["error"])
            
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"API error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "success": True,
        "status": "API is running",
        "bot_status": "connected" if client and client.is_connected else "disconnected"
    }

@app.get("/")
async def root():
    """Root endpoint with API documentation"""
    return {
        "success": True,
        "message": "Telegram Info API",
        "endpoints": {
            "/info": "GET - Get telegram entity info (requires 'username' parameter)",
            "/health": "GET - Health check",
            "/": "GET - This documentation",
            "/docs": "GET - Interactive API documentation",
            "/redoc": "GET - Alternative API documentation"
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
    }

if __name__ == "__main__":
    import uvicorn
    LOGGER.info("Starting FastAPI server with Uvicorn...")
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=5000,
        log_level="info",
        reload=False
    )
