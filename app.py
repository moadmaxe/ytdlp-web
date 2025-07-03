from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import os
import uuid
import threading
import time
from datetime import datetime

app = Flask(__name__)

# Configuration
DOWNLOAD_DIR = 'downloads'
MAX_FILE_AGE = 3600  # 1 hour in seconds

# Create downloads directory
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Store download progress
download_progress = {}

def cleanup_old_files():
    """Remove old downloaded files"""
    while True:
        try:
            current_time = time.time()
            for filename in os.listdir(DOWNLOAD_DIR):
                file_path = os.path.join(DOWNLOAD_DIR, filename)
                if os.path.isfile(file_path):
                    if current_time - os.path.getmtime(file_path) > MAX_FILE_AGE:
                        os.remove(file_path)
        except Exception as e:
            print(f"Cleanup error: {e}")
        time.sleep(300)  # Check every 5 minutes

def progress_hook(d):
    """Progress hook for yt-dlp"""
    if d['status'] == 'downloading':
        download_id = d.get('info_dict', {}).get('id', 'unknown')
        if 'total_bytes' in d:
            percentage = (d['downloaded_bytes'] / d['total_bytes']) * 100
        elif 'total_bytes_estimate' in d:
            percentage = (d['downloaded_bytes'] / d['total_bytes_estimate']) * 100
        else:
            percentage = 0
        
        download_progress[download_id] = {
            'percentage': round(percentage, 2),
            'downloaded': d.get('downloaded_bytes', 0),
            'total': d.get('total_bytes', d.get('total_bytes_estimate', 0)),
            'speed': d.get('speed', 0),
            'eta': d.get('eta', 0)
        }
    elif d['status'] == 'finished':
        download_id = d.get('info_dict', {}).get('id', 'unknown')
        download_progress[download_id] = {
            'percentage': 100,
            'finished': True,
            'filename': d['filename']
        }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    try:
        data = request.json
        url = data.get('url')
        quality = data.get('quality', 'best')
        
        if not url:
            return jsonify({'error': 'No URL provided'}), 400
        
        # Generate unique filename
        unique_id = str(uuid.uuid4())[:8]
        
        # yt-dlp options
        ydl_opts = {
            'format': quality,
            'outtmpl': os.path.join(DOWNLOAD_DIR, f'{unique_id}_%(title)s.%(ext)s'),
            'progress_hooks': [progress_hook],
            'restrictfilenames': True,
            'noplaylist': True,
        }
        
        # Start download in background
        def download_video():
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            except Exception as e:
                print(f"Download error: {e}")
                download_progress[unique_id] = {
                    'error': str(e),
                    'finished': True
                }
        
        thread = threading.Thread(target=download_video)
        thread.daemon = True
        thread.start()
        
        return jsonify({'success': True, 'download_id': unique_id})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/progress/<download_id>')
def get_progress(download_id):
    progress = download_progress.get(download_id, {'percentage': 0})
    return jsonify(progress)

@app.route('/files')
def list_files():
    files = []
    try:
        for filename in os.listdir(DOWNLOAD_DIR):
            file_path = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.isfile(file_path):
                files.append({
                    'name': filename,
                    'size': os.path.getsize(file_path),
                    'modified': datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
                })
    except Exception as e:
        print(f"Error listing files: {e}")
    return jsonify(files)

@app.route('/download_file/<filename>')
def download_file(filename):
    try:
        file_path = os.path.join(DOWNLOAD_DIR, filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Start cleanup thread
    cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
    cleanup_thread.start()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)