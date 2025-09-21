from flask import Flask, send_from_directory, request, jsonify, send_file
from flask_cors import CORS
import asyncio, os, edge_tts
from google import genai
from google.genai import types
from googleapiclient.discovery import build

app = Flask(__name__, static_folder="../client", static_url_path="")
CORS(app)

GEMINI_API_KEY = "AIzaSyBc70X28NtqrbzEpkz6uKcbLfXgDZ1Sixs"
YOUTUBE_API_KEY = "AIzaSyAwoGu3XgUVmIPtl2ZGlR1ZoJR-veqEUD4"

client = genai.Client(api_key=GEMINI_API_KEY)
grounding_tool = types.Tool(google_search=types.GoogleSearch())
config = types.GenerateContentConfig(tools=[grounding_tool])

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
AUDIO_FILE = os.path.join(UPLOAD_FOLDER, "latest.mp3")

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path):
    """
    Catch-all route to serve frontend files.
    If file exists in client/, serve it.
    Otherwise, fallback to index.html (for single-page routing).
    """
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, "index.html")

def youtube_search(query):
    youtube_set = []
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    request = youtube.search().list(q=query, part="snippet", maxResults=1, type="video")
    response = request.execute()
    for item in response["items"]:
        title = item["snippet"]["title"]
        video_id = item["id"]["videoId"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        youtube_set.append({"title": title, "url": video_url})
    return youtube_set

@app.route("/ytlink", methods=["GET"])
def ytlink():
    topic = request.args.get("topic")
    class_ = request.args.get("class")
    board = request.args.get("board")
    if not all([topic, class_, board]):
        return jsonify({"error": "Missing topic, class, or board parameter"}), 400
    query = f"{topic} Class {class_} {board} syllabus"
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    request_api = youtube.search().list(
        q=query, part="snippet", maxResults=5, type="video"
    )
    response = request_api.execute()
    links = [
        f"https://www.youtube.com/watch?v={item['id']['videoId']}"
        for item in response["items"]
    ]
    return jsonify(links)

def generate_feynman(name, topic, class_, board):
    """Generate a simplified explanation using Feynman Technique."""
    prompt = (
        f"Student Name: {name}\n"
        f"Topic: {topic}\n"
        f"Class: {class_}\n"
        f"Board: {board}\n\n"
        f"Explain {topic} to {name} in a short, clear, simple way "
        f"for a Class {class_} student following the {board} board. "
        f"Use the Feynman Technique: break down the idea into basic terms, avoid jargon, "
        f"use analogies or examples, and relate it to everyday experiences."
    )
    response = client.models.generate_content(
        model="gemini-2.5-flash", contents=prompt, config=config
    )
    return response.text.strip()

def generate_explanation(name, class_, topic, board):
    """Generate detailed HTML-friendly explanation."""
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=(
            f"Explain the topic {topic} of class {class_} to a student named {name} "
            f"as per syllabus of {board} elaborately."
        ),
        config=config
    )
    return response.text

async def text_to_speech(text, output_path):
    voice = "en-GB-RyanNeural"
    communicate = edge_tts.Communicate(text=text, voice=voice)
    await communicate.save(output_path)

@app.route("/generate_audio", methods=["POST"])
def generate_audio_post():
    data = request.get_json()
    name = data.get("name")
    topic = data.get("topic")
    class_ = data.get("class")
    board = data.get("board")
    explanation = (
        generate_feynman(name, topic, class_, board).replace("\n", " ").replace("*", "")
    )
    asyncio.run(text_to_speech(explanation, AUDIO_FILE))
    if os.path.exists(AUDIO_FILE):
        return send_file(AUDIO_FILE, mimetype="audio/mpeg")
    return jsonify({"error": "Audio could not be generated"}), 500

@app.route("/audio")
def get_audio():
    if os.path.exists(AUDIO_FILE):
        return send_file(AUDIO_FILE, mimetype="audio/mpeg")
    return "No audio found", 404

@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    name = data.get("name")
    topic = data.get("topic")
    board = data.get("board")
    class_ = data.get("class")
    explanation = generate_explanation(name, class_, topic, board)
    return jsonify({"txt": explanation})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Flask server running on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port)

