from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp
import os
import threading
import time
import re
import random
from pathlib import Path
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['DOWNLOAD_FOLDER'] = 'downloads'

# Create downloads folder with proper permissions
download_path = Path(app.config['DOWNLOAD_FOLDER'])
download_path.mkdir(exist_ok=True)

class DownloadManager:
    def __init__(self):
        self.downloads = {}
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
        ]
    
    def get_random_user_agent(self):
        return random.choice(self.user_agents)
    
    def validate_url(self, url):
        """Validate YouTube URL"""
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
        """Get video information"""
        try:
            if not self.validate_url(url):
                return {'error': 'Invalid YouTube URL format'}
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'user_agent': self.get_random_user_agent(),
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    return {'error': 'Could not fetch video information'}
                
                video_info = {
                    'title': info.get('title', 'Unknown Title'),
                    'duration': self.format_duration(info.get('duration', 0)),
                    'thumbnail': info.get('thumbnail', ''),
                    'uploader': info.get('uploader', 'Unknown Uploader'),
                    'view_count': info.get('view_count', 0),
                }
                
                return video_info
                
        except Exception as e:
            return {'error': f'Error: {str(e)}'}
    
    def format_duration(self, seconds):
        """Format duration in seconds to MM:SS"""
        if not seconds:
            return "Unknown"
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"
    
    def download_video(self, url, format_type, quality, download_id):
        """Download video with proper completion handling"""
        try:
            # Sanitize download path
            safe_download_folder = Path(app.config['DOWNLOAD_FOLDER']).absolute()
            safe_download_folder.mkdir(exist_ok=True)
            
            # Initialize download info
            self.downloads[download_id] = {
                'status': 'preparing',
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
            self.downloads[download_id]['status'] = 'downloading'
            
            # Configure download options
            ydl_opts = {
                'outtmpl': str(safe_download_folder / '%(title).100s.%(ext)s'),
                'progress_hooks': [lambda d: self.progress_hook(d, download_id)],
                'ignoreerrors': False,
                'no_warnings': True,
                'user_agent': self.get_random_user_agent(),
                'socket_timeout': 60,
                'retries': 3,
            }
            
            # Set format based on user selection
            if format_type == 'mp3':
                ydl_opts['format'] = 'bestaudio/best'
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                }]
            elif format_type == 'm4a':
                ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio'
            else:
                if quality == 'best':
                    ydl_opts['format'] = 'best[ext=mp4]/best'
                elif quality == '720p':
                    ydl_opts['format'] = 'best[height<=720][ext=mp4]'
                elif quality == '480p':
                    ydl_opts['format'] = 'best[height<=480][ext=mp4]'
                elif quality == '360p':
                    ydl_opts['format'] = 'best[height<=360][ext=mp4]'
                else:
                    ydl_opts['format'] = 'worst[ext=mp4]'
            
            # Perform download
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info_dict = ydl.extract_info(url, download=True)
                    actual_filename = ydl.prepare_filename(info_dict)
                    
                    # Handle file extension changes for audio
                    if format_type == 'mp3':
                        actual_filename = actual_filename.rsplit('.', 1)[0] + '.mp3'
                    elif format_type == 'm4a':
                        actual_filename = actual_filename.rsplit('.', 1)[0] + '.m4a'
                    
                    # Wait a moment for file to be completely written
                    time.sleep(1)
                    
                    # Verify file was created and is accessible
                    if self.verify_download_completion(actual_filename):
                        self.downloads[download_id]['status'] = 'completed'
                        self.downloads[download_id]['filename'] = actual_filename
                        self.downloads[download_id]['progress'] = 100
                        logger.info(f"Download completed successfully: {actual_filename}")
                    else:
                        self.downloads[download_id]['status'] = 'error'
                        self.downloads[download_id]['error'] = 'Download completed but file verification failed'
                        logger.error(f"File verification failed: {actual_filename}")
                        
                except Exception as e:
                    self.downloads[download_id]['status'] = 'error'
                    self.downloads[download_id]['error'] = f'Download error: {str(e)}'
                    logger.error(f"Download error: {str(e)}")
                    
        except Exception as e:
            self.downloads[download_id]['status'] = 'error'
            self.downloads[download_id]['error'] = f'System error: {str(e)}'
            logger.error(f"System error: {str(e)}")
    
    def verify_download_completion(self, filename):
        """Verify that download completed successfully"""
        try:
            file_path = Path(filename)
            if file_path.exists():
                if file_path.stat().st_size > 0:
                    with open(file_path, 'rb') as f:
                        f.read(100)
                    return True
            return False
        except:
            return False
    
    def progress_hook(self, d, download_id):
        """Update download progress with completion detection"""
        if download_id not in self.downloads:
            return
            
        if d['status'] == 'downloading':
            if d.get('total_bytes'):
                percent = int((d['downloaded_bytes'] / d['total_bytes']) * 100)
                self.downloads[download_id]['progress'] = percent
            elif d.get('total_bytes_estimate'):
                percent = int((d['downloaded_bytes'] / d['total_bytes_estimate']) * 100)
                self.downloads[download_id]['progress'] = min(percent, 99)
        
        elif d['status'] == 'finished':
            self.downloads[download_id]['progress'] = 100

download_manager = DownloadManager()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_info', methods=['POST'])
def get_video_info():
    try:
        url = request.json.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'Please enter a YouTube URL'})
        
        video_info = download_manager.get_video_info(url)
        return jsonify(video_info)
        
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'})

@app.route('/download', methods=['POST'])
def download_video():
    try:
        url = request.json.get('url', '').strip()
        format_type = request.json.get('format', 'mp4')
        quality = request.json.get('quality', 'best')
        
        if not url or not download_manager.validate_url(url):
            return jsonify({'error': 'Please enter a valid YouTube URL'})
        
        # Generate unique download ID
        download_id = f"dl_{int(time.time())}_{random.randint(1000, 9999)}"
        
        # Start download in separate thread
        thread = threading.Thread(
            target=download_manager.download_video,
            args=(url, format_type, quality, download_id)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'download_id': download_id,
            'message': 'Download started successfully'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to start download: {str(e)}'})

@app.route('/progress/<download_id>')
def get_progress(download_id):
    if download_id in download_manager.downloads:
        download_info = download_manager.downloads[download_id]
        
        if download_info['status'] == 'completed' and download_info['filename']:
            if not Path(download_info['filename']).exists():
                download_info['status'] = 'error'
                download_info['error'] = 'Downloaded file not found'
        
        return jsonify(download_info)
    return jsonify({'error': 'Download session not found'})

@app.route('/download_file/<download_id>')
def download_file(download_id):
    try:
        if download_id in download_manager.downloads:
            download_info = download_manager.downloads[download_id]
            if (download_info['status'] == 'completed' and 
                download_info['filename'] and 
                Path(download_info['filename']).exists()):
                
                filename = Path(download_info['filename']).name
                return send_file(
                    download_info['filename'],
                    as_attachment=True,
                    download_name=filename
                )
        
        return jsonify({'error': 'File not available for download'}), 404
        
    except Exception as e:
        return jsonify({'error': f'Download error: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
    