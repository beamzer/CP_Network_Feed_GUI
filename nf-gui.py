#!/usr/bin/env python3
from flask import Flask, request, redirect, render_template_string, flash, url_for
import os, shutil, datetime, ipaddress

app = Flask(__name__)
app.secret_key = 'changeme'

# Configuration - use absolute paths based on script location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IP_FILE = os.path.join(SCRIPT_DIR, 'allowed_ips.txt')
VERSIONS_DIR = os.path.join(SCRIPT_DIR, 'versions')

# Make sure the versions directory exists
try:
    if not os.path.exists(VERSIONS_DIR):
        os.makedirs(VERSIONS_DIR)
except OSError as e:
    print(f"Error creating versions directory: {e}")
    # Fallback to a temporary directory if we can't create in script dir
    import tempfile
    VERSIONS_DIR = os.path.join(tempfile.gettempdir(), 'nf_gui_versions')
    if not os.path.exists(VERSIONS_DIR):
        os.makedirs(VERSIONS_DIR)

def load_ips():
    """Read the list of IP addresses from the file."""
    if not os.path.exists(IP_FILE):
        return []
    with open(IP_FILE, 'r') as f:
        return [line.strip() for line in f if line.strip()]

def save_ips(ips):
    """Before saving, archive the current file to a versioned copy, then write new content."""
    # Backup current file if exists
    if os.path.exists(IP_FILE):
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = os.path.join(VERSIONS_DIR, f'allowed_ips_{timestamp}.txt')
        shutil.copy2(IP_FILE, backup_name)
    # Write the new file
    with open(IP_FILE, 'w') as f:
        for ip in ips:
            f.write(ip + "\n")

def is_valid_ip(address):
    try:
        ipaddress.ip_address(address)
        return True
    except ValueError:
        return False

# A basic template using render_template_string for illustration.
# In a production app, use proper template files.
HTML_TEMPLATE = """
<!doctype html>
<html>
<head>
    <title>Network Feed Editor</title>
</head>
<body>
    <h1>Allowed IPs</h1>
    <ul>
      {% for ip in ip_list %}
        <li>{{ ip }} 
            <form action="{{ url_for('delete_ip') }}" method="post" style="display:inline;">
                <input type="hidden" name="ip" value="{{ ip }}">
                <button type="submit">Delete</button>
            </form>
         </li>
      {% endfor %}
    </ul>

    <h2>Add IP</h2>
    <form method="post" action="{{ url_for('add_ip') }}">
        <input type="text" name="ip" placeholder="Enter IP address">
        <button type="submit">Add</button>
    </form>

    <p><a href="{{ url_for('versions') }}">View Versions / Rollback</a></p>

    {% with messages = get_flashed_messages() %}
      {% if messages %}
         <ul>
         {% for message in messages %}
           <li>{{ message }}</li>
         {% endfor %}
         </ul>
      {% endif %}
    {% endwith %}

</body>
</html>
"""

@app.route('/')
def index():
    ips = load_ips()
    return render_template_string(HTML_TEMPLATE, ip_list=ips)

@app.route('/add', methods=['POST'])
def add_ip():
    ip = request.form.get('ip', '').strip()
    if not ip:
        flash("No IP address provided.")
        return redirect(url_for('index'))

    if not is_valid_ip(ip):
        flash(f"{ip} is not a valid IP address.")
        return redirect(url_for('index'))

    ips = load_ips()
    # Allow duplicates? If not, uncomment the next two lines.
    if ip in ips:
        flash(f"{ip} is already in the list.")
        return redirect(url_for('index'))

    ips.append(ip)
    save_ips(ips)
    flash(f"Added IP {ip}.")
    return redirect(url_for('index'))

@app.route('/delete', methods=['POST'])
def delete_ip():
    ip_to_delete = request.form.get('ip', '').strip()
    ips = load_ips()
    if ip_to_delete not in ips:
        flash(f"IP {ip_to_delete} not found.")
        return redirect(url_for('index'))

    ips.remove(ip_to_delete)
    save_ips(ips)
    flash(f"Deleted IP {ip_to_delete}.")
    return redirect(url_for('index'))

# Endpoint to list version backups and rollback to a chosen version.
@app.route('/versions', methods=['GET', 'POST'])
def versions():
    backups = sorted(os.listdir(VERSIONS_DIR), reverse=True)
    if request.method == 'POST':
        version_file = request.form.get('version_file')
        if version_file and version_file in backups:
            # Copy the backup file to our main file.
            backup_path = os.path.join(VERSIONS_DIR, version_file)
            shutil.copy2(backup_path, IP_FILE)
            flash(f"Rolled back to version {version_file}.")
            return redirect(url_for('index'))
        else:
            flash("Invalid version selected.")
            return redirect(url_for('versions'))

    # Simple HTML for versions list.
    version_html = """
    <!doctype html>
    <html>
    <head>
        <title>Versions</title>
    </head>
    <body>
        <h1>Available Versions</h1>
        <form method="post">
        <ul>
            {% for bf in backups %}
              <li>
                {{ bf }} 
                <button type="submit" name="version_file" value="{{ bf }}">Rollback to this version</button>
              </li>
            {% endfor %}
        </ul>
        </form>
        <p><a href="{{ url_for('index') }}">Back to main view</a></p>
    </body>
    </html>
    """
    return render_template_string(version_html, backups=backups)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
