import os
from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp
import threading
import time
import re
import random
from pathlib import Path
import urllib.parse

app = Flask(__name__)

# Environment variables for railway
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-123')
app.config['DOWNLOAD_FOLDER'] = os.environ.get('DOWNLOAD_FOLDER', 'downloads')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

# Create downloads folder
download_path = Path(app.config['DOWNLOAD_FOLDER'])
download_path.mkdir(exist_ok=True)

class DownloadManager:
    def __init__(self):
        self.downloads = {}
        # Multiple user agents to rotate
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]
    
    def get_random_user_agent(self):
        return random.choice(self.user_agents)
    
    def validate_url(self, url):
        """Validate YouTube URL"""
        youtube_patterns = [
            r'(https?://)?(www\.)?youtube\.com/watch\?v=([^&]+)',
            r'(https?://)?(www\.)?youtu\.be/([^?]+)',
            r'(https?://)?(www\.)?youtube\.com/embed/([^/?]+)'
        ]
        
        url = url.strip()
        for pattern in youtube_patterns:
            if re.match(pattern, url):
                return True
        return False
    
    def get_video_info(self, url):
        """Get video information with enhanced error handling"""
        try:
            if not self.validate_url(url):
                return {'error': 'Invalid YouTube URL format'}
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'extract_flat': False,
                'user_agent': self.get_random_user_agent(),
                'http_headers': {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                },
                'socket_timeout': 30,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    return {'error': 'Video unavailable or cannot be accessed'}
                
                # Check if video is available
                if info.get('availability') == 'unavailable':
                    return {'error': 'Video is unavailable in your region or has been removed'}
                
                video_info = {
                    'title': info.get('title', 'Unknown Title'),
                    'duration': self.format_duration(info.get('duration', 0)),
                    'thumbnail': info.get('thumbnail', ''),
                    'uploader': info.get('uploader', 'Unknown Uploader'),
                    'view_count': info.get('view_count', 0),
                }
                
                return video_info
                
        except Exception as e:
            error_msg = str(e).lower()
            if 'unavailable' in error_msg:
                return {'error': 'Video is unavailable or restricted'}
            elif 'private' in error_msg:
                return {'error': 'Video is private'}
            elif '403' in error_msg or 'forbidden' in error_msg:
                return {'error': 'YouTube is temporarily blocking requests. Please try again in a few minutes.'}
            else:
                return {'error': f'Error accessing video: {str(e)}'}
    
    def format_duration(self, seconds):
        """Format duration in seconds to MM:SS"""
        if not seconds:
            return "Unknown"
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"
    
    def download_video(self, url, format_type, quality, download_id):
        """Download video with enhanced error handling and retry logic"""
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
            
            # First get video info to verify accessibility
            video_info = self.get_video_info(url)
            if 'error' in video_info:
                self.downloads[download_id]['status'] = 'error'
                self.downloads[download_id]['error'] = video_info['error']
                return
            
            self.downloads[download_id]['video_title'] = video_info['title']
            self.downloads[download_id]['status'] = 'downloading'
            
            # Enhanced download configuration for railway
            ydl_opts = {
                'outtmpl': str(safe_download_folder / '%(title).100s.%(ext)s'),
                'progress_hooks': [lambda d: self.progress_hook(d, download_id)],
                'ignoreerrors': False,
                'no_warnings': True,
                'user_agent': self.get_random_user_agent(),
                'http_headers': {
                    'Accept': '*/*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Sec-Fetch-Dest': 'video',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'cross-site',
                    'Referer': 'https://www.youtube.com/',
                    'Origin': 'https://www.youtube.com',
                },
                'socket_timeout': 60,
                'retries': 10,
                'fragment_retries': 10,
                'skip_unavailable_fragments': True,
                'extract_flat': False,
            }
            
            # Set format based on user selection
            if format_type == 'mp3':
                ydl_opts.update({
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                })
            else:
                # For video, use simpler format selection
                ydl_opts['format'] = 'best[ext=mp4]/best[height<=720]/best'
            
            # Perform download with retry logic
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info_dict = ydl.extract_info(url, download=True)
                        actual_filename = ydl.prepare_filename(info_dict)
                        
                        # Handle file extension changes for audio
                        if format_type == 'mp3':
                            actual_filename = actual_filename.rsplit('.', 1)[0] + '.mp3'
                        
                        # Wait a moment for file to be completely written
                        time.sleep(2)
                        
                        # Verify file was created and is accessible
                        if self.verify_download_completion(actual_filename):
                            self.downloads[download_id]['status'] = 'completed'
                            self.downloads[download_id]['filename'] = actual_filename
                            self.downloads[download_id]['progress'] = 100
                            break
                        else:
                            if attempt == max_retries - 1:
                                self.downloads[download_id]['status'] = 'error'
                                self.downloads[download_id]['error'] = 'Download completed but file verification failed'
                            continue
                            
                except yt_dlp.DownloadError as e:
                    if '403' in str(e) or 'Forbidden' in str(e):
                        if attempt == max_retries - 1:
                            self.downloads[download_id]['status'] = 'error'
                            self.downloads[download_id]['error'] = 'YouTube is blocking requests from this server. Please try again later or use a different video.'
                        else:
                            # Change user agent for retry
                            ydl_opts['user_agent'] = self.get_random_user_agent()
                            continue
                    else:
                        self.downloads[download_id]['status'] = 'error'
                        self.downloads[download_id]['error'] = f'Download error: {str(e)}'
                        break
                except Exception as e:
                    self.downloads[download_id]['status'] = 'error'
                    self.downloads[download_id]['error'] = f'Unexpected error: {str(e)}'
                    break
                    
        except Exception as e:
            self.downloads[download_id]['status'] = 'error'
            self.downloads[download_id]['error'] = f'System error: {str(e)}'
    
    def verify_download_completion(self, filename):
        """Verify that download completed successfully"""
        try:
            file_path = Path(filename)
            if file_path.exists() and file_path.stat().st_size > 0:
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
        
        # Test if video is accessible first
        test_info = download_manager.get_video_info(url)
        if 'error' in test_info:
            return jsonify({'error': test_info['error']})
        
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
        return jsonify(download_manager.downloads[download_id])
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

@app.route('/health')
def health_check():
    """Health check endpoint for railway"""
    return jsonify({'status': 'healthy', 'message': 'Server is running'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
