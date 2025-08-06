import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.middleware.proxy_fix import ProxyFix
from monitor import DormMonitor

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Initialize the monitor
monitor = DormMonitor()

@app.route('/')
def index():
    """Main dashboard page"""
    status = monitor.get_status()
    logs = monitor.get_logs()
    config = monitor.get_config()
    return render_template('index.html', status=status, logs=logs, config=config)

@app.route('/configure', methods=['POST'])
def configure():
    """Configure monitoring settings"""
    try:
        url = request.form.get('url', '').strip()
        bot_token = request.form.get('bot_token', '').strip()
        chat_id = request.form.get('chat_id', '').strip()
        check_interval = int(request.form.get('check_interval', 30))
        
        if not url:
            flash('URL is required', 'error')
            return redirect(url_for('index'))
        
        if not bot_token:
            flash('Bot Token is required', 'error')
            return redirect(url_for('index'))
        
        if not chat_id:
            flash('Chat ID is required', 'error')
            return redirect(url_for('index'))
        
        if check_interval < 10:
            flash('Check interval must be at least 10 seconds', 'error')
            return redirect(url_for('index'))
        
        monitor.configure(url, bot_token, chat_id, check_interval)
        flash('Configuration updated successfully!', 'success')
        
    except ValueError:
        flash('Invalid check interval. Please enter a number.', 'error')
    except Exception as e:
        flash(f'Configuration error: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/start', methods=['POST'])
def start_monitoring():
    """Start the monitoring process"""
    try:
        if monitor.start():
            flash('Monitoring started successfully!', 'success')
        else:
            flash('Unable to start monitoring. Please check your configuration.', 'error')
    except Exception as e:
        flash(f'Error starting monitoring: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/stop', methods=['POST'])
def stop_monitoring():
    """Stop the monitoring process"""
    try:
        monitor.stop()
        flash('Monitoring stopped.', 'info')
    except Exception as e:
        flash(f'Error stopping monitoring: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/manual_check', methods=['POST'])
def manual_check():
    """Trigger a manual check"""
    try:
        if monitor.manual_check():
            flash('Manual check completed. Check logs for results.', 'info')
        else:
            flash('Unable to perform manual check. Please configure the monitor first.', 'error')
    except Exception as e:
        flash(f'Error during manual check: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/clear_logs', methods=['POST'])
def clear_logs():
    """Clear the log history"""
    try:
        monitor.clear_logs()
        flash('Logs cleared successfully!', 'info')
    except Exception as e:
        flash(f'Error clearing logs: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/test_telegram', methods=['POST'])
def test_telegram():
    """Send a test Telegram message"""
    try:
        test_message = "🏠 Test message from Dorm Room Monitor!\n\nIf you receive this, your Telegram notifications are working correctly."
        if monitor.send_telegram_message(test_message):
            flash('Test notification sent! Check your Telegram.', 'success')
        else:
            flash('Failed to send test notification. Check your bot token and chat ID.', 'error')
    except Exception as e:
        flash(f'Error sending test notification: {str(e)}', 'error')
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
