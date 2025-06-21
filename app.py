from fastapi import FastAPI, Query, HTTPException
from pyrogram import Client
from pyrogram.errors import PeerIdInvalid, UsernameNotOccupied, ChannelInvalid
from pyrogram.enums import ChatType
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from config import API_ID, API_HASH, BOT_TOKEN
import logging
import os
import asyncio
import uvicorn

app = FastAPI()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Pyrogram client setup
session_path = os.path.join('/tmp', 'info_bot.session')
bot = Client(
    name="info_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workdir="/tmp"
)

# Start bot asynchronously
async def start_bot():
    try:
        await bot.start()
        logger.info("Pyrogram bot started successfully")
    except Exception as e:
        logger.error(f"Failed to start Pyrogram bot: {str(e)}")
        raise

# Initialize bot at startup
@app.on_event("startup")
async def startup_event():
    try:
        await start_bot()
    except Exception as e:
        logger.error(f"Bot initialization failed: {str(e)}")
        raise

def get_dc_locations():
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
    today = datetime.now()
    delta = relativedelta(today, creation_date)
    years = delta.years
    months = delta.months
    days = delta.days
    return f"{years} years, {months} months, {days} days"

def estimate_account_creation_date(user_id):
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

@app.get("/")
async def welcome():
    return {
        "message": "Welcome to the SmartDevs Info API!",
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
    }

@app.get("/info")
async def get_info(username: str = Query(None)):
    if not username:
        raise HTTPException(status_code=400, detail="Username parameter is required")

    username = username.strip('@').replace('https://', '').replace('http://', '').replace('t.me/', '').replace('/', '').replace(':', '')
    logger.info(f"Fetching info for: {username}")

    try:
        DC_LOCATIONS = get_dc_locations()

        try:
            user = await asyncio.wait_for(bot.get_users(username), timeout=10.0)
            logger.info(f"User/bot found: {username}")
            premium_status = "Yes" if user.is_premium else "No"
            dc_location = DC_LOCATIONS.get(user.dc_id, "Unknown")
            account_created = estimate_account_creation_date(user.id)
            account_created_str = account_created.strftime("%B %d, %Y")
            account_age = calculate_account_age(account_created)
            verified_status = "Yes" if getattr(user, 'is_verified', False) else "No"
            status = map_user_status(user.status)
            flags = "Scam" if getattr(user, 'is_scam', False) else "Fake" if getattr(user, 'is_fake', False) else "Clean"

            return {
                "type": "bot" if user.is_bot else "user",
                "full_name": f"{user.first_name} {user.last_name or ''}",
                "id": user.id,
                "username": f"@{user.username}" if user.username else "None",
                "context_id": user.id,
                "data_center": f"{user.dc_id} ({dc_location})",
                "premium": premium_status,
                "verified": verified_status,
                "flags": flags,
                "status": status,
                "account_created_on": account_created_str,
                "account_age": account_age
            }

        except (PeerIdInvalid, UsernameNotOccupied):
            logger.info(f"Username '{username}' not found as user/bot. Checking for chat...")
            try:
                chat = await asyncio.wait_for(bot.get_chat(username), timeout=10.0)
                dc_location = DC_LOCATIONS.get(chat.dc_id, "Unknown")
                chat_type = {
                    ChatType.SUPERGROUP: "Supergroup",
                    ChatType.GROUP: "Group",
                    ChatType.CHANNEL: "Channel"
                }.get(chat.type, "Unknown")

                return {
                    "type": chat_type.lower(),
                    "title": chat.title,
                    "id": chat.id,
                    "type_description": chat_type,
                    "member_count": chat.members_count if chat.members_count else "Unknown",
                    "data_center": f"{chat.dc_id} ({dc_location})"
                }

            except UsernameNotOccupied:
                logger.error(f"Username '{username}' does not exist")
                raise HTTPException(status_code=404, detail=f"Username '@{username}' does not exist")
            except (ChannelInvalid, PeerIdInvalid):
                logger.error(f"Permission error for '{username}'")
                raise HTTPException(status_code=403, detail="Bot lacks permission to access this channel or group")
            except asyncio.TimeoutError:
                logger.error(f"Timeout fetching chat info for '{username}'")
                raise HTTPException(status_code=504, detail="Request to Telegram API timed out")
            except Exception as e:
                logger.error(f"Error fetching chat info for '{username}': {str(e)}")
                raise HTTPException(status_code=500, detail=f"Failed to fetch info: {str(e)}")

        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching user info for '{username}'")
            raise HTTPException(status_code=504, detail="Request to Telegram API timed out")
        except Exception as e:
            logger.error(f"Error fetching user info for '{username}': {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to fetch info: {str(e)}")

    except Exception as e:
        logger.error(f"Unhandled exception for '{username}': {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Starting FastAPI app on host 0.0.0.0, port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
