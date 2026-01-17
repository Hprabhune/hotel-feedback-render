from flask import Flask, render_template, request, send_from_directory, redirect, url_for, Response
from functools import wraps
import sqlite3
import qrcode
import os
import socket
import csv
from io import StringIO
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Create necessary folders if they don't exist
for folder in ['qr_codes', 'database']:
    if not os.path.exists(folder):
        os.makedirs(folder)

app = Flask(__name__)

# ------------------- HOTEL CONFIGURATION -------------------
HOTEL_NAME = "Hotel Yash Undri"  # Hotel name constant
HOTEL_LOGO = "Hotel image.jpeg"  # Hotel logo filename

# ------------------- ALERT CONFIGURATION -------------------
ALERT_THRESHOLDS = {
    'food_quality': 2.5,      # Alert if average below 2.5
    'seating_arrangement': 2.5,
    'parking': 2.5,
    'washroom': 2.0,          # Washroom has stricter threshold
    'hotel_service': 2.0,     # Service has stricter threshold
    'overall': 2.5            # Overall average threshold
}

ALERT_EMAILS = [
    "admin@example.com",  # Primary manager email
    "admin@example.com"          # Your email for testing
]

# Email Configuration (Update with your SMTP settings)
EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',  # Change based on your email provider
    'smtp_port': 587,
    'sender_email': 'admin@example.com',  # Update this
    'sender_password': 'ogsp prln yhwc rbze',  # Use app password, not regular password
    'enable_emails': True  # Set to True after configuring email
}

# ------------------- CREATE FOLDERS -------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
QR_FOLDER = os.path.join(BASE_DIR, "qr_codes")
DB_FOLDER = os.path.join(BASE_DIR, "database")
STATIC_FOLDER = os.path.join(BASE_DIR, "static")

if not os.path.exists(QR_FOLDER):
    os.makedirs(QR_FOLDER)

if not os.path.exists(DB_FOLDER):
    os.makedirs(DB_FOLDER)

if not os.path.exists(STATIC_FOLDER):
    os.makedirs(STATIC_FOLDER)

# ------------------- GET IP ADDRESS -------------------


LOCAL_IP = "hotel-feedback-render.onrender.com"
# ------------------- HELPER FUNCTIONS -------------------
def get_rating_emoji(rating):
    """Return emoji for rating value"""
    emojis = {
        1: '😞',
        2: '😐',
        3: '🙂',
        4: '😊',
        5: '😍'
    }
    return emojis.get(rating, '😐')

def check_alert_thresholds(feedback_data):
    """Check if any rating falls below thresholds"""
    alerts = []
    
    # Check individual categories
    for category, threshold in ALERT_THRESHOLDS.items():
        if category in feedback_data:
            rating = feedback_data[category]
            if rating < threshold:
                alerts.append({
                    'category': category.replace('_', ' ').title(),
                    'rating': rating,
                    'threshold': threshold,
                    'comments': feedback_data.get(f'{category}_comments', 'No comments')
                })
    
    return alerts

def test_email_config():
    """Test email configuration"""
    print("\n📧 Testing Email Configuration...")
    print(f"SMTP Server: {EMAIL_CONFIG['smtp_server']}:{EMAIL_CONFIG['smtp_port']}")
    print(f"Sender Email: {EMAIL_CONFIG['sender_email']}")
    print(f"Enable Emails: {EMAIL_CONFIG['enable_emails']}")
    
    if not EMAIL_CONFIG['enable_emails']:
        print("❌ Email alerts are disabled in configuration!")
        print("   Set EMAIL_CONFIG['enable_emails'] = True")
        return False
    
    try:
        # Simple connection test
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.starttls()
        print("✅ SMTP Connection successful")
        
        # Try to login
        try:
            server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
            print("✅ Login successful")
            server.quit()
            return True
        except smtplib.SMTPAuthenticationError:
            print("❌ Login failed - Invalid credentials")
            print("   Please check your email and password")
            print("   For Gmail, use App Password, not regular password")
        except Exception as e:
            print(f"❌ Login error: {str(e)}")
        
        server.quit()
    except Exception as e:
        print(f"❌ SMTP Connection error: {str(e)}")
    
    return False

def send_alert_email(alerts, feedback_id):
    """Send email alert for low ratings"""
    if not EMAIL_CONFIG['enable_emails']:
        print(f"⚠️ Email alerts disabled. Would send alert for feedback #{feedback_id}")
        print(f"   Alerts: {alerts}")
        return False
    
    try:
        print(f"\n📧 Attempting to send alert email for feedback #{feedback_id}")
        print(f"   Recipients: {ALERT_EMAILS}")
        print(f"   Number of alerts: {len(alerts)}")
        
        # Create message
        msg = MIMEMultipart()
        msg['Subject'] = f'⚠️ LOW RATING ALERT - {HOTEL_NAME} - Feedback #{feedback_id}'
        msg['From'] = EMAIL_CONFIG['sender_email']
        msg['To'] = ', '.join(ALERT_EMAILS)
        
        # Create email body
        body = f"""
        <h2>⚠️ LOW RATING ALERT</h2>
        <p><strong>Hotel:</strong> {HOTEL_NAME}</p>
        <p><strong>Feedback ID:</strong> #{feedback_id}</p>
        <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %I:%M %p')}</p>
        
        <h3>Critical Ratings Below Threshold:</h3>
        <table border="1" cellpadding="8" style="border-collapse: collapse;">
            <tr style="background-color: #ffcccc;">
                <th>Category</th>
                <th>Rating</th>
                <th>Threshold</th>
                <th>Comments</th>
            </tr>
        """
        
        for alert in alerts:
            body += f"""
            <tr>
                <td><strong>{alert['category']}</strong></td>
                <td style="color: red;"><strong>{alert['rating']}/5</strong></td>
                <td>{alert['threshold']}/5</td>
                <td>{alert['comments'][:100]}{'...' if len(alert['comments']) > 100 else ''}</td>
            </tr>
            """
        
        body += f"""
        </table>
        
        <p style="margin-top: 20px;">
            <a href="https://{LOCAL_IP}/admin" style="background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                View Full Details in Admin Panel
            </a>
        </p>
        
        <hr>
        <p style="color: #666; font-size: 12px;">
            This is an automated alert from {HOTEL_NAME} Feedback System.
        </p>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        print(f"   Connecting to {EMAIL_CONFIG['smtp_server']}:{EMAIL_CONFIG['smtp_port']}")
        
        # Send email
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.ehlo()
        server.starttls()
        server.ehlo()
        
        print(f"   Logging in as {EMAIL_CONFIG['sender_email']}")
        server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
        
        print(f"   Sending email to {ALERT_EMAILS}")
        server.send_message(msg)
        server.quit()
        
        print(f"✅ Alert email sent successfully for feedback #{feedback_id}")
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ SMTP Authentication Error: {str(e)}")
        print("   Most likely incorrect email or password")
        print("   For Gmail, make sure:")
        print("   1. You've enabled 'Less secure app access' OR")
        print("   2. You're using an App Password (recommended)")
    except Exception as e:
        print(f"❌ Failed to send alert email: {str(e)}")
        import traceback
        traceback.print_exc()
    
    return False

def get_recent_alerts(hours=24):
    """Get alerts from recent feedback (last X hours)"""
    try:
        conn = sqlite3.connect(os.path.join(DB_FOLDER, "reviews.db"))
        cur = conn.cursor()
        
        # Get feedback from last X hours
        time_threshold = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
        
        cur.execute("""
            SELECT * FROM reviews 
            WHERE created_at >= ? 
            ORDER BY created_at DESC
        """, (time_threshold,))
        
        recent_feedback = cur.fetchall()
        conn.close()
        
        # Check each feedback for alerts
        all_alerts = []
        for feedback in recent_feedback:
            feedback_data = {
                'food_quality': feedback[1],
                'food_quality_comments': feedback[2],
                'seating_arrangement': feedback[3],
                'seating_arrangement_comments': feedback[4],
                'parking': feedback[5],
                'parking_comments': feedback[6],
                'washroom': feedback[7],
                'washroom_comments': feedback[8],
                'hotel_service': feedback[9],
                'hotel_service_comments': feedback[10]
            }
            
            # Calculate overall average
            ratings = [feedback[1], feedback[3], feedback[5], feedback[7], feedback[9]]
            overall_avg = sum(ratings) / len(ratings)
            feedback_data['overall'] = overall_avg
            
            alerts = check_alert_thresholds(feedback_data)
            if alerts:
                all_alerts.append({
                    'feedback_id': feedback[0],
                    'date': feedback[12],
                    'alerts': alerts,
                    'overall': overall_avg
                })
        
        return all_alerts
        
    except Exception as e:
        print(f"Error getting recent alerts: {e}")
        return []

# ------------------- ADMIN PASSWORD PROTECTION -------------------
def admin_required(f):
    """Decorator to protect admin page with password"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != 'admin' or auth.password != 'harshal@2002':
            return ('Unauthorized', 401, 
                   {'WWW-Authenticate': 'Basic realm="Login Required"'})
        return f(*args, **kwargs)
    return decorated

# ------------------- DATABASE SETUP -------------------
def init_db():
    conn = sqlite3.connect(os.path.join(DB_FOLDER, "reviews.db"))
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS reviews")
    cur.execute("""
        CREATE TABLE reviews(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            food_quality INTEGER,
            food_quality_comments TEXT,
            seating_arrangement INTEGER,
            seating_arrangement_comments TEXT,
            parking INTEGER,
            parking_comments TEXT,
            washroom INTEGER,
            washroom_comments TEXT,
            hotel_service INTEGER,
            hotel_service_comments TEXT,
            general_comments TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    print("✅ Database created successfully with correct schema!")

# ------------------- CHECK AND FIX DATABASE -------------------
def check_and_fix_db():
    """Check if database has correct schema, fix if needed"""
    try:
        conn = sqlite3.connect(os.path.join(DB_FOLDER, "reviews.db"))
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(reviews)")
        columns = cur.fetchall()
        column_names = [col[1] for col in columns]
        
        # Check if we have the new schema
        expected_columns = ['food_quality_comments', 'seating_arrangement_comments', 
                           'parking_comments', 'washroom_comments', 'hotel_service_comments']
        
        if not all(col in column_names for col in expected_columns):
            print("⚠️ Database schema outdated. Fixing...")
            conn.close()
            init_db()
        else:
            print("✅ Database schema is correct!")
            conn.close()
    except sqlite3.OperationalError:
        print("📊 Creating new database...")
        init_db()

# ------------------- CSV EXPORT FUNCTION -------------------
@app.route("/admin/export/csv")
@admin_required
def export_csv():
    """Export all feedback data to CSV"""
    try:
        conn = sqlite3.connect(os.path.join(DB_FOLDER, "reviews.db"))
        cur = conn.cursor()
        cur.execute("SELECT * FROM reviews ORDER BY created_at DESC")
        reviews = cur.fetchall()
        conn.close()
        
        # Create CSV in memory
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'ID', 'Date', 'Time',
            'Food Quality', 'Food Comments',
            'Seating Arrangement', 'Seating Comments',
            'Parking Facility', 'Parking Comments',
            'Washroom Cleanliness', 'Washroom Comments',
            'Hotel Service', 'Service Comments',
            'General Comments',
            'Overall Average'
        ])
        
        # Write data rows
        for review in reviews:
            # Calculate overall average
            ratings = [review[1], review[3], review[5], review[7], review[9]]
            overall_avg = sum(ratings) / len(ratings) if ratings else 0
            
            # Format date and time
            created_at = review[12]
            if created_at:
                try:
                    date_obj = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                    date_str = date_obj.strftime('%Y-%m-%d')
                    time_str = date_obj.strftime('%H:%M:%S')
                except:
                    date_str = created_at[:10] if len(created_at) > 10 else created_at
                    time_str = created_at[11:19] if len(created_at) > 19 else ''
            else:
                date_str = ''
                time_str = ''
            
            writer.writerow([
                review[0],  # ID
                date_str,   # Date
                time_str,   # Time
                review[1],  # Food Quality
                review[2] or '',  # Food Comments
                review[3],  # Seating Arrangement
                review[4] or '',  # Seating Comments
                review[5],  # Parking Facility
                review[6] or '',  # Parking Comments
                review[7],  # Washroom Cleanliness
                review[8] or '',  # Washroom Comments
                review[9],  # Hotel Service
                review[10] or '',  # Service Comments
                review[11] or '',  # General Comments
                f"{overall_avg:.2f}"  # Overall Average
            ])
        
        # Create response with CSV file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{HOTEL_NAME.replace(' ', '_')}_Feedback_{timestamp}.csv"
        
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": "text/csv; charset=utf-8"
            }
        )
        
    except Exception as e:
        return f"""
        <html>
        <head><title>Export Error</title></head>
        <body>
            <h2>CSV Export Error</h2>
            <p>Error: {str(e)}</p>
            <a href="/admin">Back to Admin</a>
        </body>
        </html>
        """

@app.route("/admin/export/recent_alerts_csv")
@admin_required
def export_recent_alerts_csv():
    """Export recent alerts to CSV"""
    try:
        alerts_data = get_recent_alerts(hours=168)  # Last 7 days
        
        # Create CSV in memory
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Feedback ID', 'Date', 'Time',
            'Alert Category', 'Rating', 'Threshold',
            'Comments', 'Overall Rating'
        ])
        
        # Write data rows
        for alert_group in alerts_data:
            feedback_id = alert_group['feedback_id']
            date_time = alert_group['date']
            
            if date_time:
                try:
                    date_obj = datetime.strptime(date_time, '%Y-%m-%d %H:%M:%S')
                    date_str = date_obj.strftime('%Y-%m-%d')
                    time_str = date_obj.strftime('%H:%M:%S')
                except:
                    date_str = date_time[:10] if len(date_time) > 10 else date_time
                    time_str = date_time[11:19] if len(date_time) > 19 else ''
            else:
                date_str = ''
                time_str = ''
            
            for alert in alert_group['alerts']:
                writer.writerow([
                    feedback_id,
                    date_str,
                    time_str,
                    alert['category'],
                    alert['rating'],
                    alert['threshold'],
                    alert['comments'][:200],  # Limit comment length
                    f"{alert_group['overall']:.2f}"
                ])
        
        # Create response with CSV file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{HOTEL_NAME.replace(' ', '_')}_Alerts_{timestamp}.csv"
        
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": "text/csv; charset=utf-8"
            }
        )
        
    except Exception as e:
        return f"""
        <html>
        <head><title>Export Error</title></head>
        <body>
            <h2>Alerts CSV Export Error</h2>
            <p>Error: {str(e)}</p>
            <a href="/admin">Back to Admin</a>
        </body>
        </html>
        """

# ------------------- TEST EMAIL ROUTE -------------------
@app.route("/test_email")
@admin_required
def test_email():
    """Test email functionality"""
    # Create a test alert
    test_alerts = [{
        'category': 'Food Quality',
        'rating': 2.0,
        'threshold': 2.5,
        'comments': 'This is a test alert to check email functionality'
    }]
    
    result = send_alert_email(test_alerts, 999)
    
    return f"""
    <html>
    <head>
        <title>Email Test</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="container mt-5">
        <div class="card">
            <div class="card-header bg-primary text-white">
                <h3>📧 Email Test Result</h3>
            </div>
            <div class="card-body text-center py-5">
                <h1 class="display-1">{'✅' if result else '❌'}</h1>
                <h3 class="{'text-success' if result else 'text-danger'}">
                    Email sending {'SUCCESSFUL' if result else 'FAILED'}
                </h3>
                <p class="mt-3">Check the terminal for detailed debug information.</p>
                <div class="mt-4">
                    <a href="/admin" class="btn btn-primary">← Back to Admin Dashboard</a>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

# ------------------- HOME ROUTE -------------------
@app.route("/")
def home():
    return f"""
    <html>
    <head>
        <title>{HOTEL_NAME} - Food Review</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            .hotel-logo {{
                width: 200px;
                height: 160px;
                object-fit: cover;
                border-radius: 10px;
                border: 3px solid #0d6efd;
                box-shadow: 0 4px 8px rgba(0,0,0,0.2);
                margin: 15px auto;
                display: block;
            }}
            .hotel-header {{
                background: linear-gradient(135deg, #0d6efd 0%, #198754 100%);
                color: white;
                padding: 1.5rem 0;
                margin-bottom: 2rem;
                border-radius: 15px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }}
            @media (max-width: 768px) {{
                .hotel-logo {{
                    width: 160px;
                    height: 130px;
                }}
            }}
        </style>
    </head>
    <body class="container mt-4">
        <div class="hotel-header text-center">
            <h2>🏨 {HOTEL_NAME}</h2>
            <p class="lead mb-0">Hotel Feedback System</p>
            <div class="mt-3">
                <img src="/static/{HOTEL_LOGO}" alt="{HOTEL_NAME} Logo" class="hotel-logo">
            </div>
        </div>
        
        <div class="card">
            <div class="card-body">
                <h5>Welcome!</h5>
                <p>Scan the QR code to submit your hotel feedback.</p>
                
                <div class="alert alert-info">
                    <strong>📱 Mobile Access:</strong> http://{LOCAL_IP}:5000
                    <br><small>Admin Login: admin / harshal@2002</small>
                </div>
                
                <div class="mt-4">
                    <a href="/generate_qr" class="btn btn-success me-2">📱 Generate QR Code</a>
                    <a href="/admin" class="btn btn-secondary me-2">👨‍💼 Admin Dashboard</a>
                    <a href="/review" class="btn btn-primary">📝 Test Feedback Form</a>
                </div>
            </div>
            <div class="card-footer text-center">
                <small>{HOTEL_NAME} &copy; 2024</small>
            </div>
        </div>
    </body>
    </html>
    """

# ------------------- GENERATE SINGLE QR -------------------
@app.route("/generate_qr")
def generate_qr():
    url = f"https://{LOCAL_IP}/review"
    img = qrcode.make(url)
    filepath = os.path.join(QR_FOLDER, "hotel_review_qr.png")
    img.save(filepath)
    
    return f"""
    <html>
    <head>
        <title>{HOTEL_NAME} - QR Code</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            .hotel-logo {{
                width: 200px;
                height: 160px;
                object-fit: cover;
                border-radius: 10px;
                border: 3px solid #198754;
                box-shadow: 0 4px 8px rgba(0,0,0,0.2);
                margin: 15px auto;
                display: block;
            }}
            .hotel-header {{
                background: linear-gradient(135deg, #198754 0%, #0d6efd 100%);
                color: white;
                padding: 1.5rem 0;
                margin-bottom: 2rem;
                border-radius: 15px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }}
            .qr-container {{
                background: white;
                padding: 20px;
                border-radius: 10px;
                display: inline-block;
                box-shadow: 0 0 20px rgba(0,0,0,0.1);
            }}
            @media (max-width: 768px) {{
                .hotel-logo {{
                    width: 160px;
                    height: 130px;
                }}
            }}
        </style>
    </head>
    <body class="container mt-4">
        <div class="hotel-header text-center">
            <h3>🏨 {HOTEL_NAME}</h3>
            <p class="lead mb-0">QR Code for Hotel Feedback</p>
            <div class="mt-2">
                <img src="/static/{HOTEL_LOGO}" alt="{HOTEL_NAME} Logo" class="hotel-logo">
            </div>
        </div>
        
        <div class="card">
            <div class="card-body text-center">
                <div class="alert alert-success">
                    <h5>✅ Ready for Mobile Scanning!</h5>
                    <p><strong>QR Points to:</strong> {url}</p>
                    <p><small>Admin Login: admin / harshal@2002</small></p>
                </div>
                
                <div class="qr-container mb-3">
                    <img src="/qr_codes/hotel_review_qr.png" width="300">
                </div>
                
                <div class="mt-4">
                    <a href="/qr_codes/hotel_review_qr.png" download="hotel_feedback_qr.png" 
                       class="btn btn-success btn-lg">
                        📥 Download QR Code
                    </a>
                    <a href="/review" class="btn btn-primary btn-lg ms-2">📝 Test Feedback Form</a>
                    <a href="/admin" class="btn btn-secondary btn-lg ms-2">👨‍💼 Admin</a>
                </div>
            </div>
            <div class="card-footer text-center">
                <small>{HOTEL_NAME} &copy; 2024</small>
            </div>
        </div>
    </body>
    </html>
    """

# ------------------- REVIEW FORM (SINGLE PAGE FOR ALL) -------------------
@app.route("/review", methods=["GET", "POST"])
def review():
    
    if request.method == "POST":
        # Get all ratings and comments from form
        food_quality = int(request.form["food_quality"])
        food_quality_comments = request.form.get("food_quality_comments", "")
        
        seating_arrangement = int(request.form["seating_arrangement"])
        seating_arrangement_comments = request.form.get("seating_arrangement_comments", "")
        
        parking = int(request.form["parking"])
        parking_comments = request.form.get("parking_comments", "")
        
        washroom = int(request.form["washroom"])
        washroom_comments = request.form.get("washroom_comments", "")
        
        hotel_service = int(request.form["hotel_service"])
        hotel_service_comments = request.form.get("hotel_service_comments", "")
        
        general_comments = request.form.get("general_comments", "")
        
        # Save to database
        conn = sqlite3.connect(os.path.join(DB_FOLDER, "reviews.db"))
        cur = conn.cursor()
        cur.execute("""INSERT INTO reviews 
                    (food_quality, food_quality_comments, 
                     seating_arrangement, seating_arrangement_comments,
                     parking, parking_comments,
                     washroom, washroom_comments,
                     hotel_service, hotel_service_comments,
                     general_comments) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (food_quality, food_quality_comments,
                     seating_arrangement, seating_arrangement_comments,
                     parking, parking_comments,
                     washroom, washroom_comments,
                     hotel_service, hotel_service_comments,
                     general_comments))
        
        # Get the ID of the inserted feedback
        feedback_id = cur.lastrowid
        conn.commit()
        conn.close()
        
        # Check for alerts
        feedback_data = {
            'food_quality': food_quality,
            'food_quality_comments': food_quality_comments,
            'seating_arrangement': seating_arrangement,
            'seating_arrangement_comments': seating_arrangement_comments,
            'parking': parking,
            'parking_comments': parking_comments,
            'washroom': washroom,
            'washroom_comments': washroom_comments,
            'hotel_service': hotel_service,
            'hotel_service_comments': hotel_service_comments
        }
        
        # Calculate overall average for alert checking
        ratings = [food_quality, seating_arrangement, parking, washroom, hotel_service]
        overall_avg = sum(ratings) / len(ratings)
        feedback_data['overall'] = overall_avg
        
        alerts = check_alert_thresholds(feedback_data)
        if alerts:
            send_alert_email(alerts, feedback_id)
        
        return f"""
        <html>
        <head>
            <title>Thank You - {HOTEL_NAME}</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                .hotel-logo {{
                    width: 200px;
                    height: 160px;
                    object-fit: cover;
                    border-radius: 10px;
                    border: 3px solid #198754;
                    box-shadow: 0 4px 8px rgba(0,0,0,0.2);
                    margin: 15px auto;
                    display: block;
                }}
                .hotel-header {{
                    background: linear-gradient(135deg, #198754 0%, #0d6efd 100%);
                    color: white;
                    padding: 1.5rem 0;
                    margin-bottom: 2rem;
                    border-radius: 15px;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                }}
                @media (max-width: 768px) {{
                    .hotel-logo {{
                        width: 160px;
                        height: 130px;
                    }}
                }}
            </style>
        </head>
        <body class="container text-center py-5">
            <div class="hotel-header">
                <h3>🏨 {HOTEL_NAME}</h3>
                <p class="lead mb-0">Thank You for Your Feedback</p>
                <div class="mt-2">
                    <img src="/static/{HOTEL_LOGO}" alt="{HOTEL_NAME} Logo" class="hotel-logo">
                </div>
            </div>
            
            <div class="card shadow mx-auto" style="max-width: 500px;">
                <div class="card-body py-5">
                    <div class="display-1 mb-4">🎉</div>
                    <h2 class="text-success">Thank You!</h2>
                    <p class="lead">Your valuable feedback has been submitted successfully.</p>
                    
                    <div class="mt-4">
                        <a href="/review" class="btn btn-primary">Submit Another Review</a>
                        <a href="/" class="btn btn-outline-secondary ms-2">Home</a>
                    </div>
                </div>
                <div class="card-footer text-center">
                    <small>{HOTEL_NAME} &copy; 2024</small>
                </div>
            </div>
        </body>
        </html>
        """
    
    # GET request - show the form
    return f"""
    <html>
    <head>
        <title>Hotel Feedback - {HOTEL_NAME}</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            .hotel-logo {{
                width: 220px;
                height: 180px;
                object-fit: cover;
                border-radius: 12px;
                border: 4px solid #0d6efd;
                box-shadow: 0 6px 12px rgba(0,0,0,0.25);
                margin: 20px auto;
                display: block;
            }}
            .hotel-header {{
                background: linear-gradient(135deg, #0d6efd 0%, #198754 100%);
                color: white;
                padding: 1.5rem 0;
                margin-bottom: 2rem;
                border-radius: 15px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }}
            .rating-item {{
                background: #f8f9fa;
                border-radius: 10px;
                padding: 20px;
                margin-bottom: 20px;
                border: 1px solid #dee2e6;
                transition: transform 0.3s;
            }}
            .rating-item:hover {{
                transform: translateY(-2px);
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            }}
            .rating-label {{
                font-weight: 600;
                color: #495057;
                margin-bottom: 15px;
                font-size: 1.1rem;
                display: flex;
                align-items: center;
            }}
            .rating-label-number {{
                background: #0d6efd;
                color: white;
                width: 28px;
                height: 28px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin-right: 10px;
                font-size: 0.9rem;
            }}
            .rating-stars {{
                display: flex;
                justify-content: center;
                gap: 8px;
                font-size: 2.2rem;
                cursor: pointer;
            }}
            .rating-stars .star {{
                transition: all 0.3s ease;
                filter: drop-shadow(0 2px 3px rgba(0,0,0,0.2));
            }}
            .rating-stars .star:hover {{
                transform: scale(1.3);
                filter: drop-shadow(0 3px 5px rgba(0,0,0,0.4));
            }}
            .rating-value {{
                font-size: 1rem;
                margin-top: 10px;
                text-align: center;
                font-weight: 500;
                padding: 5px 10px;
                border-radius: 20px;
                display: inline-block;
                background: #f1f3f5;
            }}
            .rating-bar {{
                height: 8px;
                background: #e9ecef;
                border-radius: 4px;
                margin-top: 15px;
                overflow: hidden;
            }}
            .rating-fill {{
                height: 100%;
                border-radius: 4px;
                transition: width 0.5s ease, background 0.5s ease;
            }}
            .category-comments {{
                margin-top: 15px;
                padding: 10px;
                background: #f8f9fa;
                border-radius: 8px;
                border: 1px solid #e9ecef;
            }}
            .category-comments textarea {{
                background: white;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                padding: 10px;
                font-size: 0.9rem;
                resize: vertical;
                min-height: 60px;
            }}
            .category-comments textarea:focus {{
                border-color: #0d6efd;
                box-shadow: 0 0 0 0.2rem rgba(13, 110, 253, 0.25);
                outline: none;
            }}
            
            /* Individual star colors - each star has its own fixed color */
            .star[data-value="1"] {{ color: #ff6b6b; }} /* Red */
            .star[data-value="2"] {{ color: #ffa726; }} /* Orange */
            .star[data-value="3"] {{ color: #ffd166; }} /* Yellow */
            .star[data-value="4"] {{ color: #06d6a0; }} /* Light Green */
            .star[data-value="5"] {{ color: #118ab2; }} /* Blue */
            
            /* Default inactive state */
            .star.inactive {{ 
                opacity: 0.4;
                filter: grayscale(0.8);
            }}
            
            /* Active state */
            .star.active {{
                opacity: 1;
                filter: none;
                transform: scale(1.1);
            }}
            
            /* Value display backgrounds */
            .value-bg-1 {{ background: #ffebee; color: #ff6b6b; }}
            .value-bg-2 {{ background: #fff3e0; color: #ffa726; }}
            .value-bg-3 {{ background: #fff9c4; color: #ffd166; }}
            .value-bg-4 {{ background: #e8f5e9; color: #06d6a0; }}
            .value-bg-5 {{ background: #e3f2fd; color: #118ab2; }}
            
            /* Bar gradient colors */
            .bar-1 {{ background: linear-gradient(90deg, #ff6b6b, #ffa726); }}
            .bar-2 {{ background: linear-gradient(90deg, #ff6b6b, #ffa726); }}
            .bar-3 {{ background: linear-gradient(90deg, #ff6b6b, #ffd166); }}
            .bar-4 {{ background: linear-gradient(90deg, #ff6b6b, #06d6a0); }}
            .bar-5 {{ background: linear-gradient(90deg, #ff6b6b, #118ab2); }}
            
            .comments-toggle {{
                color: #0d6efd;
                cursor: pointer;
                font-size: 0.9rem;
                margin-top: 10px;
                display: inline-block;
                text-decoration: none;
            }}
            .comments-toggle:hover {{
                text-decoration: underline;
            }}
            
            @media (max-width: 768px) {{
                .hotel-logo {{
                    width: 180px;
                    height: 150px;
                }}
                .rating-stars {{
                    font-size: 1.8rem;
                    gap: 5px;
                }}
                .rating-label {{
                    font-size: 1rem;
                }}
                .rating-label-number {{
                    width: 24px;
                    height: 24px;
                    font-size: 0.8rem;
                }}
            }}
        </style>
    </head>
    <body>
        <!-- Hotel Header with Logo -->
        <div class="hotel-header text-center">
            <div class="container">
                <h1 class="display-5 mb-3">🏨 {HOTEL_NAME}</h1>
                <p class="lead mb-0">Detailed Feedback Form</p>
                <p class="small opacity-75">Rate each aspect and provide specific comments</p>
                <div class="mt-3">
                    <img src="/static/{HOTEL_LOGO}" alt="{HOTEL_NAME} Logo" class="hotel-logo">
                </div>
            </div>
        </div>
        
        <!-- Feedback Form -->
        <div class="container">
            <div class="row justify-content-center">
                <div class="col-md-10 col-lg-8">
                    <div class="card shadow">
                        <div class="card-header bg-primary text-white">
                            <h4 class="mb-0">📝 Rate Your Experience</h4>
                        </div>
                        <div class="card-body">
                            <form method="POST" action="/review" id="feedbackForm">
                                
                                <!-- Food Quality -->
                                <div class="rating-item">
                                    <div class="rating-label">
                                        <span class="rating-label-number">1</span>
                                        Food Quality
                                    </div>
                                    <div class="rating-stars" data-category="food_quality">
                                        <span class="star inactive" data-value="1">⭐</span>
                                        <span class="star inactive" data-value="2">⭐</span>
                                        <span class="star inactive" data-value="3">⭐</span>
                                        <span class="star inactive" data-value="4">⭐</span>
                                        <span class="star inactive" data-value="5">⭐</span>
                                    </div>
                                    <div class="text-center mt-3">
                                        <span class="rating-value" id="food_quality_value">Not rated yet</span>
                                    </div>
                                    <div class="rating-bar">
                                        <div class="rating-fill" id="food_quality_bar" style="width: 0%"></div>
                                    </div>
                                    <a class="comments-toggle" onclick="toggleComments('food_quality_comments')">
                                        💬 Add comments about Food Quality
                                    </a>
                                    <div class="category-comments" id="food_quality_comments" style="display: none;">
                                        <textarea 
                                            name="food_quality_comments" 
                                            placeholder="What did you like/dislike about the food quality? Any suggestions?"
                                            rows="2"></textarea>
                                    </div>
                                    <input type="hidden" name="food_quality" id="food_quality" value="" required>
                                </div>
                                
                                <!-- Seating Arrangement -->
                                <div class="rating-item">
                                    <div class="rating-label">
                                        <span class="rating-label-number">2</span>
                                        Seating Arrangement
                                    </div>
                                    <div class="rating-stars" data-category="seating_arrangement">
                                        <span class="star inactive" data-value="1">⭐</span>
                                        <span class="star inactive" data-value="2">⭐</span>
                                        <span class="star inactive" data-value="3">⭐</span>
                                        <span class="star inactive" data-value="4">⭐</span>
                                        <span class="star inactive" data-value="5">⭐</span>
                                    </div>
                                    <div class="text-center mt-3">
                                        <span class="rating-value" id="seating_arrangement_value">Not rated yet</span>
                                    </div>
                                    <div class="rating-bar">
                                        <div class="rating-fill" id="seating_arrangement_bar" style="width: 0%"></div>
                                    </div>
                                    <a class="comments-toggle" onclick="toggleComments('seating_arrangement_comments')">
                                        💬 Add comments about Seating Arrangement
                                    </a>
                                    <div class="category-comments" id="seating_arrangement_comments" style="display: none;">
                                        <textarea 
                                            name="seating_arrangement_comments" 
                                            placeholder="Was the seating comfortable? Any issues with spacing or arrangement?"
                                            rows="2"></textarea>
                                    </div>
                                    <input type="hidden" name="seating_arrangement" id="seating_arrangement" value="" required>
                                </div>
                                
                                <!-- Parking -->
                                <div class="rating-item">
                                    <div class="rating-label">
                                        <span class="rating-label-number">3</span>
                                        Parking Facility
                                    </div>
                                    <div class="rating-stars" data-category="parking">
                                        <span class="star inactive" data-value="1">⭐</span>
                                        <span class="star inactive" data-value="2">⭐</span>
                                        <span class="star inactive" data-value="3">⭐</span>
                                        <span class="star inactive" data-value="4">⭐</span>
                                        <span class="star inactive" data-value="5">⭐</span>
                                    </div>
                                    <div class="text-center mt-3">
                                        <span class="rating-value" id="parking_value">Not rated yet</span>
                                    </div>
                                    <div class="rating-bar">
                                        <div class="rating-fill" id="parking_bar" style="width: 0%"></div>
                                    </div>
                                    <a class="comments-toggle" onclick="toggleComments('parking_comments')">
                                        💬 Add comments about Parking
                                    </a>
                                    <div class="category-comments" id="parking_comments" style="display: none;">
                                        <textarea 
                                            name="parking_comments" 
                                            placeholder="Was parking easy to find? Any safety or space concerns?"
                                            rows="2"></textarea>
                                    </div>
                                    <input type="hidden" name="parking" id="parking" value="" required>
                                </div>
                                
                                <!-- Washroom -->
                                <div class="rating-item">
                                    <div class="rating-label">
                                        <span class="rating-label-number">4</span>
                                        Washroom Cleanliness
                                    </div>
                                    <div class="rating-stars" data-category="washroom">
                                        <span class="star inactive" data-value="1">⭐</span>
                                        <span class="star inactive" data-value="2">⭐</span>
                                        <span class="star inactive" data-value="3">⭐</span>
                                        <span class="star inactive" data-value="4">⭐</span>
                                        <span class="star inactive" data-value="5">⭐</span>
                                    </div>
                                    <div class="text-center mt-3">
                                        <span class="rating-value" id="washroom_value">Not rated yet</span>
                                    </div>
                                    <div class="rating-bar">
                                        <div class="rating-fill" id="washroom_bar" style="width: 0%"></div>
                                    </div>
                                    <a class="comments-toggle" onclick="toggleComments('washroom_comments')">
                                        💬 Add comments about Washrooms
                                    </a>
                                    <div class="category-comments" id="washroom_comments" style="display: none;">
                                        <textarea 
                                            name="washroom_comments" 
                                            placeholder="Were washrooms clean and well-maintained? Any issues?"
                                            rows="2"></textarea>
                                    </div>
                                    <input type="hidden" name="washroom" id="washroom" value="" required>
                                </div>
                                
                                <!-- Hotel Service -->
                                <div class="rating-item">
                                    <div class="rating-label">
                                        <span class="rating-label-number">5</span>
                                        Hotel's Service
                                    </div>
                                    <div class="rating-stars" data-category="hotel_service">
                                        <span class="star inactive" data-value="1">⭐</span>
                                        <span class="star inactive" data-value="2">⭐</span>
                                        <span class="star inactive" data-value="3">⭐</span>
                                        <span class="star inactive" data-value="4">⭐</span>
                                        <span class="star inactive" data-value="5">⭐</span>
                                    </div>
                                    <div class="text-center mt-3">
                                        <span class="rating-value" id="hotel_service_value">Not rated yet</span>
                                    </div>
                                    <div class="rating-bar">
                                        <div class="rating-fill" id="hotel_service_bar" style="width: 0%"></div>
                                    </div>
                                    <a class="comments-toggle" onclick="toggleComments('hotel_service_comments')">
                                        💬 Add comments about Hotel Service
                                    </a>
                                    <div class="category-comments" id="hotel_service_comments" style="display: none;">
                                        <textarea 
                                            name="hotel_service_comments" 
                                            placeholder="How was staff behavior? Check-in/out experience? Room service?"
                                            rows="2"></textarea>
                                    </div>
                                    <input type="hidden" name="hotel_service" id="hotel_service" value="" required>
                                </div>
                                
                                <!-- General Comments -->
                                <div class="mb-4">
                                    <label for="general_comments" class="form-label">
                                        <strong>📝 Overall Experience & General Comments (Optional)</strong>
                                    </label>
                                    <textarea class="form-control" id="general_comments" name="general_comments" 
                                              rows="4" placeholder="Share your overall experience, any additional feedback, or suggestions for improvement..."></textarea>
                                    <div class="form-text">Your overall feedback helps us serve you better</div>
                                </div>
                                
                                <!-- Submit Button -->
                                <div class="d-grid gap-2">
                                    <button type="submit" class="btn btn-success btn-lg py-3">
                                        ✅ Submit Complete Feedback
                                    </button>
                                    <a href="/" class="btn btn-outline-secondary">← Back to Home</a>
                                </div>
                            </form>
                        </div>
                        <div class="card-footer text-center">
                            <small>Rate each category and add specific comments for detailed feedback</small>
                        </div>
                    </div>
                    
                    <!-- Info Box -->
                    <div class="alert alert-info mt-4">
                        <h5>📋 How to use this feedback form:</h5>
                        <ol class="mb-0">
                            <li><strong>Click stars</strong> to rate each category (1-5 stars)</li>
                            <li><strong>Click "Add comments"</strong> below any category to provide specific feedback</li>
                            <li>Each star has its own color: Red(1) → Orange(2) → Yellow(3) → Green(4) → Blue(5)</li>
                            <li>You must rate ALL 5 categories before submitting</li>
                            <li>Add overall comments if you wish</li>
                            <li>Click "Submit Complete Feedback" when done</li>
                        </ol>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- JavaScript for Star Rating -->
        <script>
            // Function to toggle comments section
            function toggleComments(commentId) {{
                const commentSection = document.getElementById(commentId);
                const link = event.target;
                
                if (commentSection.style.display === 'none') {{
                    commentSection.style.display = 'block';
                    link.textContent = '💬 Hide comments';
                }} else {{
                    commentSection.style.display = 'none';
                    link.textContent = '💬 Add comments';
                }}
                
                // Smooth scroll to show the comments
                commentSection.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
            }}
            
            document.addEventListener('DOMContentLoaded', function() {{
                // Rating texts with emojis
                const ratingTexts = {{
                    1: '😞 Poor (1/5)',
                    2: '😐 Fair (2/5)',
                    3: '🙂 Good (3/5)',
                    4: '😊 Very Good (4/5)',
                    5: '😍 Excellent (5/5)'
                }};
                
                // Bar gradient classes
                const barClasses = {{
                    1: 'bar-1',
                    2: 'bar-2',
                    3: 'bar-3',
                    4: 'bar-4',
                    5: 'bar-5'
                }};
                
                // Value display classes
                const valueClasses = {{
                    1: 'value-bg-1',
                    2: 'value-bg-2',
                    3: 'value-bg-3',
                    4: 'value-bg-4',
                    5: 'value-bg-5'
                }};
                
                // Initialize all rating systems
                const ratingCategories = [
                    'food_quality', 
                    'seating_arrangement', 
                    'parking', 
                    'washroom', 
                    'hotel_service'
                ];
                
                // Setup each rating category
                ratingCategories.forEach(category => {{
                    const stars = document.querySelectorAll(`[data-category="${{category}}"] .star`);
                    const hiddenInput = document.getElementById(category);
                    const valueDisplay = document.getElementById(`${{category}}_value`);
                    const barFill = document.getElementById(`${{category}}_bar`);
                    
                    // Function to update stars based on selected value
                    function updateStars(selectedValue) {{
                        stars.forEach(star => {{
                            const starValue = parseInt(star.getAttribute('data-value'));
                            
                            if (starValue <= selectedValue) {{
                                // Activate stars up to selected value
                                star.classList.remove('inactive');
                                star.classList.add('active');
                                star.style.filter = 'drop-shadow(0 2px 4px rgba(0,0,0,0.3))';
                            }} else {{
                                // Deactivate stars beyond selected value
                                star.classList.remove('active');
                                star.classList.add('inactive');
                                star.style.filter = 'none';
                            }}
                        }});
                        
                        // Update progress bar
                        const barWidth = (selectedValue / 5) * 100;
                        barFill.style.width = barWidth + '%';
                        
                        // Update bar color class
                        barFill.className = 'rating-fill ' + (barClasses[selectedValue] || '');
                        
                        // Update value display
                        valueDisplay.textContent = ratingTexts[selectedValue];
                        valueDisplay.className = 'rating-value ' + valueClasses[selectedValue];
                        
                        // Update hidden input
                        hiddenInput.value = selectedValue;
                    }}
                    
                    // Add click event to each star
                    stars.forEach(star => {{
                        star.addEventListener('click', function() {{
                            const value = parseInt(this.getAttribute('data-value'));
                            updateStars(value);
                        }});
                        
                        // Hover effect - preview
                        star.addEventListener('mouseover', function() {{
                            const hoverValue = parseInt(this.getAttribute('data-value'));
                            stars.forEach(s => {{
                                const starValue = parseInt(s.getAttribute('data-value'));
                                if (starValue <= hoverValue) {{
                                    s.style.transform = 'scale(1.2)';
                                    s.style.filter = 'drop-shadow(0 3px 5px rgba(0,0,0,0.4))';
                                }}
                            }});
                        }});
                        
                        star.addEventListener('mouseout', function() {{
                            const currentValue = parseInt(hiddenInput.value) || 0;
                            stars.forEach(s => {{
                                const starValue = parseInt(s.getAttribute('data-value'));
                                s.style.transform = starValue <= currentValue ? 'scale(1.1)' : 'scale(1)';
                                s.style.filter = starValue <= currentValue ? 'drop-shadow(0 2px 4px rgba(0,0,0,0.3))' : 'none';
                            }});
                        }});
                    }});
                }});
                
                // Form validation
                document.getElementById('feedbackForm').addEventListener('submit', function(e) {{
                    let allRated = true;
                    const missingCategories = [];
                    
                    ratingCategories.forEach(category => {{
                        const value = document.getElementById(category).value;
                        if (!value) {{
                            allRated = false;
                            // Format category name for display
                            const formattedName = category
                                .replace('_', ' ')
                                .replace(/\b\w/g, l => l.toUpperCase());
                            missingCategories.push(formattedName);
                        }}
                    }});
                    
                    if (!allRated) {{
                        e.preventDefault();
                        const missingList = missingCategories.join(', ');
                        alert(`Please rate all categories before submitting:\\n\\n${{missingList}}`);
                        
                        // Highlight missing categories with animation
                        missingCategories.forEach(cat => {{
                            const categoryId = cat.toLowerCase().replace(' ', '_');
                            const element = document.querySelector(`[data-category="${{categoryId}}"]`);
                            if (element) {{
                                element.parentElement.style.border = '2px solid #ff6b6b';
                                element.parentElement.style.animation = 'pulse 0.5s 3';
                            }}
                        }});
                        
                        return false;
                    }}
                }});
                
                // Add CSS animation for highlighting
                const style = document.createElement('style');
                style.textContent = `
                    @keyframes pulse {{
                        0% {{ box-shadow: 0 0 0 0 rgba(255, 107, 107, 0.7); }}
                        70% {{ box-shadow: 0 0 0 10px rgba(255, 107, 107, 0); }}
                        100% {{ box-shadow: 0 0 0 0 rgba(255, 107, 107, 0); }}
                    }}
                `;
                document.head.appendChild(style);
            }});
        </script>
    </body>
    </html>
    """

# ------------------- ADMIN DASHBOARD (PROTECTED) -------------------
@app.route("/admin")
@admin_required
def admin():
    try:
        conn = sqlite3.connect(os.path.join(DB_FOLDER, "reviews.db"))
        cur = conn.cursor()
        cur.execute("SELECT * FROM reviews ORDER BY created_at DESC")
        reviews = cur.fetchall()
        
        # Calculate averages
        cur.execute("""
            SELECT 
                COUNT(*) as total_reviews,
                AVG(food_quality) as avg_food_quality,
                AVG(seating_arrangement) as avg_seating,
                AVG(parking) as avg_parking,
                AVG(washroom) as avg_washroom,
                AVG(hotel_service) as avg_service,
                AVG((food_quality + seating_arrangement + parking + washroom + hotel_service) / 5.0) as avg_overall
            FROM reviews
        """)
        stats = cur.fetchone()
        
        # Get recent alerts (last 24 hours)
        recent_alerts = get_recent_alerts(hours=24)
        total_alerts = len(recent_alerts)
        
        # Get low rating categories
        low_rating_categories = []
        if stats[1] and stats[1] < ALERT_THRESHOLDS['food_quality']:
            low_rating_categories.append(f"Food Quality ({stats[1]:.1f}/5)")
        if stats[2] and stats[2] < ALERT_THRESHOLDS['seating_arrangement']:
            low_rating_categories.append(f"Seating ({stats[2]:.1f}/5)")
        if stats[3] and stats[3] < ALERT_THRESHOLDS['parking']:
            low_rating_categories.append(f"Parking ({stats[3]:.1f}/5)")
        if stats[4] and stats[4] < ALERT_THRESHOLDS['washroom']:
            low_rating_categories.append(f"Washroom ({stats[4]:.1f}/5)")
        if stats[5] and stats[5] < ALERT_THRESHOLDS['hotel_service']:
            low_rating_categories.append(f"Service ({stats[5]:.1f}/5)")
        
        conn.close()
        
        # Create feedback cards
        feedback_cards = ""
        for review in reviews:
            # Format date
            created_at = review[12]
            if created_at:
                try:
                    date_obj = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                    formatted_date = date_obj.strftime('%d %b %Y, %I:%M %p')
                    short_date = date_obj.strftime('%Y-%m-%d')
                except:
                    formatted_date = created_at[:10] if len(created_at) > 10 else created_at
                    short_date = created_at[:10] if len(created_at) > 10 else created_at
            else:
                formatted_date = "No date"
                short_date = "No date"
            
            # Check if there are any comments
            has_comments = any([
                review[2],  # food comments
                review[4],  # seating comments
                review[6],  # parking comments
                review[8],  # washroom comments
                review[10], # service comments
                review[11]  # general comments
            ])
            
            # Check for low ratings
            has_low_rating = any([
                review[1] < ALERT_THRESHOLDS['food_quality'],
                review[3] < ALERT_THRESHOLDS['seating_arrangement'],
                review[5] < ALERT_THRESHOLDS['parking'],
                review[7] < ALERT_THRESHOLDS['washroom'],
                review[9] < ALERT_THRESHOLDS['hotel_service']
            ])
            
            # Generate card HTML
            alert_badge = '<span class="alert-badge">⚠️ Low Rating</span>' if has_low_rating else ''
            
            feedback_cards += f'''
            <div class="feedback-card" id="feedback-{review[0]}">
                <div class="feedback-header">
                    <span class="feedback-date"><i class="fas fa-calendar"></i> {formatted_date}</span>
                    <span class="feedback-id">ID: {review[0]} {alert_badge}</span>
                </div>
                
                <div class="feedback-ratings">
                    <div class="rating-row {'low-rating' if review[1] < ALERT_THRESHOLDS['food_quality'] else ''}">
                        <span class="rating-category"><i class="fas fa-utensils"></i> Food Quality:</span>
                        <span class="rating-stars">{"⭐" * review[1]}</span>
                        <span class="rating-value">{get_rating_emoji(review[1])} {review[1]}/5</span>
                    </div>
                    
                    <div class="rating-row {'low-rating' if review[3] < ALERT_THRESHOLDS['seating_arrangement'] else ''}">
                        <span class="rating-category"><i class="fas fa-chair"></i> Seating Arrangement:</span>
                        <span class="rating-stars">{"⭐" * review[3]}</span>
                        <span class="rating-value">{get_rating_emoji(review[3])} {review[3]}/5</span>
                    </div>
                    
                    <div class="rating-row {'low-rating' if review[5] < ALERT_THRESHOLDS['parking'] else ''}">
                        <span class="rating-category"><i class="fas fa-parking"></i> Parking Facility:</span>
                        <span class="rating-stars">{"⭐" * review[5]}</span>
                        <span class="rating-value">{get_rating_emoji(review[5])} {review[5]}/5</span>
                    </div>
                    
                    <div class="rating-row {'low-rating' if review[7] < ALERT_THRESHOLDS['washroom'] else ''}">
                        <span class="rating-category"><i class="fas fa-restroom"></i> Washroom Cleanliness:</span>
                        <span class="rating-stars">{"⭐" * review[7]}</span>
                        <span class="rating-value">{get_rating_emoji(review[7])} {review[7]}/5</span>
                    </div>
                    
                    <div class="rating-row {'low-rating' if review[9] < ALERT_THRESHOLDS['hotel_service'] else ''}">
                        <span class="rating-category"><i class="fas fa-concierge-bell"></i> Hotel Service:</span>
                        <span class="rating-stars">{"⭐" * review[9]}</span>
                        <span class="rating-value">{get_rating_emoji(review[9])} {review[9]}/5</span>
                    </div>
                </div>
                
                <div class="feedback-overall">
                    <div class="overall-rating">
                        <strong><i class="fas fa-chart-line"></i> Overall Average:</strong>
                        <span class="overall-score">{((review[1] + review[3] + review[5] + review[7] + review[9]) / 5):.1f}/5.0</span>
                    </div>
                </div>
            '''
            
            # Add comments section if there are any comments
            if has_comments:
                feedback_cards += '''
                <div class="feedback-comments-section">
                    <h6><i class="fas fa-comment"></i> Comments:</h6>
                    <div class="comments-grid">
                '''
                
                # Food comments
                if review[2]:
                    feedback_cards += f'''
                    <div class="comment-item">
                        <span class="comment-label"><i class="fas fa-utensils"></i> Food:</span>
                        <span class="comment-text">{review[2]}</span>
                    </div>
                    '''
                
                # Seating comments
                if review[4]:
                    feedback_cards += f'''
                    <div class="comment-item">
                        <span class="comment-label"><i class="fas fa-chair"></i> Seating:</span>
                        <span class="comment-text">{review[4]}</span>
                    </div>
                    '''
                
                # Parking comments
                if review[6]:
                    feedback_cards += f'''
                    <div class="comment-item">
                        <span class="comment-label"><i class="fas fa-parking"></i> Parking:</span>
                        <span class="comment-text">{review[6]}</span>
                    </div>
                    '''
                
                # Washroom comments
                if review[8]:
                    feedback_cards += f'''
                    <div class="comment-item">
                        <span class="comment-label"><i class="fas fa-restroom"></i> Washroom:</span>
                        <span class="comment-text">{review[8]}</span>
                    </div>
                    '''
                
                # Service comments
                if review[10]:
                    feedback_cards += f'''
                    <div class="comment-item">
                        <span class="comment-label"><i class="fas fa-concierge-bell"></i> Service:</span>
                        <span class="comment-text">{review[10]}</span>
                    </div>
                    '''
                
                # General comments
                if review[11]:
                    feedback_cards += f'''
                    <div class="comment-item general-comment">
                        <span class="comment-label"><i class="fas fa-file-alt"></i> General:</span>
                        <span class="comment-text">{review[11]}</span>
                    </div>
                    '''
                
                feedback_cards += '''
                    </div>
                </div>
                '''
            
            feedback_cards += '</div>'
        
        # Generate HTML for recent alerts table
        alerts_table = ""
        if recent_alerts:
            alerts_table = """
            <div class="alert-alerts-section mt-4">
                <h5><i class="fas fa-exclamation-triangle" style="color: #dc3545;"></i> Recent Low Rating Alerts (Last 24 Hours)</h5>
                <div class="table-responsive">
                    <table class="table table-sm table-hover">
                        <thead>
                            <tr>
                                <th>Feedback ID</th>
                                <th>Time</th>
                                <th>Low Categories</th>
                                <th>Rating</th>
                                <th>Comments</th>
                            </tr>
                        </thead>
                        <tbody>
            """
            
            for alert_group in recent_alerts[:10]:  # Show last 10 alerts
                feedback_id = alert_group['feedback_id']
                date_time = alert_group['date']
                
                # Format time
                if date_time:
                    try:
                        time_obj = datetime.strptime(date_time, '%Y-%m-%d %H:%M:%S')
                        time_str = time_obj.strftime('%I:%M %p')
                        date_str = time_obj.strftime('%b %d')
                    except:
                        time_str = date_time[11:16] if len(date_time) > 16 else date_time
                        date_str = date_time[:10]
                else:
                    time_str = ""
                    date_str = ""
                
                # Get low categories
                low_categories = ", ".join([alert['category'] for alert in alert_group['alerts']])
                
                # Get first comment
                first_comment = alert_group['alerts'][0]['comments'][:50] + "..." if len(alert_group['alerts'][0]['comments']) > 50 else alert_group['alerts'][0]['comments']
                
                alerts_table += f"""
                <tr>
                    <td><a href="#feedback-{feedback_id}" style="text-decoration: none;">#{feedback_id}</a></td>
                    <td><small>{date_str}<br>{time_str}</small></td>
                    <td><span class="badge bg-danger">{low_categories}</span></td>
                    <td>{alert_group['alerts'][0]['rating']}/5</td>
                    <td><small>{first_comment}</small></td>
                </tr>
                """
            
            alerts_table += """
                        </tbody>
                    </table>
                </div>
            </div>
            """
        else:
            alerts_table = """
            <div class="alert alert-success mt-4">
                <i class="fas fa-check-circle"></i> No low rating alerts in the last 24 hours. Good job!
            </div>
            """
        
        return f"""
        <html>
        <head>
            <title>Admin Dashboard - {HOTEL_NAME}</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                }}
                
                body {{
                    background-color: #f5f7fa;
                    padding: 20px;
                    color: #333;
                }}
                
                .container {{
                    max-width: 1400px;
                    margin: 0 auto;
                }}
                
                .hotel-header {{
                    background: linear-gradient(135deg, #0d6efd 0%, #198754 100%);
                    color: white;
                    padding: 1.5rem 0;
                    margin-bottom: 2rem;
                    border-radius: 15px;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                    text-align: center;
                }}
                
                .hotel-logo {{
                    width: 180px;
                    height: 140px;
                    object-fit: cover;
                    border-radius: 10px;
                    border: 3px solid white;
                    box-shadow: 0 4px 8px rgba(0,0,0,0.2);
                    margin: 15px auto;
                    display: block;
                }}
                
                .dashboard-header {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 25px;
                    flex-wrap: wrap;
                    gap: 15px;
                }}
                
                .stats-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 20px;
                    margin-bottom: 30px;
                }}
                
                .stat-card {{
                    background: white;
                    border-radius: 10px;
                    padding: 20px;
                    box-shadow: 0 3px 10px rgba(0,0,0,0.08);
                    text-align: center;
                    transition: transform 0.3s;
                }}
                
                .stat-card:hover {{
                    transform: translateY(-5px);
                    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                }}
                
                .stat-card.primary {{
                    border-top: 4px solid #0d6efd;
                }}
                
                .stat-card.success {{
                    border-top: 4px solid #198754;
                }}
                
                .stat-card.warning {{
                    border-top: 4px solid #ffc107;
                }}
                
                .stat-card.info {{
                    border-top: 4px solid #17a2b8;
                }}
                
                .stat-card.danger {{
                    border-top: 4px solid #dc3545;
                }}
                
                .stat-card.critical {{
                    border-top: 4px solid #dc3545;
                    animation: pulse 2s infinite;
                }}
                
                .stat-card h3 {{
                    font-size: 2.5rem;
                    margin: 10px 0;
                    color: #2c3e50;
                }}
                
                .stat-card p {{
                    color: #7f8c8d;
                    font-size: 0.9rem;
                }}
                
                .controls {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 25px;
                    flex-wrap: wrap;
                    gap: 15px;
                    background: white;
                    padding: 15px 20px;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                }}
                
                .filter-group {{
                    display: flex;
                    gap: 10px;
                    align-items: center;
                }}
                
                select, input, button {{
                    padding: 10px 15px;
                    border: 1px solid #ddd;
                    border-radius: 6px;
                    font-size: 0.95rem;
                }}
                
                button {{
                    background-color: #3498db;
                    color: white;
                    border: none;
                    cursor: pointer;
                    transition: background-color 0.3s;
                }}
                
                button:hover {{
                    background-color: #2980b9;
                }}
                
                .feedback-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(500px, 1fr));
                    gap: 25px;
                }}
                
                @media (max-width: 768px) {{
                    .feedback-grid {{
                        grid-template-columns: 1fr;
                    }}
                }}
                
                .feedback-card {{
                    background: white;
                    border-radius: 12px;
                    padding: 25px;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.08);
                    transition: all 0.3s ease;
                    border-left: 5px solid #3498db;
                }}
                
                .feedback-card:hover {{
                    transform: translateY(-5px);
                    box-shadow: 0 8px 25px rgba(0,0,0,0.12);
                }}
                
                .feedback-header {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 20px;
                    padding-bottom: 15px;
                    border-bottom: 1px solid #eee;
                }}
                
                .feedback-date {{
                    font-weight: 600;
                    color: #2c3e50;
                    font-size: 1.1rem;
                }}
                
                .feedback-id {{
                    background: #f1f8ff;
                    color: #0366d6;
                    padding: 5px 12px;
                    border-radius: 20px;
                    font-size: 0.85rem;
                    font-weight: 600;
                }}
                
                .alert-badge {{
                    background-color: #dc3545;
                    color: white;
                    padding: 3px 8px;
                    border-radius: 12px;
                    font-size: 0.8rem;
                    margin-left: 10px;
                }}
                
                .feedback-ratings {{
                    margin-bottom: 20px;
                }}
                
                .rating-row {{
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    margin-bottom: 12px;
                    padding: 10px;
                    background: #f8f9fa;
                    border-radius: 8px;
                }}
                
                .rating-row.low-rating {{
                    background-color: #ffeaea;
                    border-left: 4px solid #dc3545;
                }}
                
                .rating-category {{
                    flex: 1;
                    font-weight: 500;
                }}
                
                .rating-stars {{
                    flex: 1;
                    text-align: center;
                    color: #ffc107;
                    font-size: 1.2rem;
                    letter-spacing: 2px;
                }}
                
                .rating-value {{
                    flex: 1;
                    text-align: right;
                    font-weight: 600;
                    color: #2c3e50;
                }}
                
                .feedback-overall {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 15px;
                    border-radius: 10px;
                    margin-bottom: 20px;
                    text-align: center;
                }}
                
                .overall-rating {{
                    font-size: 1.1rem;
                }}
                
                .overall-score {{
                    background: rgba(255,255,255,0.2);
                    padding: 5px 15px;
                    border-radius: 20px;
                    margin-left: 10px;
                    font-weight: 700;
                }}
                
                .feedback-comments-section {{
                    background: #f9f9f9;
                    border-radius: 10px;
                    padding: 20px;
                    margin-top: 20px;
                }}
                
                .comments-grid {{
                    display: grid;
                    gap: 15px;
                    margin-top: 15px;
                }}
                
                .comment-item {{
                    display: flex;
                    gap: 15px;
                    padding: 12px;
                    background: white;
                    border-radius: 8px;
                    border-left: 4px solid #4CAF50;
                }}
                
                .comment-item.general-comment {{
                    border-left-color: #2196F3;
                }}
                
                .comment-label {{
                    font-weight: 600;
                    min-width: 80px;
                    color: #555;
                }}
                
                .comment-text {{
                    flex: 1;
                    color: #333;
                    line-height: 1.5;
                }}
                
                .no-feedback {{
                    text-align: center;
                    padding: 50px 20px;
                    color: #7f8c8d;
                    font-size: 1.2rem;
                }}
                
                .no-feedback i {{
                    font-size: 3rem;
                    margin-bottom: 20px;
                    color: #bdc3c7;
                }}
                
                .summary-card {{
                    background: white;
                    border-radius: 10px;
                    padding: 25px;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.08);
                    margin-bottom: 30px;
                }}
                
                .summary-header {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 20px;
                }}
                
                .summary-title {{
                    font-size: 1.4rem;
                    font-weight: 600;
                    color: #2c3e50;
                }}
                
                .summary-stats {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 15px;
                }}
                
                .summary-stat {{
                    text-align: center;
                    padding: 15px;
                    background: #f8f9fa;
                    border-radius: 8px;
                    border: 2px solid transparent;
                }}
                
                .summary-stat.border-danger {{
                    border-color: #dc3545 !important;
                }}
                
                .summary-stat h4 {{
                    color: #3498db;
                    margin-bottom: 5px;
                }}
                
                .action-buttons {{
                    display: flex;
                    gap: 10px;
                    flex-wrap: wrap;
                }}
                
                .threshold-info {{
                    background-color: #fff3cd;
                    border-left: 4px solid #ffc107;
                    padding: 15px;
                    border-radius: 5px;
                    margin-bottom: 20px;
                }}
                
                .threshold-list {{
                    list-style-type: none;
                    padding-left: 0;
                }}
                
                .threshold-list li {{
                    padding: 5px 0;
                    border-bottom: 1px solid #eee;
                }}
                
                .export-buttons {{
                    display: flex;
                    gap: 10px;
                    margin-top: 20px;
                }}
                
                .alert-alerts-section {{
                    background-color: #f8f9fa;
                    border-radius: 10px;
                    padding: 20px;
                    margin-top: 30px;
                    border: 1px solid #dee2e6;
                }}
                
                @keyframes pulse {{
                    0% {{ box-shadow: 0 0 0 0 rgba(220, 53, 69, 0.4); }}
                    70% {{ box-shadow: 0 0 0 10px rgba(220, 53, 69, 0); }}
                    100% {{ box-shadow: 0 0 0 0 rgba(220, 53, 69, 0); }}
                }}
                
                @media (max-width: 768px) {{
                    .hotel-logo {{
                        width: 150px;
                        height: 120px;
                    }}
                    .dashboard-header {{
                        flex-direction: column;
                        align-items: stretch;
                    }}
                    .action-buttons {{
                        justify-content: center;
                    }}
                    .export-buttons {{
                        flex-direction: column;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <!-- Hotel Header -->
                <div class="hotel-header">
                    <h2><i class="fas fa-user-shield"></i> Admin Dashboard - {HOTEL_NAME}</h2>
                    <p class="lead mb-0">Feedback System with Alerts & Export</p>
                    <div class="mt-3">
                        <img src="/static/{HOTEL_LOGO}" alt="{HOTEL_NAME} Logo" class="hotel-logo">
                    </div>
                    <small class="d-block mt-2">Mobile Access: http://{LOCAL_IP}:5000/admin</small>
                </div>
                
                <!-- Dashboard Header -->
                <div class="dashboard-header">
                    <h3><i class="fas fa-chart-bar"></i> Feedback Overview</h3>
                    <div class="action-buttons">
                        <a href="/generate_qr" class="btn btn-success">
                            <i class="fas fa-qrcode"></i> View QR Code
                        </a>
                        <a href="/test_email" class="btn btn-info">
                            <i class="fas fa-envelope"></i> Test Email
                        </a>
                        <a href="/" class="btn btn-primary">
                            <i class="fas fa-home"></i> Home
                        </a>
                        <a href="/review" class="btn btn-warning">
                            <i class="fas fa-plus"></i> Test Form
                        </a>
                    </div>
                </div>
                
                <!-- Threshold Information -->
                <div class="threshold-info">
                    <h5><i class="fas fa-exclamation-circle" style="color: #ffc107;"></i> Alert Thresholds</h5>
                    <p>Alerts are triggered when ratings fall below these thresholds:</p>
                    <div class="row">
                        <div class="col-md-6">
                            <ul class="threshold-list">
                                <li><strong>Food Quality:</strong> Below {ALERT_THRESHOLDS['food_quality']}/5</li>
                                <li><strong>Seating Arrangement:</strong> Below {ALERT_THRESHOLDS['seating_arrangement']}/5</li>
                                <li><strong>Parking Facility:</strong> Below {ALERT_THRESHOLDS['parking']}/5</li>
                            </ul>
                        </div>
                        <div class="col-md-6">
                            <ul class="threshold-list">
                                <li><strong>Washroom Cleanliness:</strong> Below {ALERT_THRESHOLDS['washroom']}/5</li>
                                <li><strong>Hotel Service:</strong> Below {ALERT_THRESHOLDS['hotel_service']}/5</li>
                                <li><strong>Overall Average:</strong> Below {ALERT_THRESHOLDS['overall']}/5</li>
                            </ul>
                        </div>
                    </div>
                </div>
                
                <!-- Statistics Grid -->
                <div class="stats-grid">
                    <div class="stat-card primary">
                        <i class="fas fa-comments fa-2x mb-3" style="color: #0d6efd;"></i>
                        <h3>{stats[0] or 0}</h3>
                        <p>Total Feedbacks</p>
                    </div>
                    
                    <div class="stat-card {'critical' if stats[6] and stats[6] < ALERT_THRESHOLDS['overall'] else 'success'}">
                        <i class="fas fa-star fa-2x mb-3" style="color: {'#dc3545' if stats[6] and stats[6] < ALERT_THRESHOLDS['overall'] else '#198754'}"></i>
                        <h3>{'%.1f' % (stats[6] or 0) if stats[6] else '0.0'}/5.0</h3>
                        <p>Overall Average</p>
                        {'<small style="color: #dc3545;">⚠️ Below threshold</small>' if stats[6] and stats[6] < ALERT_THRESHOLDS['overall'] else ''}
                    </div>
                    
                    <div class="stat-card {'critical' if stats[1] and stats[1] < ALERT_THRESHOLDS['food_quality'] else 'warning'}">
                        <i class="fas fa-utensils fa-2x mb-3" style="color: {'#dc3545' if stats[1] and stats[1] < ALERT_THRESHOLDS['food_quality'] else '#ffc107'}"></i>
                        <h3>{'%.1f' % (stats[1] or 0) if stats[1] else '0.0'}/5.0</h3>
                        <p>Food Quality Avg</p>
                    </div>
                    
                    <div class="stat-card {'critical' if stats[5] and stats[5] < ALERT_THRESHOLDS['hotel_service'] else 'info'}">
                        <i class="fas fa-concierge-bell fa-2x mb-3" style="color: {'#dc3545' if stats[5] and stats[5] < ALERT_THRESHOLDS['hotel_service'] else '#17a2b8'}"></i>
                        <h3>{'%.1f' % (stats[5] or 0) if stats[5] else '0.0'}/5.0</h3>
                        <p>Service Avg</p>
                    </div>
                </div>
                
                <!-- Export Buttons -->
                <div class="export-buttons">
                    <a href="/admin/export/csv" class="btn btn-success">
                        <i class="fas fa-file-csv"></i> Export All Data to CSV
                    </a>
                    <a href="/admin/export/recent_alerts_csv" class="btn btn-danger">
                        <i class="fas fa-exclamation-triangle"></i> Export Recent Alerts to CSV
                    </a>
                </div>
                
                <!-- Recent Alerts Section -->
                {alerts_table}
                
                <!-- Summary Card -->
                <div class="summary-card">
                    <div class="summary-header">
                        <div class="summary-title"><i class="fas fa-chart-line"></i> Category Averages</div>
                        <small>Based on {stats[0] or 0} feedback submissions</small>
                    </div>
                    <div class="summary-stats">
                        <div class="summary-stat {'border-danger' if stats[1] and stats[1] < ALERT_THRESHOLDS['food_quality'] else ''}">
                            <h4 style="color: {'#dc3545' if stats[1] and stats[1] < ALERT_THRESHOLDS['food_quality'] else '#3498db'}">
                                {'%.1f' % (stats[1] or 0) if stats[1] else '0.0'}/5.0
                                {'<i class="fas fa-exclamation-triangle" style="color: #dc3545;"></i>' if stats[1] and stats[1] < ALERT_THRESHOLDS['food_quality'] else ''}
                            </h4>
                            <p><i class="fas fa-utensils"></i> Food Quality</p>
                        </div>
                        <div class="summary-stat {'border-danger' if stats[2] and stats[2] < ALERT_THRESHOLDS['seating_arrangement'] else ''}">
                            <h4 style="color: {'#dc3545' if stats[2] and stats[2] < ALERT_THRESHOLDS['seating_arrangement'] else '#3498db'}">
                                {'%.1f' % (stats[2] or 0) if stats[2] else '0.0'}/5.0
                                {'<i class="fas fa-exclamation-triangle" style="color: #dc3545;"></i>' if stats[2] and stats[2] < ALERT_THRESHOLDS['seating_arrangement'] else ''}
                            </h4>
                            <p><i class="fas fa-chair"></i> Seating Arrangement</p>
                        </div>
                        <div class="summary-stat {'border-danger' if stats[3] and stats[3] < ALERT_THRESHOLDS['parking'] else ''}">
                            <h4 style="color: {'#dc3545' if stats[3] and stats[3] < ALERT_THRESHOLDS['parking'] else '#3498db'}">
                                {'%.1f' % (stats[3] or 0) if stats[3] else '0.0'}/5.0
                                {'<i class="fas fa-exclamation-triangle" style="color: #dc3545;"></i>' if stats[3] and stats[3] < ALERT_THRESHOLDS['parking'] else ''}
                            </h4>
                            <p><i class="fas fa-parking"></i> Parking Facility</p>
                        </div>
                        <div class="summary-stat {'border-danger' if stats[4] and stats[4] < ALERT_THRESHOLDS['washroom'] else ''}">
                            <h4 style="color: {'#dc3545' if stats[4] and stats[4] < ALERT_THRESHOLDS['washroom'] else '#3498db'}">
                                {'%.1f' % (stats[4] or 0) if stats[4] else '0.0'}/5.0
                                {'<i class="fas fa-exclamation-triangle" style="color: #dc3545;"></i>' if stats[4] and stats[4] < ALERT_THRESHOLDS['washroom'] else ''}
                            </h4>
                            <p><i class="fas fa-restroom"></i> Washroom Cleanliness</p>
                        </div>
                        <div class="summary-stat {'border-danger' if stats[5] and stats[5] < ALERT_THRESHOLDS['hotel_service'] else ''}">
                            <h4 style="color: {'#dc3545' if stats[5] and stats[5] < ALERT_THRESHOLDS['hotel_service'] else '#3498db'}">
                                {'%.1f' % (stats[5] or 0) if stats[5] else '0.0'}/5.0
                                {'<i class="fas fa-exclamation-triangle" style="color: #dc3545;"></i>' if stats[5] and stats[5] < ALERT_THRESHOLDS['hotel_service'] else ''}
                            </h4>
                            <p><i class="fas fa-concierge-bell"></i> Hotel Service</p>
                        </div>
                    </div>
                </div>
                
                <!-- Controls -->
                <div class="controls">
                    <div>
                        <h5 style="margin: 0;"><i class="fas fa-list"></i> All Feedback Entries ({len(reviews)})</h5>
                        <small style="color: #7f8c8d;">Showing most recent first</small>
                    </div>
                    <div class="filter-group">
                        <select id="filterCategory">
                            <option value="all">All Categories</option>
                            <option value="food">Food Quality</option>
                            <option value="seating">Seating</option>
                            <option value="parking">Parking</option>
                            <option value="washroom">Washroom</option>
                            <option value="service">Service</option>
                        </select>
                        <input type="text" id="searchInput" placeholder="Search feedback...">
                        <button onclick="filterFeedback()"><i class="fas fa-filter"></i> Filter</button>
                    </div>
                </div>
                
                <!-- Feedback Cards Grid -->
                <div class="feedback-grid">
                    {feedback_cards if feedback_cards else '''
                    <div class="no-feedback">
                        <i class="fas fa-inbox"></i>
                        <h3>No feedback yet</h3>
                        <p>No feedback submissions have been received.</p>
                        <p>Generate QR code and share with customers to collect feedback.</p>
                        <a href="/generate_qr" class="btn btn-primary mt-3"><i class="fas fa-qrcode"></i> Generate QR Code</a>
                    </div>
                    '''}
                </div>
                
                <!-- Footer -->
                <div class="text-center mt-5 mb-3" style="color: #7f8c8d;">
                    <small>{HOTEL_NAME} &copy; 2024 - Feedback Management System v2.0</small>
                    <br><small>Features: CSV Export | Email Alerts | Rating Thresholds</small>
                </div>
            </div>
            
            <script>
                function filterFeedback() {{
                    const category = document.getElementById('filterCategory').value;
                    const searchTerm = document.getElementById('searchInput').value.toLowerCase();
                    const cards = document.querySelectorAll('.feedback-card');
                    
                    cards.forEach(card => {{
                        const cardText = card.textContent.toLowerCase();
                        const hasSearchTerm = searchTerm === '' || cardText.includes(searchTerm);
                        
                        let hasCategory = true;
                        if (category !== 'all') {{
                            const categoryKeywords = {{
                                'food': ['food', 'utensils'],
                                'seating': ['seating', 'chair'],
                                'parking': ['parking'],
                                'washroom': ['washroom', 'restroom'],
                                'service': ['service', 'concierge']
                            }};
                            
                            const keywords = categoryKeywords[category] || [];
                            hasCategory = keywords.some(keyword => cardText.includes(keyword));
                        }}
                        
                        if (hasSearchTerm && hasCategory) {{
                            card.style.display = 'block';
                        }} else {{
                            card.style.display = 'none';
                        }}
                    }});
                }}
                
                // Add keyboard shortcut for search (Ctrl+F)
                document.addEventListener('keydown', function(e) {{
                    if (e.ctrlKey && e.key === 'f') {{
                        e.preventDefault();
                        document.getElementById('searchInput').focus();
                    }}
                }});
            </script>
        </body>
        </html>
        """
    except Exception as e:
        return f"""
        <html>
        <head>
            <title>Admin Error</title>
        </head>
        <body>
            <h2>Admin Error</h2>
            <p>Error: {str(e)}</p>
            <a href="/">Home</a>
        </body>
        </html>
        """

# ------------------- SERVE STATIC FILES -------------------
@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory(STATIC_FOLDER, filename)

# ------------------- SERVE QR FILES -------------------
@app.route("/qr_codes/<filename>")
def serve_qr(filename):
    return send_from_directory(QR_FOLDER, filename)

# ------------------- INITIALIZE & RUN -------------------
if __name__ == "__main__":
    # Check if hotel logo exists
    logo_path = os.path.join(STATIC_FOLDER, HOTEL_LOGO)
    if not os.path.exists(logo_path):
        print(f"⚠️ Warning: Hotel logo '{HOTEL_LOGO}' not found in static folder.")
        print(f"📁 Please place the image in: {STATIC_FOLDER}")
        print("Using placeholder image...")
    
    # Check and fix database
    check_and_fix_db()
    
    # Test email configuration
    email_test_result = test_email_config()
    
    print("\n" + "="*60)
    print(f"🚀 {HOTEL_NAME} - Hotel Feedback System Starting...")
    print(f"🏨 Hotel Logo: {HOTEL_LOGO}")
    print(f"📧 Email Status: {'✅ CONFIGURED' if email_test_result else '❌ NOT CONFIGURED'}")
    print(f"📊 Admin Dashboard: Enhanced with CSV Export & Alerts")
    print(f"📈 Alert Thresholds: Food={ALERT_THRESHOLDS['food_quality']}, Service={ALERT_THRESHOLDS['hotel_service']}")
    print(f"📧 Email Alerts: {'ENABLED' if EMAIL_CONFIG['enable_emails'] else 'DISABLED (configure EMAIL_CONFIG to enable)'}")
    print(f"📁 CSV Export: /admin/export/csv (Admin only)")
    print(f"📧 Email Test: /test_email (Admin only)")
    print(f"💻 Local Access: http://127.0.0.1:5000")
    print(f"📱 Mobile Access: http://{LOCAL_IP}:5000")
    print(f"🔒 Admin Login: admin / harshal@2002")
    print("="*60 + "\n")
    
    if not email_test_result:
        print("⚠️  EMAIL ALERTS MAY NOT WORK!")
        print("   To fix email issues:")
        print("   1. For Gmail, create an App Password (not regular password)")
        print("   2. Update EMAIL_CONFIG['sender_password'] with the 16-character App Password")
        print("   3. Make sure EMAIL_CONFIG['enable_emails'] is set to True")
        print("\n   You can still test the system, but emails won't be sent until fixed.\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)