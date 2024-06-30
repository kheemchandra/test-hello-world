import os
import cv2
from aiohttp import web
import shutil
import telebot
import traceback
import requests
import mimetypes
import googleapiclient
from googleapiclient.discovery import build
import concurrent.futures


# Load environment variables
TOKEN='<your-telegram-bot-token>'
GOOGLE_API_KEY='<your-google-ai-api-key>'

# Initialize Telegram bot
bot = telebot.TeleBot(TOKEN)

# Set up Gemini API
DISCOVERY_URL = f"https://generativelanguage.googleapis.com/$discovery/rest?version=v1beta&key={GOOGLE_API_KEY}"
discovery_doc = requests.get(DISCOVERY_URL).content



# =========================================
# =========================================
# ============INTRO-SECTION-START======================

@bot.message_handler(commands=["start"])
def send_welcome(message): 
    bot.reply_to(message, "Hi there! I am Int Bot. I can generate description for image & video, can chat with you. \n\nTo get started, upload an image or video and use the /img or /vid command to ask about it. You can use the /chat command to chat with me.")

@bot.message_handler(commands=["help"])
def send_welcome(message):
    bot.reply_to(message, "Hi there! I am Int Bot. I can generate description for image & video, can chat with you. \n\nTo get started, upload an image or video and use the /img or /vid command to ask about it. You can use the /chat command to chat with me.")


# ============INTRO-SECTION-END======================
# =========================================
# =========================================

# =========================================
# =========================================
# ============IMAGE-SECTION-START======================



# File class for Gemini API
class File:
    def __init__(self, file_path, display_name=None, mimetype=None, uri=None):
        self.file_path = file_path
        self.display_name = display_name or os.path.basename(file_path)
        self.mimetype = mimetype or mimetypes.guess_type(file_path)[0]
        self.uri = uri

    def set_file_uri(self, uri):
        self.uri = uri

# Function to create GenerateContent request
def makeGenerateContentRequest(prompt, files):
    generateContent = {"contents": [{"parts": [{"text": prompt}]}]}
    for file in files:
        generateContent["contents"][0]["parts"].append(makeImagePart(file))
    return generateContent

# Function to create image part for request
def makeImagePart(file):
    return [{"file_data": {"file_uri": file.uri, "mime_type": file.mimetype}}]


# Handle photo uploads
# Global variable to store file paths for each chat
chat_file_paths = {}

@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    chat_id = message.chat.id
    create_directories(chat_id)
    try:

        # Send a message to the user immediately after receiving the image
        bot.send_message(chat_id, "Image received. Start your query with /img to ask about the image.")

        # Get file information
        file_info = bot.get_file(message.photo[-1].file_id)

        # Extract file extension
        file_extension = os.path.splitext(file_info.file_path)[1]

        # Download and save image with original extension
        downloaded_file = bot.download_file(file_info.file_path)
        os.makedirs('assets', exist_ok=True)  # Create 'assets/' directory if it does not exist
        file_path = f"assets/images/image_{chat_id}{file_extension}"
        with open(file_path, "wb") as new_file:
            new_file.write(downloaded_file)

        # Store file path for this chat
        chat_file_paths[chat_id] = file_path

    except Exception as e:
        print("An error occurred:", e)
        traceback.print_exc()
        bot.reply_to(message, "Sorry, there was an error processing your image.")


@bot.message_handler(commands=['img'])
def handle_img_command(message):
    chat_id = message.chat.id
    create_directories(chat_id)    
    try:
        genai_service_thread = googleapiclient.discovery.build_from_document(discovery_doc, developerKey=GOOGLE_API_KEY)


        # Check if there is a file path for this chat
        if chat_id not in chat_file_paths:
            bot.send_message(chat_id, "Please upload an image, or use /help for help.")
            return

        file_path = chat_file_paths[chat_id] 

        # Strip any leading or trailing whitespace from the message text
        message = message.text.strip()

        # Check if the message text starts with "/img"
        if message == '/img':
            # Use default prompt if none is provided
            prompt = "Provide a very brief description of the image."
        else:
            # Remove '/img' from the start of the message text and strip any leading or trailing whitespace
            prompt = message[4:].strip()

         

        # Send feedback to user immediately after receiving the command
        loading_message = bot.send_message(chat_id, "Please wait...")

        # Create File object and upload to File API
        file = File(file_path=file_path, display_name="Uploaded Image")
        upload_response = genai_service_thread.media().upload(
            media_body=file.file_path,
            media_mime_type=file.mimetype,
            body={"file": {"display_name": file.display_name}},
        ).execute()
        file.set_file_uri(upload_response["file"]["uri"])

        # Generate description using Gemini
        model = "models/gemini-1.5-pro-latest"
        prompt = f"Summarize your response to this image query [[{prompt}]] within 150 characters limit."
        genai_service_thread = googleapiclient.discovery.build_from_document(discovery_doc, developerKey=GOOGLE_API_KEY)
        response = genai_service_thread.models().generateContent(
            model=model, body=makeGenerateContentRequest(prompt, [file])
        ).execute()

        

        # Extract description
        description_text = response_parser(response)
        

        # Edit the "Please wait..." message with the Gemini response
        bot.edit_message_text(chat_id=chat_id, message_id=loading_message.message_id, text=description_text)

        # Delete uploaded file
        resource = file.uri.split("/files/")[-1]
        genai_service_thread.files().delete(name=f"files/{resource}").execute()

    except Exception as e:
        print("An error occurred:", e)
        traceback.print_exc()
        bot.reply_to(message, "Sorry, there was an error processing your image.")



# =========================================
# =========================================
# ============IMAGE-SECTION-END======================



# =========================================
# =========================================
# ============CHAT-SECTION-START======================
@bot.message_handler(commands=['chat'])
def handle_chat_command(message):
    try:
        chat_id = message.chat.id         

        # Strip any leading or trailing whitespace from the message text
        prompt = message.text.strip() 
        
        prompt = prompt[5:].strip() 

        if len(prompt.split(' ')) < 2:
            bot.send_message(chat_id, "Please enter the text after /chat or use /help for help.")
            return

        # Send feedback to user immediately after receiving the command
        loading_message = bot.send_message(chat_id, "Please wait...")

        # Create a new client for this request
        genai_service_thread = googleapiclient.discovery.build_from_document(discovery_doc, developerKey=GOOGLE_API_KEY)
        
        # Generate description using Gemini
        model = "models/gemini-pro"
        response = genai_service_thread.models().generateContent(
            model=model, 
            body={"contents": [{"parts": [{"text": f"Summarize your response to this user input [[{prompt}]] within 60 characters limit."}]}]}
        ).execute()

        # Extract description 
        description_text = response_parser(response)
        
        # Edit the "Please wait..." message with the Gemini response
        bot.edit_message_text(chat_id=chat_id, message_id=loading_message.message_id, text=description_text)

    except Exception as e:
        print("An error occurred:", e)
        traceback.print_exc()
        bot.reply_to(message, "Sorry, there was an error. Please try after sometime.")  

# =========================================
# =========================================
# ============CHAT-SECTION-END======================
    



# =========================================
# =========================================
# ============VIDEO-SECTION-START======================
        


# Constants
FRAME_EXTRACTION_DIRECTORY = "./assets/content/frames_{}"
FRAME_PREFIX = "_frame" 

# Video processing status
video_processing = False


class File_v:
  def __init__(self, file_path: str, display_name: str = None,
               timestamp_seconds: int = None, mimetype: str = None, uri = None):
    self.file_path = file_path
    if display_name:
      self.display_name = display_name
    if timestamp_seconds != None:
      self.timestamp = seconds_to_time_string_v(timestamp_seconds)
    # Detect mimetype if not specified
    self.mimetype = mimetype if mimetype else mimetypes.guess_type(file_path)[0]
    self.uri = uri

  def set_file_uri(self, uri):
    self.uri = uri


def seconds_to_time_string_v(seconds):
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def get_timestamp_seconds_v(filename):
    parts = filename.split(FRAME_PREFIX)
    if len(parts) != 2:
        return None  # Indicate incorrect filename format
    frame_count_str = parts[1].split(".")[0]
    return int(frame_count_str)


def create_frame_output_dir_v(output_dir): 

    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir) 


def frames_exist_in_directory_v(directory):
    return any(filename.endswith(".jpg") for filename in os.listdir(directory))


def extract_frame_from_video_v(video_file_path, output_dir):
    try:
        if frames_exist_in_directory_v(output_dir):
            print(f"Frames already exist. Skipping frame extraction.")
            return

        print(f"Extracting {video_file_path} at 1 frame per second...")
        create_frame_output_dir_v(output_dir)
        vidcap = cv2.VideoCapture(video_file_path)
        fps = int(vidcap.get(cv2.CAP_PROP_FPS)) 
        output_file_prefix = os.path.basename(video_file_path).replace(".", "_")
 
        frame_count = 0
        count = 0
        while vidcap.isOpened():
            success, frame = vidcap.read()
            if not success or frame_count >= 30:  # Break the loop if frame_count reaches 30
                break
            if count % fps == 0:
                image_name = f"{output_file_prefix}{FRAME_PREFIX}{frame_count:04d}.jpg"
                output_filename = os.path.join(output_dir, image_name) 
                cv2.imwrite(output_filename, frame)
                frame_count += 1
            count += 1
        vidcap.release()
        print(f"Extracted {frame_count} frames.")
    except Exception as e:
        print(f"HERE IS ERROR: {e}")


def upload_file_v(file):
    print(f"Uploading: {file.file_path}...")
    # Create a new service object for each thread
    genai_service_thread = googleapiclient.discovery.build_from_document(discovery_doc, developerKey=GOOGLE_API_KEY)
    
    response = genai_service_thread.media().upload(
        media_body=file.file_path, media_mime_type=file.mimetype
    ).execute()
    file.set_file_uri(response["file"]["uri"])
    return file


def make_video_part_v(file):
    return [
        {"text": file.timestamp},
        {"file_data": {"file_uri": file.uri, "mime_type": file.mimetype}},
    ]


def make_generate_content_request_v(prompt, files):
    generate_content = {"contents": [{"parts": [{"text": prompt}]}]}
    for file in files:
        generate_content["contents"][0]["parts"].extend(make_video_part_v(file))
    return generate_content


def delete_file_v(file):
    print(f"Deleting: {file.file_path}...")
    # Create a new service object for each thread
    genai_service_thread = googleapiclient.discovery.build_from_document(discovery_doc, developerKey=GOOGLE_API_KEY)
    
    resource = file.uri.split("/files/")[-1]
    genai_service_thread.files().delete(name=f"files/{resource}").execute()


# Telegram bot handlers



@bot.message_handler(content_types=["video"])
def handle_video(message):
    global video_processing
    chat_id = message.chat.id
    create_directories(chat_id)
    wait_message = bot.send_message(chat_id, "Please wait...")
    try:        
        file_info = bot.get_file(message.video.file_id)
        # Check the file size
        if file_info.file_size > 7 * 1024 * 1024:  # 7MB
            bot.edit_message_text("The video is too big.", chat_id, wait_message.message_id)
            return
        
        video_processing = True
        
        # Delete existing frames and create a new directory for frames
        create_frame_output_dir_v(FRAME_EXTRACTION_DIRECTORY.format(chat_id))

        downloaded_video = requests.get(f'https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}')

        os.makedirs("assets", exist_ok=True)
        # Append chat_id to the video file name
        video_file_name = f"assets/videos/video_{chat_id}.mp4"
        with open(video_file_name, "wb") as new_video:
            new_video.write(downloaded_video.content)

        # Set video processing status to False
        video_processing = False

        bot.edit_message_text("Please start your query with /vid", chat_id, wait_message.message_id)

    except telebot.apihelper.ApiException as e:
        if 'file is too big' in str(e):
            bot.edit_message_text("The video is too big.", chat_id, wait_message.message_id)
        else:
            print(f"An error occurred: {e}")
            bot.edit_message_text("An error occurred while processing your video. Please try again.", chat_id, wait_message.message_id)
    except Exception as e:
        # Handle other general errors
        print(f"An error occurred: {e} in handle_video")
        bot.send_message(chat_id, f"Something went wrong. Try after sometime.")


@bot.message_handler(commands=["vid"])
def handle_vid_query(message):
    chat_id = message.chat.id
    global video_processing
    create_directories(chat_id)
    try:
        wait_message = bot.send_message(chat_id, "🤔......")
        
        
        
        query = message.text.split("/vid")[1].strip()

        # Check if frames exist
        # Append chat_id to the video file name
        video_file_name = f"assets/videos/video_{chat_id}.mp4"
        if not frames_exist_in_directory_v(FRAME_EXTRACTION_DIRECTORY.format(chat_id)):
            # Check if video is still being processed
            if video_processing:
                bot.edit_message_text(chat_id=chat_id, message_id=wait_message.message_id, text="Your video is currently being processed, please wait.")
                return
            
            # Check if video exists
            if not os.path.exists(video_file_name):
                bot.edit_message_text(chat_id=chat_id, message_id=wait_message.message_id, text="Please upload a video, or use /help for help.")
                return

            

            # Extract frames
            extract_frame_from_video_v(video_file_name, FRAME_EXTRACTION_DIRECTORY.format(chat_id))

        # Set video processing status to False
        video_processing = False

        # Send "Please wait..." message to user
        bot.edit_message_text(chat_id=chat_id, message_id=wait_message.message_id, text="Please wait...") 
        

        # Prepare files for upload
        files_to_upload = [
            File_v(file_path=os.path.join(FRAME_EXTRACTION_DIRECTORY.format(chat_id), file), timestamp_seconds=get_timestamp_seconds_v(file))
            for file in sorted(os.listdir(FRAME_EXTRACTION_DIRECTORY.format(chat_id)))
        ]

        # Upload files concurrently
        with concurrent.futures.ThreadPoolExecutor() as executor:
            uploaded_files = list(executor.map(upload_file_v, files_to_upload))

        # Generate content 
        model = "models/gemini-1.5-pro-latest" # @param ["models/gemini-1.5-pro-latest", "models/gemini-1.0-pro-vision-latest"]
        prompt = f"Summarize your response to this video query [[{query}]] within 150 characters limit."
        
        # Create a new client for this request
        genai_service_thread = googleapiclient.discovery.build_from_document(discovery_doc, developerKey=GOOGLE_API_KEY)
        
        req = make_generate_content_request_v(prompt, uploaded_files)
        response = genai_service_thread.models().generateContent(
            model = model,
            body = req).execute() 

        # Extract description
        description_text = response_parser(response)
         

        # Edit "Please wait..." message with actual response
        bot.edit_message_text(chat_id=chat_id, message_id=wait_message.message_id, text=description_text)

        # Delete uploaded files concurrently
        with concurrent.futures.ThreadPoolExecutor() as executor:
            list(executor.map(delete_file_v, uploaded_files))

    except Exception as e:
        print(f"An error occurred: {e}")
        bot.send_message(chat_id, "An error occurred while processing your video. Please try again.")


# ==========VIDEO-SECTION-END=================
# =========================================
# =========================================



# =========================================
# =========================================
# ==========DOCUMENT-SECTION-START=================
@bot.message_handler(content_types=["document"])
def handle_document(message):
    chat_id = message.chat.id
    create_directories(chat_id)
    # Send the "Please wait..." message
    wait_message = bot.send_message(chat_id, "Please wait...")
    try:
        file_info = bot.get_file(message.document.file_id)
        file_path = file_info.file_path

        if file_path.endswith(".mp4"):
            # Delete the wait message
            bot.delete_message(chat_id, wait_message.message_id)
            # Create a new message object with the video field set to the document field
            message.content_type = "video"
            message.video = message.document
            handle_video(message)
        elif file_path.endswith((".png", ".jpg", ".jpeg")):
            # Delete the wait message
            bot.delete_message(chat_id, wait_message.message_id)
            # Create a new message object with the photo field set to the document field
            message.content_type = "photo"
            message.photo = [message.document]
            handle_photo(message)
        else:
            # Edit the wait message
            bot.edit_message_text("Unsupported file type. Please upload a video or image. Use /help for help.", chat_id, wait_message.message_id)
    except telebot.apihelper.ApiException as e:
        if 'file is too big' in str(e):
            bot.edit_message_text("The file is too big.", chat_id, wait_message.message_id)
        else:
            print(f"An error occurred: {e}")
            bot.edit_message_text("An error occurred while processing your file. Please try again.", chat_id, wait_message.message_id)
    except Exception as e:
        # Handle other general errors
        print(f"An error occurred: {e} in handle_document")
        bot.send_message(chat_id, f"Something went wrong. Try after sometime.")
# ==========DOCUMENT-SECTION-END=================
# =========================================
# =========================================
        

# =========================================
# =========================================
# ==========TEXT & Extra-SECTION-START=================
@bot.message_handler(content_types=["text"])
def handle_text(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "Start your query with /chat to get response to text or use /help for help.")
        

@bot.message_handler(content_types=["audio", "animation", "game", "sticker", "video_note", "voice", "location", "contact", "venue", "dice", "new_chat_members", "left_chat_member", "new_chat_title", "new_chat_photo", "delete_chat_photo", "group_chat_created", "supergroup_chat_created", "channel_chat_created", "migrate_to_chat_id", "migrate_from_chat_id", "pinned_message", "invoice", "successful_payment", "connected_website", "poll", "passport_data", "proximity_alert_triggered", "video_chat_scheduled", "video_chat_started", "video_chat_ended", "video_chat_participants_invited", "web_app_data", "message_auto_delete_timer_changed", "forum_topic_created", "forum_topic_closed", "forum_topic_reopened", "forum_topic_edited", "general_forum_topic_hidden", "general_forum_topic_unhidden", "write_access_allowed", "user_shared", "chat_shared", "story"])
def handle_unsupported_types(message):
    supported_types = ["Image", "Video", "Text"] 
    bot.reply_to(message, "Your message type should be one of these: \nImage, Video or Text.")


# ==========TEXT & Extra-SECTION-END=================
# =========================================
# =========================================
    


# =========================================
# =========================================
# ==========HELPER-METHOD=================
    
def response_parser(response):
    result='I cannot answer this.'
    if 'candidates' not in response:
        return result
    result = response["candidates"][0]["content"]["parts"][0]['text']  
    return result

    # Create directories if they don't exist
def create_directories(chat_id):
    directories = [f'./assets/content/frames_{chat_id}', './assets/images', './assets/videos']
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
         
# ==========HELPER-METHOD=================
# =========================================
# =========================================



# =========================================
# =========================================
# ==========WEB-HOOK-START=================
WEBHOOK_HOST =  '<web-hook>'
WEBHOOK_PORT = 8443  
WEBHOOK_LISTEN = '0.0.0.0'  
WEBHOOK_URL_BASE = "https://{}".format(WEBHOOK_HOST)
WEBHOOK_URL_PATH = "/{}/".format(TOKEN)



app = web.Application()


async def handle(request):
    print("Received a request...")
    if request.match_info.get('token') == bot.token:
        request_body_dict = await request.json()
        update = telebot.types.Update.de_json(request_body_dict)
        bot.process_new_updates([update])
        return web.Response()
    else:
        return web.Response(status=403)
app.router.add_post('/{token}/', handle)


print("Removing old webhook...")
bot.remove_webhook()

print("Setting new webhook...")
try:
    bot.set_webhook(url=WEBHOOK_URL_BASE + WEBHOOK_URL_PATH)
except Exception as e:
    print(f"Error setting webhook: {e}")
                

print("Starting Server...")
web.run_app(
    app,
    host=WEBHOOK_LISTEN,
    port=WEBHOOK_PORT
)
print("Server started!")
# ==========WEB-HOOK-END=================
# =========================================
# =========================================






