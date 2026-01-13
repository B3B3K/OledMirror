from flask import Flask, request, jsonify, Response
import socket
import io
import threading
import time
import mss
import mss.tools
import numpy as np
from PIL import Image
import queue
import json

# This is the entire Web Interface (HTML, CSS, and JS)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ESP32-C3 OLED Screen Streamer</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: #0f172a; color: #f8fafc;
            min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 20px;
        }
        .card {
            background: #1e293b; border-radius: 16px; padding: 32px;
            width: 100%; max-width: 600px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5);
        }
        h1 { font-size: 1.5rem; margin-bottom: 8px; text-align: center; color: #38bdf8; }
        p.subtitle { font-size: 0.875rem; color: #94a3b8; text-align: center; margin-bottom: 24px; }
        
        .field { margin-bottom: 16px; }
        label { display: block; font-size: 0.875rem; font-weight: 600; margin-bottom: 6px; color: #cbd5e1; }
        input, select {
            width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #334155;
            background: #0f172a; color: white; outline: none;
        }
        input:focus { border-color: #38bdf8; }

        .btn-group {
            display: flex; gap: 10px; margin-bottom: 20px;
        }
        .btn {
            flex: 1; padding: 12px; border-radius: 8px; border: none;
            background: #0284c7; color: white; font-weight: 600; cursor: pointer; transition: 0.2s;
        }
        .btn:hover:not(:disabled) { background: #0369a1; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn.secondary { background: #475569; }
        .btn.secondary:hover { background: #334155; }
        .btn.danger { background: #dc2626; }
        .btn.danger:hover { background: #b91c1c; }
        .btn.success { background: #059669; }
        .btn.success:hover { background: #047857; }
        
        .preview-area {
            text-align: center; margin-bottom: 20px; 
            background: #0f172a; border-radius: 8px; padding: 15px;
        }
        canvas { 
            background: #000; border: 1px solid #38bdf8; 
            image-rendering: pixelated; width: 256px; height: 128px; 
        }
        .live-preview {
            display: flex; justify-content: center; gap: 20px; flex-wrap: wrap;
        }
        .preview-box {
            background: #0f172a; padding: 10px; border-radius: 8px; margin-bottom: 10px;
        }
        .preview-box h3 {
            font-size: 0.9rem; margin-bottom: 8px; color: #cbd5e1;
        }
        
        .status { 
            margin-top: 16px; padding: 10px; border-radius: 6px; font-size: 0.875rem; 
            text-align: center; display: none; 
        }
        .success { background: #065f46; color: #a7f3d0; }
        .error { background: #7f1d1d; color: #fecaca; }
        .info { background: #1e3a8a; color: #dbeafe; }
        
        .controls {
            display: flex; gap: 10px; margin-bottom: 15px;
        }
        .control-group {
            flex: 1;
        }
        .slider-container {
            display: flex; align-items: center; gap: 10px;
        }
        .slider-container input {
            flex: 1;
        }
        .slider-container span {
            min-width: 40px; text-align: center; font-size: 0.9rem;
        }
        
        .stats {
            display: flex; justify-content: space-between; margin-top: 15px;
            font-size: 0.8rem; color: #94a3b8;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>OLED Screen Streamer</h1>
        <p class="subtitle">Live screen capture to ESP32-C3 OLED</p>

        <div class="field">
            <label>ESP32 IP Address</label>
            <input type="text" id="espIp" placeholder="e.g. 192.168.1.50" value="192.168.1.100">
        </div>

        <div class="controls">
            <div class="control-group">
                <label>FPS</label>
                <div class="slider-container">
                    <input type="range" id="fpsSlider" min="1" max="30" value="10">
                    <span id="fpsValue">10</span>
                </div>
            </div>
            <div class="control-group">
                <label>Quality</label>
                <div class="slider-container">
                    <input type="range" id="qualitySlider" min="1" max="100" value="50">
                    <span id="qualityValue">50</span>
                </div>
            </div>
        </div>

        <div class="btn-group">
            <button class="btn" id="captureBtn">Capture Screen</button>
            <button class="btn secondary" id="streamBtn">Start Stream</button>
            <button class="btn danger" id="stopBtn" disabled>Stop Stream</button>
        </div>

        <div class="preview-area">
            <div class="live-preview">
                <div class="preview-box">
                    <h3>Original Preview</h3>
                    <canvas id="originalCanvas" width="320" height="180"></canvas>
                </div>
                <div class="preview-box">
                    <h3>OLED Preview (128x64)</h3>
                    <canvas id="oledCanvas" width="256" height="128"></canvas>
                </div>
            </div>
            
            <div class="stats">
                <div>Resolution: <span id="resStat">-</span></div>
                <div>FPS: <span id="fpsStat">0</span></div>
                <div>Status: <span id="statusText">Ready</span></div>
            </div>
        </div>

        <div class="field">
            <label>Screen Region (drag on original preview)</label>
            <input type="text" id="regionInput" placeholder="0,0,1920,1080" readonly>
        </div>

        <div id="status" class="status"></div>
    </div>

    <script>
        const espIp = document.getElementById('espIp');
        const fpsSlider = document.getElementById('fpsSlider');
        const fpsValue = document.getElementById('fpsValue');
        const qualitySlider = document.getElementById('qualitySlider');
        const qualityValue = document.getElementById('qualityValue');
        const captureBtn = document.getElementById('captureBtn');
        const streamBtn = document.getElementById('streamBtn');
        const stopBtn = document.getElementById('stopBtn');
        const originalCanvas = document.getElementById('originalCanvas');
        const oledCanvas = document.getElementById('oledCanvas');
        const regionInput = document.getElementById('regionInput');
        const statusDiv = document.getElementById('status');
        const resStat = document.getElementById('resStat');
        const fpsStat = document.getElementById('fpsStat');
        const statusText = document.getElementById('statusText');
        
        const oledCtx = oledCanvas.getContext('2d');
        const originalCtx = originalCanvas.getContext('2d');
        
        let isStreaming = false;
        let streamInterval = null;
        let frameCount = 0;
        let lastFpsTime = Date.now();
        let selectedRegion = null;
        let isSelecting = false;
        let selectionStart = null;
        
        // Update slider values
        fpsSlider.oninput = () => fpsValue.textContent = fpsSlider.value;
        qualitySlider.oninput = () => qualityValue.textContent = qualitySlider.value;
        
        // Region selection on original canvas
        originalCanvas.addEventListener('mousedown', (e) => {
            if (!isStreaming) {
                const rect = originalCanvas.getBoundingClientRect();
                selectionStart = {
                    x: e.clientX - rect.left,
                    y: e.clientY - rect.top
                };
                isSelecting = true;
            }
        });
        
        originalCanvas.addEventListener('mousemove', (e) => {
            if (isSelecting && selectionStart) {
                const rect = originalCanvas.getBoundingClientRect();
                const currentX = e.clientX - rect.left;
                const currentY = e.clientY - rect.top;
                
                // Draw selection rectangle
                originalCtx.clearRect(0, 0, originalCanvas.width, originalCanvas.height);
                originalCtx.drawImage(lastCapturedImage, 0, 0, originalCanvas.width, originalCanvas.height);
                originalCtx.strokeStyle = '#38bdf8';
                originalCtx.lineWidth = 2;
                originalCtx.strokeRect(
                    selectionStart.x, selectionStart.y,
                    currentX - selectionStart.x, currentY - selectionStart.y
                );
            }
        });
        
        originalCanvas.addEventListener('mouseup', (e) => {
            if (isSelecting && selectionStart) {
                const rect = originalCanvas.getBoundingClientRect();
                const endX = e.clientX - rect.left;
                const endY = e.clientY - rect.top;
                
                // Calculate actual screen coordinates
                const scaleX = lastScreenWidth / originalCanvas.width;
                const scaleY = lastScreenHeight / originalCanvas.height;
                
                selectedRegion = {
                    x: Math.round(Math.min(selectionStart.x, endX) * scaleX),
                    y: Math.round(Math.min(selectionStart.y, endY) * scaleY),
                    width: Math.round(Math.abs(endX - selectionStart.x) * scaleX),
                    height: Math.round(Math.abs(endY - selectionStart.y) * scaleY)
                };
                
                regionInput.value = `${selectedRegion.x},${selectedRegion.y},${selectedRegion.width},${selectedRegion.height}`;
                isSelecting = false;
                selectionStart = null;
                
                showStatus(`Region selected: ${selectedRegion.width}x${selectedRegion.height}`, 'info');
            }
        });
        
        let lastCapturedImage = null;
        let lastScreenWidth = 0;
        let lastScreenHeight = 0;
        
        async function captureScreen() {
            try {
                const response = await fetch('/capture');
                const blob = await response.blob();
                const img = await createImageBitmap(blob);
                
                lastCapturedImage = img;
                lastScreenWidth = img.width;
                lastScreenHeight = img.height;
                
                // Draw to original canvas
                originalCtx.clearRect(0, 0, originalCanvas.width, originalCanvas.height);
                originalCtx.drawImage(img, 0, 0, originalCanvas.width, originalCanvas.height);
                
                resStat.textContent = `${img.width}x${img.height}`;
                showStatus('Screen captured successfully', 'success');
                
                // Process for OLED preview
                processForOLED(img);
                
                return img;
            } catch (error) {
                showStatus(`Capture failed: ${error.message}`, 'error');
                return null;
            }
        }
        
        function processForOLED(img) {
            // Create temp canvas for processing
            const tempCanvas = document.createElement('canvas');
            tempCanvas.width = 128;
            tempCanvas.height = 48; // Bottom 48px for image area
            const tempCtx = tempCanvas.getContext('2d');
            
            // Clear with black
            tempCtx.fillStyle = 'black';
            tempCtx.fillRect(0, 0, 128, 48);
            
            // Calculate scaling
            const sourceRegion = selectedRegion || {
                x: 0, y: 0, width: img.width, height: img.height
            };
            
            const scale = Math.min(128 / sourceRegion.width, 48 / sourceRegion.height);
            const dw = sourceRegion.width * scale;
            const dh = sourceRegion.height * scale;
            const dx = (128 - dw) / 2;
            const dy = (48 - dh) / 2;
            
            // Draw image
            tempCtx.drawImage(
                img, 
                sourceRegion.x, sourceRegion.y, sourceRegion.width, sourceRegion.height,
                dx, dy, dw, dh
            );
            
            // Convert to grayscale and dither
            const imgData = tempCtx.getImageData(0, 0, 128, 48);
            const gray = new Float32Array(128 * 48);
            
            for(let i = 0; i < imgData.data.length; i += 4) {
                gray[i/4] = imgData.data[i] * 0.299 + 
                           imgData.data[i+1] * 0.587 + 
                           imgData.data[i+2] * 0.114;
            }
            
            // Floyd-Steinberg Dithering
            for(let i = 0; i < gray.length; i++) {
                const oldP = gray[i];
                const newP = oldP > 127 ? 255 : 0;
                gray[i] = newP;
                const err = oldP - newP;
                const x = i % 128;
                
                if (x < 127) gray[i+1] += err * 7/16;
                if (i + 127 < gray.length) gray[i+127] += err * 3/16;
                if (i + 128 < gray.length) gray[i+128] += err * 5/16;
                if (i + 129 < gray.length && x < 127) gray[i+129] += err * 1/16;
            }
            
            // Build OLED buffer (SSD1306 Page Format)
            const buffer = new Uint8Array(1024);
            
            // Fill image data (pages 2-7)
            for (let p = 2; p < 8; p++) {
                for (let x = 0; x < 128; x++) {
                    let byte = 0;
                    for (let bit = 0; bit < 8; bit++) {
                        const y = (p - 2) * 8 + bit;
                        if (gray[y * 128 + x] > 127) byte |= (1 << bit);
                    }
                    buffer[p * 128 + x] = byte;
                }
            }
            
            // Render OLED preview
            renderOLEDPreview(buffer);
            
            return buffer;
        }
        
        function renderOLEDPreview(buffer) {
            const ctx = oledCtx;
            const view = ctx.createImageData(128, 64);
            
            for(let y = 0; y < 64; y++) {
                for(let x = 0; x < 128; x++) {
                    const p = Math.floor(y / 8);
                    const b = y % 8;
                    const i = (y * 128 + x) * 4;
                    
                    const on = (buffer[p * 128 + x] & (1 << b)) !== 0;
                    
                    if (y < 16) { // Status bar area
                        view.data[i] = 30;
                        view.data[i+1] = 30;
                        view.data[i+2] = 50;
                    } else { // Image area
                        const v = on ? 255 : 0;
                        view.data[i] = v;
                        view.data[i+1] = v;
                        view.data[i+2] = v;
                    }
                    view.data[i+3] = 255;
                }
            }
            
            ctx.putImageData(view, 0, 0);
        }
        
        async function sendFrame(buffer) {
            try {
                const response = await fetch('/send', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        ip: espIp.value, 
                        data: Array.from(buffer) 
                    })
                });
                
                if (!response.ok) throw new Error('Send failed');
                return true;
            } catch (error) {
                console.error('Frame send error:', error);
                return false;
            }
        }
        
        function startStream() {
            if (isStreaming) return;
            
            isStreaming = true;
            captureBtn.disabled = true;
            streamBtn.disabled = true;
            stopBtn.disabled = false;
            statusText.textContent = 'Streaming...';
            
            const fps = parseInt(fpsSlider.value);
            const interval = 1000 / fps;
            
            streamInterval = setInterval(async () => {
                const img = await captureScreen();
                if (img) {
                    const buffer = processForOLED(img);
                    await sendFrame(buffer);
                    
                    // Update FPS counter
                    frameCount++;
                    const now = Date.now();
                    if (now - lastFpsTime >= 1000) {
                        fpsStat.textContent = frameCount;
                        frameCount = 0;
                        lastFpsTime = now;
                    }
                }
            }, interval);
            
            showStatus('Stream started', 'success');
        }
        
        function stopStream() {
            if (!isStreaming) return;
            
            isStreaming = false;
            clearInterval(streamInterval);
            
            captureBtn.disabled = false;
            streamBtn.disabled = false;
            stopBtn.disabled = true;
            statusText.textContent = 'Stopped';
            fpsStat.textContent = '0';
            
            showStatus('Stream stopped', 'info');
        }
        
        function showStatus(message, type = 'info') {
            statusDiv.textContent = message;
            statusDiv.className = `status ${type}`;
            statusDiv.style.display = 'block';
            
            setTimeout(() => {
                statusDiv.style.display = 'none';
            }, 3000);
        }
        
        // Event listeners
        captureBtn.addEventListener('click', captureScreen);
        
        streamBtn.addEventListener('click', () => {
            if (!isStreaming) startStream();
        });
        
        stopBtn.addEventListener('click', stopStream);
        
        // Initial capture
        captureScreen();
        
        // Cleanup on page unload
        window.addEventListener('beforeunload', () => {
            if (isStreaming) {
                fetch('/stop_stream', { method: 'POST' });
            }
        });
    </script>
</body>
</html>
"""

app = Flask(__name__)

# Global variables for screen capture
streaming = False
stream_thread = None
stop_event = threading.Event()
frame_queue = queue.Queue(maxsize=10)

def dither_image(image):
    """Convert image to 1-bit dithered using Floyd-Steinberg algorithm."""
    # Convert to grayscale
    gray = image.convert('L')
    gray_array = np.array(gray, dtype=np.float32)
    
    # Apply Floyd-Steinberg dithering
    height, width = gray_array.shape
    for y in range(height):
        for x in range(width):
            old_pixel = gray_array[y, x]
            new_pixel = 255 if old_pixel > 127 else 0
            gray_array[y, x] = new_pixel
            quant_error = old_pixel - new_pixel
            
            if x + 1 < width:
                gray_array[y, x + 1] += quant_error * 7/16
            if y + 1 < height:
                if x > 0:
                    gray_array[y + 1, x - 1] += quant_error * 3/16
                gray_array[y + 1, x] += quant_error * 5/16
                if x + 1 < width:
                    gray_array[y + 1, x + 1] += quant_error * 1/16
    
    # Convert back to image
    return Image.fromarray(gray_array.astype(np.uint8))

def process_for_oled(image, target_width=128, target_height=48):
    """Process image for OLED display (128x48 image area)."""
    # Scale image to fit target dimensions while maintaining aspect ratio
    img_ratio = image.width / image.height
    target_ratio = target_width / target_height
    
    if img_ratio > target_ratio:
        # Image is wider
        new_width = target_width
        new_height = int(target_width / img_ratio)
    else:
        # Image is taller
        new_height = target_height
        new_width = int(target_height * img_ratio)
    
    # Resize image
    resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Create new image with black background
    result = Image.new('L', (target_width, target_height), 0)
    
    # Paste resized image in center
    paste_x = (target_width - new_width) // 2
    paste_y = (target_height - new_height) // 2
    result.paste(resized, (paste_x, paste_y))
    
    # Apply dithering
    dithered = dither_image(result)
    
    # Convert to OLED buffer format (1024 bytes)
    buffer = bytearray(1024)
    
    # Fill image data (pages 2-7, bytes 256-1023)
    pixels = dithered.load()
    for page in range(2, 8):
        for x in range(128):
            byte = 0
            for bit in range(8):
                y = (page - 2) * 8 + bit
                if y < target_height:  # Safety check
                    pixel_value = pixels[x, y]
                    if pixel_value > 127:
                        byte |= (1 << bit)
            buffer[page * 128 + x] = byte
    
    return bytes(buffer)

def screen_capture_thread(ip, fps, quality):
    """Thread for continuous screen capture and streaming."""
    with mss.mss() as sct:
        # Get all monitors
        monitors = sct.monitors
        monitor = monitors[1]  # Primary monitor (index 1)
        
        # UDP socket for sending
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        last_frame_time = time.time()
        frame_interval = 1.0 / fps
        
        while not stop_event.is_set():
            try:
                current_time = time.time()
                if current_time - last_frame_time >= frame_interval:
                    # Capture screen
                    screenshot = sct.grab(monitor)
                    
                    # Convert to PIL Image
                    img = Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')
                    
                    # Process for OLED
                    oled_buffer = process_for_oled(img)
                    
                    # Send to ESP32
                    sock.sendto(oled_buffer, (ip, 8888))
                    
                    # Put in queue for web preview
                    try:
                        # Convert to JPEG for web preview
                        img_jpeg = io.BytesIO()
                        img.save(img_jpeg, 'JPEG', quality=quality)
                        frame_queue.put(img_jpeg.getvalue(), block=False)
                    except queue.Full:
                        pass  # Skip if queue is full
                    
                    last_frame_time = current_time
                
                # Small sleep to prevent CPU overuse
                time.sleep(0.001)
                
            except Exception as e:
                print(f"Screen capture error: {e}")
                time.sleep(1)  # Wait before retrying
    
    sock.close()

@app.route('/')
def home():
    return HTML_TEMPLATE

@app.route('/capture')
def capture():
    """Capture a single screen frame."""
    try:
        with mss.mss() as sct:
            monitors = sct.monitors
            screenshot = sct.grab(monitors[1])  # Primary monitor
            
            # Convert to JPEG
            img = Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')
            img_io = io.BytesIO()
            img.save(img_io, 'JPEG', quality=80)
            img_io.seek(0)
            
            return Response(img_io.getvalue(), mimetype='image/jpeg')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/send', methods=['POST'])
def send():
    """Send a single frame to ESP32."""
    try:
        req = request.json
        ip = req.get('ip')
        img_list = req.get('data')
        
        if not ip or len(img_list) != 1024:
            return jsonify({'success': False, 'error': 'Invalid data'}), 400

        # Create UDP socket and send
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(bytes(img_list), (ip, 8888))
        sock.close()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/start_stream', methods=['POST'])
def start_stream():
    """Start continuous screen streaming."""
    global streaming, stream_thread, stop_event
    
    if streaming:
        return jsonify({'success': False, 'error': 'Already streaming'}), 400
    
    try:
        req = request.json
        ip = req.get('ip', '192.168.1.100')
        fps = req.get('fps', 10)
        quality = req.get('quality', 50)
        
        # Reset stop event
        stop_event.clear()
        
        # Start capture thread
        stream_thread = threading.Thread(
            target=screen_capture_thread,
            args=(ip, fps, quality),
            daemon=True
        )
        stream_thread.start()
        
        streaming = True
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/stop_stream', methods=['POST'])
def stop_stream():
    """Stop screen streaming."""
    global streaming, stop_event
    
    if not streaming:
        return jsonify({'success': False, 'error': 'Not streaming'}), 400
    
    stop_event.set()
    streaming = False
    
    # Clear the frame queue
    while not frame_queue.empty():
        try:
            frame_queue.get_nowait()
        except:
            pass
    
    return jsonify({'success': True})

@app.route('/stream_feed')
def stream_feed():
    """SSE endpoint for streaming frames to web client."""
    def generate():
        while streaming:
            try:
                frame = frame_queue.get(timeout=1)
                yield f"data: {frame.hex()}\n\n"
            except queue.Empty:
                yield ":keepalive\n\n"
            except Exception:
                break
    
    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

@app.route('/status')
def status():
    """Get streaming status."""
    return jsonify({
        'streaming': streaming,
        'queue_size': frame_queue.qsize()
    })

if __name__ == '__main__':
    print("-" * 50)
    print("OLED Screen Streamer Running at http://localhost:5000")
    print("Features:")
    print("  • Live screen capture")
    print("  • Region selection")
    print("  • Adjustable FPS (1-30)")
    print("  • Adjustable quality")
    print("  • Real-time preview")
    print("-" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)