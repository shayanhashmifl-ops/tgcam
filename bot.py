import telegram
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import cv2
import os
import asyncio
import time

# --- Configuration ---
# Replace with your actual bot token
BOT_TOKEN = '7806535006:AAF5mYhGH38KYeH3bXtaPI_f7V6b5-zos2Y'
TEMP_DIR = 'temp_videos'
SS_INTERVAL = 0.5  # Screenshot interval in seconds

# Create the temp directory if it doesn't exist
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# --- Utility Functions ---

async def update_status_message(context: ContextTypes.DEFAULT_TYPE, chat_id, message_id, text):
    """Edits the status message to update the user."""
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text
        )
    except telegram.error.BadRequest as e:
        # Ignore "Message is not modified" error
        if "message is not modified" not in str(e):
            print(f"Error updating status: {e}")

async def process_video_and_send_screenshots(update: Update, context: ContextTypes.DEFAULT_TYPE, video_path: str):
    """Extracts frames and sends them back to the user."""
    chat_id = update.effective_chat.id
    
    # Send initial status message
    status_message = await context.bot.send_message(
        chat_id=chat_id,
        text="🎬 Starting video processing and screenshot extraction..."
    )
    status_message_id = status_message.message_id
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        await update_status_message(context, chat_id, status_message_id, "❌ Error: Could not open video file.")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0:
        await update_status_message(context, chat_id, status_message_id, "❌ Error: Could not determine video FPS.")
        cap.release()
        return

    # Calculate frame step based on the desired interval (0.5 seconds)
    frame_step = int(fps * SS_INTERVAL)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_count = 0
    screenshot_count = 0
    
    start_time = time.time()
    
    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if frame_count % frame_step == 0:
                # High-quality JPEG compression (0-100, 100 is best)
                # Ensure the path is unique and has a .jpg extension
                ss_filename = f"ss_{chat_id}_{screenshot_count}.jpg"
                ss_path = os.path.join(TEMP_DIR, ss_filename)
                
                # Save the frame as a high-quality JPEG
                cv2.imwrite(ss_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                
                # Send the screenshot right away
                with open(ss_path, 'rb') as photo_file:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo_file,
                        caption=f"Screenshot at frame {frame_count} ({screenshot_count+1}/{total_frames//frame_step})"
                    )
                
                # Clean up the temporary screenshot file immediately
                os.remove(ss_path)
                screenshot_count += 1
                
                # Update status (only update every 5 screenshots to avoid API limits)
                if screenshot_count % 5 == 0:
                    percentage = (frame_count / total_frames) * 100 if total_frames else 0
                    await update_status_message(
                        context, 
                        chat_id, 
                        status_message_id, 
                        f"⚙️ Processing... {screenshot_count} screenshots sent. (~{percentage:.1f}%)"
                    )

            frame_count += 1

    except Exception as e:
        await update_status_message(context, chat_id, status_message_id, f"❌ An error occurred during frame extraction: {e}")
    finally:
        cap.release()
        end_time = time.time()

    # Final status update
    duration = end_time - start_time
    await update_status_message(
        context, 
        chat_id, 
        status_message_id, 
        f"✅ Finished! Extracted and sent {screenshot_count} screenshots in {duration:.2f} seconds."
    )


# --- Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message and instructions."""
    await update.message.reply_text(
        "👋 Hello! Send me a **video** and I will extract high-quality screenshots every 0.5 seconds and send them back while showing the status.",
        parse_mode=telegram.constants.ParseMode.MARKDOWN
    )

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles an uploaded video file."""
    chat_id = update.effective_chat.id
    video_file = update.message.video

    if video_file.file_size > 50 * 1024 * 1024:  # Telegram bot API limit is 50MB for uploads
        await update.message.reply_text("⚠️ Video is too large. Max file size is typically 50MB.")
        return

    await context.bot.send_message(chat_id=chat_id, text="⬇️ Downloading video... Please wait.")
    
    # Download the video file
    file_id = video_file.file_id
    new_file = await context.bot.get_file(file_id)
    video_filename = os.path.join(TEMP_DIR, f"{chat_id}_{file_id}.mp4")
    
    try:
        await new_file.download_to_drive(video_filename)
        await context.bot.send_message(chat_id=chat_id, text="💾 Video downloaded. Starting processing...")
        
        # Process the video in the background
        await process_video_and_send_screenshots(update, context, video_filename)
        
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ An error occurred during download/processing: {e}")
    finally:
        # Clean up the downloaded video file
        if os.path.exists(video_filename):
            os.remove(video_filename)
            print(f"Cleaned up: {video_filename}")


# --- Main Execution ---

def main():
    """Starts the bot."""
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.VIDEO & ~filters.COMMAND, handle_video))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND & ~filters.VIDEO, 
                                           lambda update, context: update.message.reply_text("Please send a **video** file.", parse_mode=telegram.constants.ParseMode.MARKDOWN)))

    print("Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
