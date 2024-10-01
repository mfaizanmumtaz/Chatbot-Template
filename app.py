from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, join_room, leave_room, emit
from openai import OpenAI
import os
import base64
import tempfile
import uuid
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, 
            static_folder='static',
            static_url_path='/static',
            template_folder='templates')

socketio = SocketIO(app, cors_allowed_origins="*")

client = OpenAI()

@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        print(f"Error rendering template: {e}")
        return f"Error: {e}", 500

@socketio.on('connect')
def on_connect():
    room = str(uuid.uuid4())
    join_room(room)
    emit('room', {'room': room})

@socketio.on('process_text')
def process_text(data):
    text = data['text']
    room = data['room']
    history = data.get('history', [])
    
    # Process the text with ChatGPT, including chat history
    messages = history + [{"role": "user", "content": text}]
    chat_completion = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages
    )
    
    response_text = chat_completion.choices[0].message.content
    emit('text_response', {'text': response_text, 'isTranscription': False}, room=room)

@socketio.on('generate_audio')
def generate_audio(data):
    text = data['text']
    room = data['room']
    print(f"Generating audio for text: {text[:50]}...")  # Log the first 50 characters of the text
    
    try:
        # Generate audio response
        speech_response = client.audio.speech.create(
            model="tts-1",
            voice="alloy",
            input=text
        )

        # Encode the audio response to base64
        audio_base64 = base64.b64encode(speech_response.content).decode('utf-8')
        audio_data_url = f"data:audio/mp3;base64,{audio_base64}"

        print(f"Audio generated successfully. Data URL length: {len(audio_data_url)}")
        emit('audio_generated', {
            'text': text,
            'audio_url': audio_data_url
        }, room=room)
    except Exception as e:
        print(f"Error generating audio: {str(e)}")
        emit('audio_error', {'error': str(e)}, room=room)

@socketio.on('process_audio')
def process_audio(data):
    audio_data = data['audio']
    room = data['room']
    history = data.get('history', [])
    # Decode the base64 audio data
    audio_bytes = base64.b64decode(audio_data.split(',')[1])
    
    # Save the audio data to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_audio_file:
        temp_audio_file.write(audio_bytes)
        temp_audio_path = temp_audio_file.name

    try:
        # Transcribe the audio using Whisper
        with open(temp_audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file,
            )
        
        # Emit the transcription to the client
        emit('text_response', {'text': transcript.text, 'isTranscription': True}, room=room)
        
        # Process the transcribed text with ChatGPT
        messages = history + [{"role": "user", "content": transcript.text}]
        chat_completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages
        )
        
        response_text = chat_completion.choices[0].message.content
        
        # Emit the model's response
        emit('text_response', {'text': response_text, 'isTranscription': False}, room=room)

    finally:
        # Clean up the temporary file
        os.unlink(temp_audio_path)

# Add this new event handler
@socketio.on('audio_error')
def handle_audio_error(data):
    print(f"Audio error: {data['error']}")

if __name__ == '__main__':
    print(f"Templates folder: {app.template_folder}")
    print(f"Static folder: {app.static_folder}")
    socketio.run(app, debug=True)