import os
from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp
import threading
import time
import re
import random
from pathlib import Path

app = Flask(__name__)

# Environment variables for live deployment
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-123')
app.config['DOWNLOAD_FOLDER'] = os.environ.get('DOWNLOAD_FOLDER', 'downloads')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size

# Create downloads folder
download_path = Path(app.config['DOWNLOAD_FOLDER'])
download_path.mkdir(exist_ok=True)

class DownloadManager:
    def __init__(self):
        self.downloads = {}
    
    def validate_url(self, url):
        youtube_patterns = [
            r'(https?://)?(www\.)?youtube\.com/watch\?v=([^&]+)',
            r'(https?://)?(www\.)?youtu\.be/([^?]+)',
        ]
        url = url.strip()
        for pattern in youtube_patterns:
            if re.match(pattern, url):
                return True
        return False
    
    def get_video_info(self, url):
        try:
            if not self.validate_url(url):
                return {'error': 'Invalid YouTube URL'}
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    return {'error': 'Video not found'}
                
                return {
                    'title': info.get('title', 'Unknown Title'),
                    'duration': self.format_duration(info.get('duration', 0)),
                    'thumbnail': info.get('thumbnail', ''),
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count', 0),
                }
                
        except Exception as e:
            return {'error': f'Error: {str(e)}'}
    
    def format_duration(self, seconds):
        if not seconds: return "Unknown"
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"
    
    def download_video(self, url, format_type, quality, download_id):
        try:
            safe_download_folder = Path(app.config['DOWNLOAD_FOLDER']).absolute()
            safe_download_folder.mkdir(exist_ok=True)
            
            self.downloads[download_id] = {
                'status': 'downloading',
                'progress': 0,
                'filename': None,
                'error': None,
                'video_title': None
            }
            
            # Get video info first
            video_info = self.get_video_info(url)
            if 'error' in video_info:
                self.downloads[download_id]['status'] = 'error'
                self.downloads[download_id]['error'] = video_info['error']
                return
            
            self.downloads[download_id]['video_title'] = video_info['title']
            
            # Download configuration
            ydl_opts = {
                'outtmpl': str(safe_download_folder / '%(title).100s.%(ext)s'),
                'progress_hooks': [lambda d: self.progress_hook(d, download_id)],
                'ignoreerrors': False,
            }
            
            if format_type == 'mp3':
                ydl_opts.update({
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                    }],
                })
            else:
                ydl_opts['format'] = 'best[ext=mp4]/best'
            
            # Perform download
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info_dict)
                
                if format_type == 'mp3':
                    filename = filename.rsplit('.', 1)[0] + '.mp3'
                
                if Path(filename).exists():
                    self.downloads[download_id]['status'] = 'completed'
                    self.downloads[download_id]['filename'] = filename
                    self.downloads[download_id]['progress'] = 100
                else:
                    self.downloads[download_id]['status'] = 'error'
                    self.downloads[download_id]['error'] = 'Download failed'
                
        except Exception as e:
            self.downloads[download_id]['status'] = 'error'
            self.downloads[download_id]['error'] = f'Download error: {str(e)}'
    
    def progress_hook(self, d, download_id):
        if download_id not in self.downloads:
            return
        if d['status'] == 'downloading':
            if d.get('total_bytes'):
                percent = int((d['downloaded_bytes'] / d['total_bytes']) * 100)
                self.downloads[download_id]['progress'] = percent

download_manager = DownloadManager()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_info', methods=['POST'])
def get_video_info():
    url = request.json.get('url', '').strip()
    if not url:
        return jsonify({'error': 'Please enter a URL'})
    video_info = download_manager.get_video_info(url)
    return jsonify(video_info)

@app.route('/download', methods=['POST'])
def download_video():
    url = request.json.get('url', '').strip()
    format_type = request.json.get('format', 'mp4')
    quality = request.json.get('quality', 'best')
    
    if not url or not download_manager.validate_url(url):
        return jsonify({'error': 'Invalid URL'})
    
    download_id = f"dl_{int(time.time())}_{random.randint(1000, 9999)}"
    
    thread = threading.Thread(
        target=download_manager.download_video,
        args=(url, format_type, quality, download_id)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({'download_id': download_id})

@app.route('/progress/<download_id>')
def get_progress(download_id):
    if download_id in download_manager.downloads:
        return jsonify(download_manager.downloads[download_id])
    return jsonify({'error': 'Download not found'})

@app.route('/download_file/<download_id>')
def download_file(download_id):
    if download_id in download_manager.downloads:
        download_info = download_manager.downloads[download_id]
        if download_info['status'] == 'completed' and download_info['filename']:
            if Path(download_info['filename']).exists():
                filename = Path(download_info['filename']).name
                return send_file(
                    download_info['filename'],
                    as_attachment=True,
                    download_name=filename
                )
    return jsonify({'error': 'File not found'}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)