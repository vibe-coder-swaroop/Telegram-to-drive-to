
from telethon import TelegramClient
from telethon.sessions import StringSession
import os
import shutil
import asyncio
import logging

# ==========================================
# 1. LOGGING CONFIGURATION
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger("TelegramArchiver")
logging.getLogger('telethon').setLevel(logging.WARNING)


# ==========================================
# 2. TELEGRAM CONFIGURATION
# ==========================================

api_id = int(os.environ['API_ID'])
api_hash = os.environ['API_HASH']
session_string = os.environ['TELEGRAM_SESSION']

channel_id = -1003980679191

base_save_path = (
    '/content/drive/MyDrive/Telegram_Archive/topper-batch/'
)

LOCAL_TEMP_DIR = '/content/telegram_tmp/'

os.makedirs(LOCAL_TEMP_DIR, exist_ok=True)


# ==========================================
# 3. PARALLEL DOWNLOAD SETTINGS
# ==========================================

MAX_PARALLEL_DOWNLOADS = 4
BATCH_SIZE = 100
MAX_RETRIES = 3

download_semaphore = asyncio.Semaphore(
    MAX_PARALLEL_DOWNLOADS
)

# Prevent simultaneous writes to the same destination filename
destination_locks = {}


# ==========================================
# 4. SUBJECT-WISE MESSAGE IDS
# ==========================================

target_downloads = {
    "Maths": list(range(11, 137)),
    "English": list(range(140, 298)),
    "Reasoning": list(range(303, 393)),
    "Gk-GS": list(range(397, 514))
}


# ==========================================
# 5. UNIQUE FILENAME GENERATOR
# ==========================================

def generate_filename(message, is_video):

    if message.file and message.file.name:

        original_name = os.path.basename(
            message.file.name.replace('\\', '/')
        )

        if is_video:

            name, extension = os.path.splitext(
                original_name
            )

            if not extension:
                extension = message.file.ext or '.mp4'

            return f"{message.id}_{name}{extension}"

        else:
            # Keep original Telegram PDF filename
            return original_name

    else:

        extension = (
            message.file.ext
            if message.file and message.file.ext
            else ('.mp4' if is_video else '.pdf')
        )

        if is_video:
            return f"{message.id}_video{extension}"

        return f"file_{message.id}{extension}"


# ==========================================
# 6. SINGLE FILE DOWNLOAD FUNCTION
# ==========================================

async def download_file(client, message, current_save_path):

    if not message or not message.media:
        return

    is_video = message.video is not None

    is_pdf = (
        message.document is not None
        and message.document.mime_type == 'application/pdf'
    )

    if not (is_video or is_pdf):
        return

    file_name = generate_filename(
        message,
        is_video
    )

    full_drive_path = os.path.join(
        current_save_path,
        file_name
    )

    # Each Telegram message gets its own temporary filename.
    # This prevents collisions when PDFs share a filename.
    local_path = os.path.join(
        LOCAL_TEMP_DIR,
        f"{message.id}_{file_name}"
    )

    # Lock files targeting the same final filename
    lock = destination_locks.setdefault(
        full_drive_path,
        asyncio.Lock()
    )

    async with lock:

        if os.path.exists(full_drive_path):

            logger.info(
                f"[SKIP] [ID: {message.id}] "
                f"Already exists: {file_name}"
            )
            return

        async with download_semaphore:

            file_type = "Video" if is_video else "PDF"

            for attempt in range(1, MAX_RETRIES + 1):

                try:

                    logger.info(
                        f"[DOWNLOAD] [ID: {message.id}] "
                        f"{file_type}: {file_name} "
                        f"(Attempt {attempt}/{MAX_RETRIES})"
                    )

                    downloaded_path = await client.download_media(
                        message,
                        file=local_path
                    )

                    if (
                        downloaded_path
                        and os.path.isfile(local_path)
                    ):

                        # Check again before saving
                        if os.path.exists(full_drive_path):

                            os.remove(local_path)

                            logger.info(
                                f"[SKIP] Already saved: {file_name}"
                            )
                            return

                        # Move to Google Drive
                        shutil.move(
                            local_path,
                            full_drive_path
                        )

                        logger.info(
                            f"[SUCCESS] [ID: {message.id}] "
                            f"Saved: {file_name}"
                        )

                        return

                    raise IOError("Downloaded file not found")

                except Exception as e:

                    logger.error(
                        f"[FAILED] [ID: {message.id}] "
                        f"Attempt {attempt}: {e}"
                    )

                    if attempt < MAX_RETRIES:

                        await asyncio.sleep(
                            2 * attempt
                        )

                finally:

                    if os.path.exists(local_path):
                        os.remove(local_path)

            logger.error(
                f"[PERMANENT FAILURE] "
                f"Message ID: {message.id}, "
                f"Filename: {file_name}"
            )


# ==========================================
# 7. MAIN ARCHIVING PROCESS
# ==========================================

async def main():

    logger.info("Starting Telegram Archiver...")

    client = TelegramClient(
        StringSession(session_string),
        api_id,
        api_hash
    )

    client.max_concurrent_connections = 4

    try:

        await client.connect()

        if not await client.is_user_authorized():

            logger.critical(
                "Telegram session invalid or expired."
            )
            return

        logger.info(
            f"Connected! Channel ID: {channel_id}"
        )

        # Process each subject
        for subject, msg_ids in target_downloads.items():

            current_save_path = os.path.join(
                base_save_path,
                subject
            )

            os.makedirs(
                current_save_path,
                exist_ok=True
            )

            total_ids = len(msg_ids)

            logger.info(
                f"Starting {subject}: {total_ids} messages"
            )

            # Process messages in batches
            for b_idx in range(
                0,
                total_ids,
                BATCH_SIZE
            ):

                batch_slice = msg_ids[
                    b_idx:b_idx + BATCH_SIZE
                ]

                logger.info(
                    f"[BATCH] {subject}: "
                    f"{b_idx + 1} to "
                    f"{min(b_idx + BATCH_SIZE, total_ids)}"
                )

                try:

                    messages = await client.get_messages(
                        channel_id,
                        ids=batch_slice
                    )

                    # Download up to 4 files simultaneously
                    tasks = [
                        download_file(
                            client,
                            message,
                            current_save_path
                        )
                        for message in messages
                        if message is not None
                    ]

                    await asyncio.gather(*tasks)

                    logger.info(
                        f"[BATCH COMPLETE] {subject}: "
                        f"{b_idx + len(batch_slice)} processed"
                    )

                except Exception:

                    logger.exception(
                        f"[BATCH ERROR] {subject}, "
                        f"starting index {b_idx}"
                    )

                    await asyncio.sleep(10)

        logger.info(
            "All subject archives processed successfully."
        )

    finally:

        if client.is_connected():
            await client.disconnect()

        # Clean temporary storage
        try:
            shutil.rmtree(LOCAL_TEMP_DIR)
        except Exception:
            logger.exception(
                "Could not clean temporary directory."
            )

        logger.info(
            "Telegram Archiver execution finished."
        )


# ==========================================
# 8. EXECUTION
# ==========================================

if __name__ == "__main__":
    asyncio.run(main())
                    
