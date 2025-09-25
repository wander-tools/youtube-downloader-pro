import os
from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp
import threading
import time
import random
from pathlib import Path
import requests
from urllib.parse import urlparse

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
app.config['DOWNLOAD_FOLDER'] = 'downloads'

# Create downloads folder
download_path = Path(app.config['DOWNLOAD_FOLDER'])
download_path.mkdir(exist_ok=True)

class MultiPlatformDownloader:
    def __init__(self):
        self.downloads = {}
        self.supported_platforms = {
            'youtube': [
                'youtube.com',
                'youtu.be',
                'www.youtube.com',
                'm.youtube.com'
            ],
            'dailymotion': [
                'dailymotion.com',
                'www.dailymotion.com'
            ],
            'vimeo': [
                'vimeo.com',
                'www.vimeo.com'
            ],
            'facebook': [
                'facebook.com',
                'www.facebook.com',
                'fb.watch'
            ]
        }
    
    def identify_platform(self, url):
        """Identify which platform the URL belongs to"""
        try:
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.lower()
            
            for platform, domains in self.supported_platforms.items():
                if any(d in domain for d in domains):
                    return platform
            
            return 'unknown'
        except:
            return 'unknown'
    
    def validate_url(self, url):
        """Validate if URL is from supported platform"""
        platform = self.identify_platform(url)
        return platform != 'unknown'
    
    def get_video_info(self, url):
        """Get video information with platform-specific handling"""
        try:
            if not self.validate_url(url):
                return {'error': 'Unsupported video platform. Supported: YouTube, DailyMotion, Vimeo'}
            
            platform = self.identify_platform(url)
            
            # Platform-specific configurations
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
            }
            
            # Add platform-specific options
            if platform == 'youtube':
                ydl_opts.update({
                    'extract_flat': False,
                    'socket_timeout': 30,
                })
            elif platform == 'dailymotion':
                ydl_opts.update({
                    'extract_flat': True,
                })
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    return {'error': 'Video not found or unavailable'}
                
                return {
                    'title': info.get('title', 'Unknown Title'),
                    'duration': self.format_duration(info.get('duration', 0)),
                    'thumbnail': info.get('thumbnail', ''),
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count', 0),
                    'platform': platform
                }
                
        except Exception as e:
            return {'error': f'Error: {str(e)}'}
    
    def format_duration(self, seconds):
        """Format duration"""
        if not seconds: return "Unknown"
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"
    
    def download_video(self, url, format_type, quality, download_id):
        """Download video with enhanced error handling"""
        try:
            platform = self.identify_platform(url)
            
            self.downloads[download_id] = {
                'status': 'downloading',
                'progress': 0,
                'filename': None,
                'error': None,
                'platform': platform
            }
            
            download_path = Path(app.config['DOWNLOAD_FOLDER'])
            download_path.mkdir(exist_ok=True)
            
            # Platform-specific download options
            ydl_opts = {
                'outtmpl': str(download_path / f'%(title).100s.%(ext)s'),
                'progress_hooks': [lambda d: self.progress_hook(d, download_id)],
                'ignoreerrors': False,
            }
            
            # For non-YouTube platforms, use simpler approach
            if platform != 'youtube':
                ydl_opts.update({
                    'format': 'best',
                    'no_check_certificate': True,
                })
            else:
                # For YouTube, try multiple approaches
                ydl_opts.update({
                    'format': 'best[ext=mp4]/best',
                    'retries': 3,
                    'fragment_retries': 3,
                })
            
            if format_type == 'mp3':
                ydl_opts.update({
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                    }],
                })
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                
                if format_type == 'mp3':
                    filename = filename.rsplit('.', 1)[0] + '.mp3'
                
                if Path(filename).exists():
                    self.downloads[download_id]['status'] = 'completed'
                    self.downloads[download_id]['filename'] = filename
                else:
                    self.downloads[download_id]['status'] = 'error'
                    self.downloads[download_id]['error'] = 'Download failed - file not created'
                    
        except Exception as e:
            error_msg = str(e)
            if '403' in error_msg or 'Forbidden' in error_msg:
                self.downloads[download_id]['error'] = (
                    f'{platform.capitalize()} is blocking requests. ' 
                    f'Try a different video or platform like DailyMotion/Vimeo.'
                )
            else:
                self.downloads[download_id]['error'] = f'Download error: {error_msg}'
    
    def progress_hook(self, d, download_id):
        """Update progress"""
        if download_id in self.downloads and d['status'] == 'downloading':
            if d.get('total_bytes'):
                percent = int((d['downloaded_bytes'] / d['total_bytes']) * 100)
                self.downloads[download_id]['progress'] = percent

downloader = MultiPlatformDownloader()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_info', methods=['POST'])
def get_video_info():
    url = request.json.get('url', '').strip()
    if not url:
        return jsonify({'error': 'Please enter a video URL'})
    
    info = downloader.get_video_info(url)
    return jsonify(info)

@app.route('/download', methods=['POST'])
def download_video():
    url = request.json.get('url', '').strip()
    format_type = request.json.get('format', 'mp4')
    quality = request.json.get('quality', 'best')
    
    if not url or not downloader.validate_url(url):
        return jsonify({'error': 'Please enter a valid video URL'})
    
    download_id = f"dl_{int(time.time())}_{random.randint(1000, 9999)}"
    
    thread = threading.Thread(
        target=downloader.download_video,
        args=(url, format_type, quality, download_id)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({'download_id': download_id})

@app.route('/progress/<download_id>')
def get_progress(download_id):
    if download_id in downloader.downloads:
        return jsonify(downloader.downloads[download_id])
    return jsonify({'error': 'Download not found'})

@app.route('/download_file/<download_id>')
def download_file(download_id):
    if download_id in downloader.downloads:
        info = downloader.downloads[download_id]
        if info['status'] == 'completed' and info['filename']:
            if Path(info['filename']).exists():
                return send_file(info['filename'], as_attachment=True)
    return jsonify({'error': 'File not found'}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
