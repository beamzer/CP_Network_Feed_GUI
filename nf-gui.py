#!/usr/bin/env python3
from flask import Flask, request, redirect, render_template_string, flash, url_for
import os, shutil, datetime, ipaddress, fcntl, time

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
    """Read the list of IP addresses from the file with file locking."""
    if not os.path.exists(IP_FILE):
        return []
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            with open(IP_FILE, 'r') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # Shared lock for reading
                return [line.strip() for line in f if line.strip()]
        except (IOError, OSError) as e:
            if attempt < max_retries - 1:
                time.sleep(0.1)  # Brief delay before retry
                continue
            else:
                # If we can't get the lock after retries, return empty list
                return []

def save_ips(ips):
    """Before saving, archive the current file to a versioned copy, then write new content with file locking."""
    max_retries = 5
    for attempt in range(max_retries):
        try:
            # Create backup with microsecond precision to avoid conflicts
            if os.path.exists(IP_FILE):
                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                backup_name = os.path.join(VERSIONS_DIR, f'allowed_ips_{timestamp}.txt')
                shutil.copy2(IP_FILE, backup_name)
            
            # Write the new file with exclusive lock
            with open(IP_FILE, 'w') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Exclusive lock for writing
                for ip in ips:
                    f.write(ip + "\n")
            break  # Success, exit retry loop
            
        except (IOError, OSError) as e:
            if attempt < max_retries - 1:
                time.sleep(0.1)  # Brief delay before retry
                continue
            else:
                # If we can't get the lock after retries, raise the exception
                raise e

def is_valid_ip(address):
    try:
        ip = ipaddress.ip_address(address)
        return True
    except ValueError:
        return False

def is_internet_routable_ip(address):
    """Check if IP address is Internet-routable (not private, loopback, multicast, etc.)"""
    try:
        ip = ipaddress.ip_address(address)
        
        # Reject IPv4 non-routable addresses
        if ip.version == 4:
            # Loopback (127.0.0.0/8)
            if ip.is_loopback:
                return False, "Loopback addresses (127.x.x.x) are not allowed"
            
            # Private networks (RFC1918: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
            if ip.is_private:
                return False, "Private network addresses (RFC1918) are not allowed"
            
            # Multicast (224.0.0.0/4)
            if ip.is_multicast:
                return False, "Multicast addresses (224.x.x.x - 239.x.x.x) are not allowed"
            
            # Reserved/unspecified (0.0.0.0/8)
            if ip.is_unspecified or ip.is_reserved:
                return False, "Reserved or unspecified addresses are not allowed"
            
            # APIPA/Link-local (169.254.0.0/16)
            if ip.is_link_local:
                return False, "APIPA/Link-local addresses (169.254.x.x) are not allowed"
            
            # Broadcast
            if str(ip).endswith('.255'):
                return False, "Broadcast addresses are not allowed"
                
            # Additional specific ranges to block
            # 0.0.0.0/8 (this network)
            if ipaddress.ip_address('0.0.0.0') <= ip <= ipaddress.ip_address('0.255.255.255'):
                return False, "Network 0.0.0.0/8 addresses are not allowed"
                
        # Reject IPv6 non-routable addresses  
        elif ip.version == 6:
            if ip.is_loopback:
                return False, "IPv6 loopback address (::1) is not allowed"
            if ip.is_private:
                return False, "IPv6 private addresses are not allowed"
            if ip.is_multicast:
                return False, "IPv6 multicast addresses are not allowed"
            if ip.is_unspecified:
                return False, "IPv6 unspecified address (::) is not allowed"
            if ip.is_link_local:
                return False, "IPv6 link-local addresses are not allowed"
            if ip.is_reserved:
                return False, "IPv6 reserved addresses are not allowed"
                
        return True, None
        
    except ValueError:
        return False, "Invalid IP address format"

# Professional template with Bootstrap styling
HTML_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Network Feed Manager</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        .ip-card { transition: all 0.2s ease; }
        .ip-card:hover { transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
        .navbar-brand { font-weight: 600; }
        .btn-delete { --bs-btn-padding-y: 0.25rem; --bs-btn-padding-x: 0.5rem; --bs-btn-font-size: 0.75rem; }
    </style>
</head>
<body class="bg-light">
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary mb-4">
        <div class="container">
            <span class="navbar-brand mb-0 h1">
                <i class="bi bi-shield-check me-2"></i>Network Feed Manager
            </span>
        </div>
    </nav>

    <div class="container">
        {% with messages = get_flashed_messages() %}
          {% if messages %}
            {% for message in messages %}
              <div class="alert alert-info alert-dismissible fade show" role="alert">
                <i class="bi bi-info-circle me-2"></i>{{ message }}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
              </div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        <div class="row">
            <div class="col-lg-8">
                <div class="card shadow-sm">
                    <div class="card-header bg-white">
                        <h5 class="card-title mb-0">
                            <i class="bi bi-list-ul me-2"></i>Allowed IP Addresses
                            <span class="badge bg-secondary ms-2">{{ ip_list|length }}</span>
                        </h5>
                    </div>
                    <div class="card-body">
                        {% if ip_list %}
                            <div class="row g-3">
                                {% for ip in ip_list %}
                                <div class="col-md-6">
                                    <div class="card ip-card h-100">
                                        <div class="card-body d-flex justify-content-between align-items-center py-3">
                                            <div>
                                                <i class="bi bi-globe text-primary me-2"></i>
                                                <code class="text-dark">{{ ip }}</code>
                                            </div>
                                            <form action="{{ url_for('delete_ip') }}" method="post" class="d-inline">
                                                <input type="hidden" name="ip" value="{{ ip }}">
                                                <button type="submit" class="btn btn-outline-danger btn-delete" 
                                                        onclick="return confirm('Remove {{ ip }}?')">
                                                    <i class="bi bi-trash"></i>
                                                </button>
                                            </form>
                                        </div>
                                    </div>
                                </div>
                                {% endfor %}
                            </div>
                        {% else %}
                            <div class="text-center py-5 text-muted">
                                <i class="bi bi-inbox display-1"></i>
                                <p class="mt-3">No IP addresses configured yet</p>
                            </div>
                        {% endif %}
                    </div>
                </div>
            </div>

            <div class="col-lg-4">
                <div class="card shadow-sm">
                    <div class="card-header bg-white">
                        <h5 class="card-title mb-0">
                            <i class="bi bi-plus-circle me-2"></i>Add New IP
                        </h5>
                    </div>
                    <div class="card-body">
                        <form method="post" action="{{ url_for('add_ip') }}">
                            <div class="mb-3">
                                <label for="ip" class="form-label">IP Address</label>
                                <input type="text" class="form-control" id="ip" name="ip" 
                                       placeholder="192.168.1.100" required>
                                <div class="form-text">Enter a valid IPv4 or IPv6 address</div>
                            </div>
                            <button type="submit" class="btn btn-primary w-100">
                                <i class="bi bi-plus-lg me-2"></i>Add IP Address
                            </button>
                        </form>
                    </div>
                </div>

                <div class="card shadow-sm mt-4">
                    <div class="card-header bg-white">
                        <h5 class="card-title mb-0">
                            <i class="bi bi-clock-history me-2"></i>Version Control
                        </h5>
                    </div>
                    <div class="card-body">
                        <p class="card-text text-muted">
                            View previous versions and rollback changes if needed.
                        </p>
                        <a href="{{ url_for('versions') }}" class="btn btn-outline-secondary w-100">
                            <i class="bi bi-archive me-2"></i>Manage Versions
                        </a>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
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
    
    is_routable, error_msg = is_internet_routable_ip(ip)
    if not is_routable:
        flash(f"{ip}: {error_msg}")
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

    # Professional versions page template
    version_html = """
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Version History - Network Feed Manager</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css" rel="stylesheet">
    </head>
    <body class="bg-light">
        <nav class="navbar navbar-expand-lg navbar-dark bg-primary mb-4">
            <div class="container">
                <a class="navbar-brand" href="{{ url_for('index') }}">
                    <i class="bi bi-shield-check me-2"></i>Network Feed Manager
                </a>
                <span class="navbar-text">Version History</span>
            </div>
        </nav>

        <div class="container">
            <div class="row justify-content-center">
                <div class="col-lg-8">
                    <div class="card shadow-sm">
                        <div class="card-header bg-white d-flex justify-content-between align-items-center">
                            <h5 class="card-title mb-0">
                                <i class="bi bi-clock-history me-2"></i>Version History
                            </h5>
                            <a href="{{ url_for('index') }}" class="btn btn-outline-primary btn-sm">
                                <i class="bi bi-arrow-left me-1"></i>Back to Main
                            </a>
                        </div>
                        <div class="card-body">
                            {% if backups %}
                                <form method="post">
                                    <div class="list-group">
                                        {% for bf in backups %}
                                        <div class="list-group-item d-flex justify-content-between align-items-center">
                                            <div>
                                                <i class="bi bi-file-text text-primary me-2"></i>
                                                <strong>{{ bf }}</strong>
                                                <br>
                                                <small class="text-muted">
                                                    {% set parts = bf.replace('allowed_ips_', '').replace('.txt', '').split('_') %}
                                                    {% if parts|length >= 2 %}
                                                        {{ parts[0][:4] }}-{{ parts[0][4:6] }}-{{ parts[0][6:8] }} 
                                                        {{ parts[1][:2] }}:{{ parts[1][2:4] }}:{{ parts[1][4:6] }}
                                                    {% endif %}
                                                </small>
                                            </div>
                                            <button type="submit" name="version_file" value="{{ bf }}" 
                                                    class="btn btn-warning btn-sm"
                                                    onclick="return confirm('Rollback to this version? This will replace the current configuration.')">
                                                <i class="bi bi-arrow-counterclockwise me-1"></i>Rollback
                                            </button>
                                        </div>
                                        {% endfor %}
                                    </div>
                                </form>
                            {% else %}
                                <div class="text-center py-5 text-muted">
                                    <i class="bi bi-archive display-1"></i>
                                    <p class="mt-3">No backup versions available yet</p>
                                    <small>Versions are created automatically when you make changes</small>
                                </div>
                            {% endif %}
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """
    return render_template_string(version_html, backups=backups)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
