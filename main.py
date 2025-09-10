# music_api.py - Flask API for music search and download
import os
import logging
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
from io import BytesIO
import zipfile
import requests
import yt_dlp
from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials
import eyed3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.flac import FLAC, Picture
from pydub import AudioSegment
from syncedlyrics import search as get_lyrics
from ytmusicapi import YTMusic
import re
from PIL import Image
import time
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration - Replace with your actual keys
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
# Initialize clients
sp = Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET))
ytmusic = YTMusic()

AUDIO_FORMATS = {
    'mp3': {'format': 'bestaudio/best', 'audio_format': 'mp3', 'preferred_codec': 'mp3', 'audio_quality': '320k', 'export_format': 'mp3', 'codec': None, 'ffmpeg_params': ['-codec:a', 'libmp3lame', '-q:a', '0']},
    'm4a': {'format': 'bestaudio/best', 'audio_format': 'm4a', 'preferred_codec': 'm4a', 'audio_quality': '256k', 'export_format': 'mp4', 'codec': 'aac', 'ffmpeg_params': ['-codec:a', 'aac', '-q:a', '2']},
    'flac': {'format': 'bestaudio/best', 'audio_format': 'flac', 'preferred_codec': 'flac', 'audio_quality': '0', 'export_format': 'flac', 'codec': 'flac', 'ffmpeg_params': ['-codec:a', 'flac', '-compression_level', '8']}
}

TEMP_DIR = 'temp_downloads'
os.makedirs(TEMP_DIR, exist_ok=True)

def sanitize_filename(name):
    return re.sub(r'[\\/:*?"<>|]', '', name)

def search_spotify_tracks(query):
    results = sp.search(q=query, limit=5, type='track')
    return [{'name': t['name'], 'artist': t['artists'][0]['name'], 'url': t['external_urls']['spotify']} for t in results['tracks']['items']]

def search_youtube(query):
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&q={query}&key={YOUTUBE_API_KEY}&maxResults=5"
    response = requests.get(url).json()
    items = [item for item in response.get('items', []) if item['id']['kind'] == 'youtube#video' and get_video_details(item['id']['videoId'])['categoryId'] == '10']
    return [{'title': i['snippet']['title'], 'video_id': i['id']['videoId']} for i in items]

def get_video_details(video_id):
    url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet&id={video_id}&key={YOUTUBE_API_KEY}"
    return requests.get(url).json()['items'][0]['snippet'] if 'items' in requests.get(url).json() else {}

def get_spotify_track_info(url):
    track_id = url.split('/')[-1].split('?')[0]
    track = sp.track(track_id)
    return {'name': track['name'], 'artist': track['artists'][0]['name']}

def get_spotify_playlist_tracks(url):
    playlist_id = url.split('/')[-1].split('?')[0]
    results = sp.playlist_items(playlist_id)
    return [{'name': i['track']['name'], 'artist': i['track']['artists'][0]['name']} for i in results['items'] if i['track']]

def get_spotify_album_tracks(url):
    album_id = url.split('/')[-1].split('?')[0]
    results = sp.album_tracks(album_id)
    return [{'name': i['name'], 'artist': i['artists'][0]['name']} for i in results['items']]

def download_cover(track_id):
    track = sp.track(track_id)
    if track['album']['images']:
        response = requests.get(track['album']['images'][0]['url'])
        return response.content if response.status_code == 200 else None
    return None

def add_mp3_metadata(file_path, cover_data, lyrics, artist, title):
    audio = eyed3.load(file_path)
    if audio.tag is None:
        audio.initTag()
    audio.tag.artist = artist
    audio.tag.title = title
    if lyrics:
        audio.tag.lyrics.set(lyrics)
    if cover_data:
        audio.tag.images.set(3, cover_data, 'image/jpeg')
    audio.tag.save()

def add_m4a_metadata(file_path, cover_data, lyrics, artist, title):
    audio = MP4(file_path)
    audio['\xa9ART'] = artist
    audio['\xa9nam'] = title
    if lyrics:
        audio['\xa9lyr'] = lyrics
    if cover_data:
        audio['covr'] = [MP4Cover(cover_data, imageformat=MP4Cover.FORMAT_JPEG)]
    audio.save()

def add_flac_metadata(file_path, cover_data, lyrics, artist, title):
    audio = FLAC(file_path)
    audio['artist'] = artist
    audio['title'] = title
    if lyrics:
        audio['lyrics'] = lyrics
    if cover_data:
        pic = Picture()
        pic.data = cover_data
        pic.type = 3
        pic.mime = 'image/jpeg'
        audio.add_picture(pic)
    audio.save()

def process_audio(input_path, output_path, audio_format):
    audio = AudioSegment.from_file(input_path)
    export_format = AUDIO_FORMATS[audio_format]['export_format']
    kwargs = {
        'format': export_format,
        'bitrate': AUDIO_FORMATS[audio_format]['audio_quality']
    }
    if 'codec' in AUDIO_FORMATS[audio_format] and AUDIO_FORMATS[audio_format]['codec']:
        kwargs['codec'] = AUDIO_FORMATS[audio_format]['codec']
    if 'ffmpeg_params' in AUDIO_FORMATS[audio_format]:
        kwargs['parameters'] = AUDIO_FORMATS[audio_format]['ffmpeg_params']
    audio.export(output_path, **kwargs)

def download_track(track_name, artist, audio_format, is_spotify=True):
    temp_path = os.path.join(TEMP_DIR, f"{sanitize_filename(track_name)}_temp")
    if artist in track_name:
        output_path = os.path.join(TEMP_DIR, f"{sanitize_filename(track_name)}.{audio_format}")
    else:
        output_path = os.path.join(TEMP_DIR, f"{sanitize_filename(artist + ' - ' + track_name)}.{audio_format}")
    
    query = f"{artist} {track_name}"
    video_id = ytmusic.search(query, filter='songs')[0]['videoId'] if ytmusic.search(query, filter='songs') else None
    if not video_id:
        raise ValueError('Track not found')
    
    ydl_opts = {
        'format': AUDIO_FORMATS[audio_format]['format'],
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': AUDIO_FORMATS[audio_format]['preferred_codec'], 'preferredquality': AUDIO_FORMATS[audio_format]['audio_quality']}],
        'outtmpl': temp_path
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    
    temp_audio_path = f"{temp_path}.{AUDIO_FORMATS[audio_format]['audio_format']}"
    process_audio(temp_audio_path, output_path, audio_format)
    time.sleep(0.5)  # Delay to release file lock
    
    lyrics = get_lyrics(query, synced_only=True) or get_lyrics(query)
    
    if is_spotify:
        sp_result = sp.search(query, limit=1)['tracks']['items'][0]
        cover_data = download_cover(sp_result['id'])
        if audio_format == 'mp3':
            add_mp3_metadata(output_path, cover_data, lyrics, artist, track_name)
        elif audio_format == 'm4a':
            add_m4a_metadata(output_path, cover_data, lyrics, artist, track_name)
        elif audio_format == 'flac':
            add_flac_metadata(output_path, cover_data, lyrics, artist, track_name)
        time.sleep(0.5)  # Delay after metadata to release lock
    
    os.remove(temp_audio_path)
    return output_path

def download_youtube_track(url, audio_format):
    with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
        info = ydl.extract_info(url, download=False)
    track_name = info['title']
    artist = info['uploader']
    temp_path = os.path.join(TEMP_DIR, f"{sanitize_filename(track_name)}_temp")
    if artist in track_name:
        output_path = os.path.join(TEMP_DIR, f"{sanitize_filename(track_name)}.{audio_format}")
    else:
        output_path = os.path.join(TEMP_DIR, f"{sanitize_filename(artist + ' - ' + track_name)}.{audio_format}")
    
    ydl_opts = {
        'format': AUDIO_FORMATS[audio_format]['format'],
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': AUDIO_FORMATS[audio_format]['preferred_codec'], 'preferredquality': AUDIO_FORMATS[audio_format]['audio_quality']}],
        'outtmpl': temp_path
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    
    temp_audio_path = f"{temp_path}.{AUDIO_FORMATS[audio_format]['audio_format']}"
    process_audio(temp_audio_path, output_path, audio_format)
    time.sleep(0.5)  # Delay to release file lock
    
    lyrics = get_lyrics(f"{artist} {track_name}", synced_only=True) or get_lyrics(f"{artist} {track_name}")
    thumbnail_url = info['thumbnail']
    if thumbnail_url:
        resp = requests.get(thumbnail_url)
        if resp.status_code == 200:
            img = Image.open(BytesIO(resp.content)).convert('RGB')
            img = img.crop(((img.width - min(img.size)) // 2, (img.height - min(img.size)) // 2, (img.width + min(img.size)) // 2, (img.height + min(img.size)) // 2))
            cover_buf = BytesIO()
            img.save(cover_buf, 'JPEG')
            cover_data = cover_buf.getvalue()
            if audio_format == 'mp3':
                add_mp3_metadata(output_path, cover_data, lyrics, artist, track_name)
            elif audio_format == 'm4a':
                add_m4a_metadata(output_path, cover_data, lyrics, artist, track_name)
            elif audio_format == 'flac':
                add_flac_metadata(output_path, cover_data, lyrics, artist, track_name)
            time.sleep(0.5)  # Delay after metadata to release lock
    
    os.remove(temp_audio_path)
    return output_path

@app.route('/api/search/spotify', methods=['GET'])
def api_search_spotify():
    query = request.args.get('query')
    if not query:
        return jsonify({'error': 'Query required'}), 400
    return jsonify(search_spotify_tracks(query))

@app.route('/api/search/youtube', methods=['GET'])
def api_search_youtube():
    query = request.args.get('query')
    if not query:
        return jsonify({'error': 'Query required'}), 400
    return jsonify(search_youtube(query))

@app.route('/api/download/track', methods=['POST'])
def api_download_track():
    data = request.json
    url = data.get('url')
    audio_format = data.get('format', 'mp3')
    if audio_format not in AUDIO_FORMATS:
        return jsonify({'error': 'Invalid format'}), 400
    try:
        if 'spotify.com/track' in url:
            info = get_spotify_track_info(url)
            path = download_track(info['name'], info['artist'], audio_format)
        elif 'youtube.com' in url or 'youtu.be' in url:
            path = download_youtube_track(url, audio_format)
        else:
            return jsonify({'error': 'Invalid URL'}), 400
        
        with open(path, 'rb') as f:
            file_data = f.read()
        time.sleep(0.5)  # Delay to ensure file is released
        os.remove(path)
        return send_file(BytesIO(file_data), as_attachment=True, download_name=os.path.basename(path))
    except Exception as e:
        logger.error(str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/playlist', methods=['POST'])
def api_download_playlist():
    data = request.json
    url = data.get('url')
    audio_format = data.get('format', 'mp3')
    if audio_format not in AUDIO_FORMATS:
        return jsonify({'error': 'Invalid format'}), 400
    try:
        if 'spotify.com/playlist' in url:
            tracks = get_spotify_playlist_tracks(url)
        elif 'spotify.com/album' in url:
            tracks = get_spotify_album_tracks(url)
        else:
            return jsonify({'error': 'Invalid URL'}), 400
        zip_buf = BytesIO()
        with zipfile.ZipFile(zip_buf, 'w') as zf:
            for t in tracks:
                path = download_track(t['name'], t['artist'], audio_format)
                with open(path, 'rb') as f:
                    zf.writestr(os.path.basename(path), f.read())
                time.sleep(0.5)  # Delay to ensure file is released
                os.remove(path)
        zip_buf.seek(0)
        return Response(zip_buf, mimetype='application/zip', headers={'Content-Disposition': 'attachment; filename=playlist.zip'})
    except Exception as e:
        logger.error(str(e))
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)