class YouTubeDownloader {
    constructor() {
        this.downloadForm = document.getElementById('downloadForm');
        this.urlInput = document.getElementById('url');
        this.formatSelect = document.getElementById('format');
        this.qualitySelect = document.getElementById('quality');
        this.downloadBtn = document.getElementById('downloadBtn');
        this.btnLoading = document.getElementById('btnLoading');
        this.videoInfo = document.getElementById('videoInfo');
        this.progressSection = document.getElementById('progressSection');
        this.errorMessage = document.getElementById('errorMessage');
        this.downloadTitle = document.getElementById('downloadTitle');
        this.clearBtn = document.getElementById('clearBtn');
        this.themeToggle = document.getElementById('themeToggle');
        
        this.currentDownloadId = null;
        this.progressCheckInterval = null;
        this.typingTimer = null;
        this.isCheckingVideo = false;
        
        this.initEventListeners();
        this.loadTheme();
        this.performSilentUpdateCheck(); // Check for updates on app start
    }
    
    initEventListeners() {
        this.downloadForm.addEventListener('submit', (e) => this.handleSubmit(e));
        this.urlInput.addEventListener('input', () => this.handleUrlInput());
        this.clearBtn.addEventListener('click', () => this.clearUrl());
        this.themeToggle.addEventListener('click', () => this.toggleTheme());
        
        // Auto-check URL when user stops typing (1 second delay)
        this.urlInput.addEventListener('input', () => {
            clearTimeout(this.typingTimer);
            this.showUrlCheckingIndicator();
            this.typingTimer = setTimeout(() => {
                this.getVideoInfo();
            }, 1000);
        });
        
        // Show checking indicator immediately when user focuses out
        this.urlInput.addEventListener('blur', () => {
            if (this.urlInput.value.trim() && !this.isCheckingVideo) {
                this.getVideoInfo();
            }
        });
    }
    
    async performSilentUpdateCheck() {
        // Silent update check when app loads (no UI feedback)
        try {
            await fetch('/check_update');
            console.log('Silent update check completed');
        } catch (error) {
            console.log('Silent update check failed (normal for first run)');
        }
    }
    
    showUrlCheckingIndicator() {
        const url = this.urlInput.value.trim();
        if (url && this.isValidYouTubeUrl(url)) {
            // Add checking class to input field
            this.urlInput.classList.add('checking');
            
            // Show checking text near the input
            this.hideVideoInfo();
            this.hideError();
        }
    }
    
    hideUrlCheckingIndicator() {
        this.urlInput.classList.remove('checking');
        this.urlInput.classList.remove('checking-success');
        this.urlInput.classList.remove('checking-error');
    }
    
    handleUrlInput() {
        // Show/hide clear button based on input
        if (this.urlInput.value.trim()) {
            this.clearBtn.style.display = 'block';
        } else {
            this.clearBtn.style.display = 'none';
            this.hideVideoInfo();
            this.hideUrlCheckingIndicator();
        }
    }
    
    clearUrl() {
        this.urlInput.value = '';
        this.clearBtn.style.display = 'none';
        this.hideVideoInfo();
        this.hideError();
        this.hideUrlCheckingIndicator();
        this.urlInput.focus();
    }
    
    async getVideoInfo() {
        const url = this.urlInput.value.trim();
        
        if (!url) {
            this.hideVideoInfo();
            this.hideUrlCheckingIndicator();
            return;
        }
        
        if (!this.isValidYouTubeUrl(url)) {
            this.showError('Please enter a valid YouTube URL');
            this.hideVideoInfo();
            this.urlInput.classList.add('checking-error');
            setTimeout(() => this.hideUrlCheckingIndicator(), 2000);
            return;
        }
        
        try {
            this.isCheckingVideo = true;
            this.showVideoCheckingAnimation();
            this.hideError();
            this.hideVideoInfo();
            
            const response = await fetch('/get_info', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url: url })
            });
            
            const data = await response.json();
            
            if (data.error) {
                this.showError(data.error);
                this.hideVideoInfo();
                this.urlInput.classList.add('checking-error');
                setTimeout(() => this.hideUrlCheckingIndicator(), 3000);
                return;
            }
            
            this.displayVideoInfo(data);
            this.hideError();
            this.urlInput.classList.add('checking-success');
            setTimeout(() => this.hideUrlCheckingIndicator(), 2000);
            
        } catch (error) {
            this.showError('Network error: Could not fetch video information');
            this.hideVideoInfo();
            this.urlInput.classList.add('checking-error');
            setTimeout(() => this.hideUrlCheckingIndicator(), 3000);
        } finally {
            this.isCheckingVideo = false;
            this.resetDownloadButton();
        }
    }
    
    showVideoCheckingAnimation() {
        // Create or show checking animation
        let checkingIndicator = document.getElementById('checkingIndicator');
        if (!checkingIndicator) {
            checkingIndicator = document.createElement('div');
            checkingIndicator.id = 'checkingIndicator';
            checkingIndicator.className = 'checking-indicator';
            checkingIndicator.innerHTML = `
                <div class="checking-animation">
                    <div class="checking-spinner"></div>
                    <span>Checking video availability...</span>
                </div>
            `;
            this.urlInput.parentNode.appendChild(checkingIndicator);
        }
        checkingIndicator.style.display = 'block';
        
        // Add pulse animation to input
        this.urlInput.classList.add('checking-pulse');
    }
    
    hideVideoCheckingAnimation() {
        const checkingIndicator = document.getElementById('checkingIndicator');
        if (checkingIndicator) {
            checkingIndicator.style.display = 'none';
        }
        this.urlInput.classList.remove('checking-pulse');
    }
    
    displayVideoInfo(info) {
        this.hideVideoCheckingAnimation();
        
        if (info.thumbnail) {
            document.getElementById('thumbnail').src = info.thumbnail;
            document.getElementById('thumbnail').style.display = 'block';
        } else {
            document.getElementById('thumbnail').style.display = 'none';
        }
        
        document.getElementById('videoTitle').textContent = info.title;
        document.getElementById('videoUploader').textContent = info.uploader;
        document.getElementById('videoDuration').textContent = info.duration;
        document.getElementById('videoViews').textContent = this.formatNumber(info.view_count);
        
        this.videoInfo.style.display = 'block';
        
        // Add success animation
        this.videoInfo.classList.add('show-success');
        setTimeout(() => {
            this.videoInfo.classList.remove('show-success');
        }, 2000);
        
        // Smooth scroll to video info
        setTimeout(() => {
            this.videoInfo.scrollIntoView({ 
                behavior: 'smooth', 
                block: 'center' 
            });
        }, 300);
    }
    
    hideVideoInfo() {
        this.videoInfo.style.display = 'none';
        this.hideVideoCheckingAnimation();
    }
    
    async handleSubmit(e) {
        e.preventDefault();
        
        const url = this.urlInput.value.trim();
        const format = this.formatSelect.value;
        const quality = this.qualitySelect.value;
        
        if (!url || !this.isValidYouTubeUrl(url)) {
            this.showError('Please enter a valid YouTube URL');
            return;
        }
        
        this.setDownloadButtonLoading(true);
        this.hideError();
        
        try {
            const response = await fetch('/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    url: url,
                    format: format,
                    quality: quality
                })
            });
            
            const data = await response.json();
            
            if (data.error) {
                this.showError(data.error);
                this.setDownloadButtonLoading(false);
                return;
            }
            
            this.currentDownloadId = data.download_id;
            this.startProgressTracking(this.currentDownloadId);
            
        } catch (error) {
            this.showError('Network error: Could not start download');
            this.setDownloadButtonLoading(false);
        }
    }
    
    startProgressTracking(downloadId) {
        this.showProgressSection();
        this.downloadTitle.textContent = 'Preparing Download...';
        
        let progressChecks = 0;
        const maxProgressChecks = 300;
        
        const checkProgress = async () => {
            try {
                const response = await fetch(`/progress/${downloadId}`);
                const progress = await response.json();
                
                if (progress.error) {
                    this.showError(progress.error);
                    this.stopProgressTracking();
                    this.setDownloadButtonLoading(false);
                    return;
                }
                
                this.updateProgressDisplay(progress);
                
                if (progress.status === 'completed') {
                    this.showDownloadComplete(progress);
                    this.stopProgressTracking();
                    this.setDownloadButtonLoading(false);
                } else if (progress.status === 'error') {
                    this.showError(progress.error || 'Download failed');
                    this.stopProgressTracking();
                    this.setDownloadButtonLoading(false);
                } else if (progressChecks >= maxProgressChecks) {
                    this.showError('Download timeout. Please try again.');
                    this.stopProgressTracking();
                    this.setDownloadButtonLoading(false);
                } else {
                    progressChecks++;
                    this.progressCheckInterval = setTimeout(checkProgress, 1000);
                }
                
            } catch (error) {
                console.error('Progress check error:', error);
                if (progressChecks < 10) {
                    progressChecks++;
                    this.progressCheckInterval = setTimeout(checkProgress, 2000);
                } else {
                    this.showError('Failed to check download progress');
                    this.stopProgressTracking();
                    this.setDownloadButtonLoading(false);
                }
            }
        };
        
        checkProgress();
    }
    
    updateProgressDisplay(progress) {
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        
        if (progress.video_title) {
            this.downloadTitle.textContent = `Downloading: ${progress.video_title}`;
        }
        
        progressFill.style.width = `${progress.progress}%`;
        progressText.textContent = `${progress.progress}%`;
        
        if (progress.status === 'downloading') {
            progressText.textContent = `${progress.progress}% - Downloading...`;
        } else if (progress.status === 'preparing') {
            progressText.textContent = 'Preparing download...';
        }
    }
    
    showDownloadComplete(progress) {
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        const downloadLink = document.getElementById('downloadLink');
        
        progressFill.style.width = '100%';
        progressText.textContent = '100% - Complete!';
        progressText.style.color = 'var(--secondary-color)';
        progressText.style.fontWeight = 'bold';
        
        const fileDownload = document.getElementById('fileDownload');
        fileDownload.href = `/download_file/${this.currentDownloadId}`;
        
        fileDownload.onclick = () => {
            setTimeout(() => {
                this.hideProgressSection();
            }, 2000);
        };
        
        downloadLink.style.display = 'block';
        this.downloadTitle.textContent = 'Download Complete!';
        this.downloadTitle.style.color = 'var(--secondary-color)';
        
        // Scroll to download link
        downloadLink.scrollIntoView({ behavior: 'smooth' });
    }
    
    showProgressSection() {
        this.progressSection.style.display = 'block';
        document.getElementById('progressFill').style.width = '0%';
        document.getElementById('progressText').textContent = '0%';
        document.getElementById('downloadLink').style.display = 'none';
        
        // Scroll to progress section
        this.progressSection.scrollIntoView({ behavior: 'smooth' });
    }
    
    hideProgressSection() {
        this.progressSection.style.display = 'none';
        this.currentDownloadId = null;
    }
    
    stopProgressTracking() {
        if (this.progressCheckInterval) {
            clearTimeout(this.progressCheckInterval);
            this.progressCheckInterval = null;
        }
    }
    
    setDownloadButtonLoading(loading) {
        if (loading) {
            this.downloadBtn.classList.add('loading');
            this.downloadBtn.disabled = true;
        } else {
            this.downloadBtn.classList.remove('loading');
            this.downloadBtn.disabled = false;
        }
    }
    
    showLoading() {
        this.downloadBtn.disabled = true;
    }
    
    resetDownloadButton() {
        this.downloadBtn.disabled = false;
    }
    
    isValidYouTubeUrl(url) {
        const youtubeRegex = /^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.?be)\/.+$/;
        return youtubeRegex.test(url);
    }
    
    formatNumber(num) {
        if (!num) return 'Unknown';
        return new Intl.NumberFormat().format(num);
    }
    
    showError(message) {
        this.hideVideoCheckingAnimation();
        this.errorMessage.innerHTML = `
            <i class='bx bx-error'></i>
            <span>${message}</span>
        `;
        this.errorMessage.style.display = 'flex';
        this.errorMessage.style.alignItems = 'center';
        this.errorMessage.style.gap = '10px';
        
        // Scroll to error message
        this.errorMessage.scrollIntoView({ behavior: 'smooth' });
    }
    
    hideError() {
        this.errorMessage.style.display = 'none';
    }
    
    toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        
        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        
        // Update theme button icon
        const icon = this.themeToggle.querySelector('i');
        icon.className = newTheme === 'dark' ? 'bx bx-moon' : 'bx bx-sun';
    }
    
    loadTheme() {
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
        
        // Set correct icon
        const icon = this.themeToggle.querySelector('i');
        icon.className = savedTheme === 'dark' ? 'bx bx-moon' : 'bx bx-sun';
    }
}

// Initialize the application when the page loads
document.addEventListener('DOMContentLoaded', () => {
    new YouTubeDownloader();
});