from telethon import TelegramClient
from telethon.sessions import StringSession
import os
import shutil
import asyncio
import logging

# --- Logging System Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("TelegramArchiver")

# SILENCE TELETHON INTERNAL NOISE
logging.getLogger('telethon').setLevel(logging.WARNING)

# --- Configuration (Pulled from GitHub Env) ---
api_id = int(os.environ['API_ID'])
api_hash = os.environ['API_HASH']
session_string = os.environ['TELEGRAM_SESSION']

channel_id = -1003980679191 # Your target private channel ID
base_save_path = '/content/drive/MyDrive/Telegram_Archive/topper-batch/'

LOCAL_TEMP_DIR = '/content/telegram_tmp/'
os.makedirs(LOCAL_TEMP_DIR, exist_ok=True)

target_downloads = {
    "Maths": [i for i in range(11,137)],
    "English": [j for j in range(140,298)],
    "Reasoning":[k for k in range(303,393)],
    "Gk-GS": [l for l in range(396,)]
    
}

    

async def main():
    logger.info("Starting connection to Telegram...")
    
    # Initialize the client with standard parameters
    client = TelegramClient(StringSession(session_string), api_id, api_hash)
    
    # CRITICAL FIX: Unlock 4 parallel network connections across cross-DC servers
    client.max_concurrent_connections = 4
    
    await client.connect()
    
    if not await client.is_user_authorized():
        logger.critical("Session string is invalid or expired.")
        return

    logger.info(f"Connected securely! Processing target channel: {channel_id}")

    for subject, msg_ids in target_downloads.items():
        current_save_path = os.path.join(base_save_path, subject)
        os.makedirs(current_save_path, exist_ok=True)
        
        total_ids = len(msg_ids)
        logger.info(f"Starting {subject} Block: Evaluating {total_ids} items.")
        
        BATCH_SIZE = 100
        for b_idx in range(0, total_ids, BATCH_SIZE):
            batch_slice = msg_ids[b_idx : b_idx + BATCH_SIZE]
            logger.info(f"Checking batch bundle ({b_idx + 1} to {min(b_idx + BATCH_SIZE, total_ids)})...")
            
            try:
                messages = await client.get_messages(channel_id, ids=batch_slice)
                
                for message in messages:
                    if not message or not message.media:
                        continue
                    
                    is_video = message.video is not None
                    is_pdf = message.document and 'pdf' in message.document.mime_type

                    if is_video or is_pdf:
                        if message.file and message.file.name:
                            file_name = message.file.name
                        else:
                            extension = message.file.ext if message.file.ext else ('.mp4' if is_video else '.pdf')
                            file_name = f"file_{message.id}{extension}"

                        full_drive_path = os.path.join(current_save_path, file_name)
                        
                        if os.path.exists(full_drive_path):
                            logger.info(f"[SKIP] [ID: {message.id}] File already exists: {file_name}")
                            continue

                        local_path = os.path.join(LOCAL_TEMP_DIR, file_name)
                        file_type = "Video" if is_video else "PDF"
                        
                        logger.info(f"[DOWNLOAD] [ID: {message.id}] Starting {file_type} download: {file_name}")
                        
                        # Download directly to local fast container scratch storage
                        await client.download_media(message, file=local_path)
                        
                        if os.path.exists(local_path):
                            shutil.move(local_path, full_drive_path)
                            logger.info(f"[SYNC SUCCESS] [ID: {message.id}] Saved to Mounted Drive: {file_name}")
                        
                        await asyncio.sleep(2)
                        
            except Exception as e:
                logger.error(f"Error handling batch block starting at index {b_idx}: {e}")
                await asyncio.sleep(10)

    try:
        shutil.rmtree(LOCAL_TEMP_DIR)
    except Exception:
        pass
    logger.info("Execution complete. Channel archiving process finished cleanly.")

if __name__ == "__main__":
    asyncio.run(main())
    
