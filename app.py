import os
import pandas as pd
import time
import json
import re
import smtplib
import ssl
import requests
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify, Response, stream_with_context, redirect
from flask_cors import CORS
import google.generativeai as genai
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, auth, firestore
from datetime import datetime
import stripe
from werkzeug.utils import secure_filename

# --- Initialization ---
load_dotenv()
app = Flask(__name__)
# Extension ki ID ko yahan add karein
# =================================================================
CHROME_EXTENSION_ORIGIN = "chrome-extension://aealgniiohdlafbfgenillkbcahodfcj" 

CORS(app, resources={
    r"/api/*": {
        "origins": [
            "http://127.0.0.1:5500",
            "http://localhost:5500",
            "null",
            "https://client-hunter-mvz6gyei3-rossycoders-projects.vercel.app",
            CHROME_EXTENSION_ORIGIN
        ]
    }
})
# YEH DOOSRI LINE GHALAT HAI AUR MASLA KAR RAHI HAI
CORS(app, resources={r"/api/*": {"origins": ["http://127.0.0.1:5500", "http://localhost:5500", "null"]}})

# --- Firebase & Stripe Configuration ---
try:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("✅ Firebase Admin SDK configured successfully!")
except Exception as e:
    print(f"❌ Error initializing Firebase Admin SDK: {e}")
    db = None

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
YOUR_DOMAIN = 'https://client-hunter-a.vercel.app/'

# --- Helper Functions ---
def get_user_from_token(request):
    """Verifies Firebase ID token from Authorization header and returns user UID."""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return None, (jsonify({"error": "Authorization header is missing"}), 401)
        id_token = auth_header.split('Bearer ')[1]
        decoded_token = auth.verify_id_token(id_token, clock_skew_seconds=30)
        return decoded_token['uid'], None
    except Exception as e:
        print(f"Token verification failed: {e}")
        return None, (jsonify({"error": "Unauthorized request. Invalid token."}), 401)

def get_user_settings(uid):
    """Fetches user settings (API keys, email config) from Firestore."""
    if not db: return {}
    try:
        settings_ref = db.collection('users').document(uid).collection('settings').document('api_keys')
        settings_doc = settings_ref.get()
        return settings_doc.to_dict() if settings_doc.exists else {}
    except Exception as e:
        print(f"Error fetching user settings for {uid}: {e}")
        return {}

# REVERTED: send_email_helper now uses smtplib (Gmail App Password)
def send_email_helper(receiver_email, subject, body, user_settings):
    sender_email = user_settings.get("sender_email")
    sender_password = user_settings.get("sender_password")
    if not sender_email or not sender_password:
        return False, "Gmail credentials not configured in settings."

    message = MIMEMultipart("alternative")
    message["Subject"], message["From"], message["To"] = subject, sender_email, receiver_email
    message.attach(MIMEText(body, "html"))
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_email, message.as_string())
        return True, "Email sent successfully."
    except Exception as e:
        return False, str(e)

# --- API Routes ---

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    uid, error_response = get_user_from_token(request)
    if error_response: return error_response
    settings_ref = db.collection('users').document(uid).collection('settings').document('api_keys')
    if request.method == 'POST':
        try:
            data = request.get_json()
            settings_ref.set(data, merge=True)
            return jsonify({"message": "Settings saved successfully."}), 200
        except Exception as e:
            return jsonify({"error": f"Could not save settings: {e}"}), 500
    else:
        return jsonify(get_user_settings(uid)), 200

@app.route('/api/load-sheet', methods=['POST'])
def load_sheet():
    uid, error_response = get_user_from_token(request)
    if error_response: return error_response
    df = None
    try:
        if 'sheet' in request.files:
            file = request.files['sheet']
            if file.filename == '': return jsonify({"error": "No file selected"}), 400
            if file and file.filename.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                return jsonify({"error": "Invalid file type. Please upload a CSV."}), 400
        elif request.is_json:
            data = request.get_json()
            url = data.get('url')
            if not url: return jsonify({"error": "URL is missing"}), 400
            if 'docs.google.com/spreadsheets/d/' not in url:
                return jsonify({"error": "Invalid Google Sheet URL format."}), 400
            try:
                sheet_id = url.split('/d/')[1].split('/')[0]
                csv_url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv'
                if '#gid=' in url:
                    gid = url.split('#gid=')[1]
                    csv_url += f'&gid={gid}'
                df = pd.read_csv(csv_url)
            except Exception as e:
                 return jsonify({"error": "Could not access Google Sheet. Make sure link is correct & sheet is public ('Anyone with the link')."}), 400
        else:
            return jsonify({"error": "Invalid request. Provide a CSV file or a URL."}), 400

        if df is None or df.empty:
            return jsonify({"error": "The provided file or sheet is empty or could not be read."}), 400

        df.columns = [str(col).lower().strip() for col in df.columns]
        if 'score' not in df.columns:
            df['score'] = 0
        leads = df.to_dict(orient='records')
        batch = db.batch()
        leads_ref = db.collection('users').document(uid).collection('leads')
        for lead in leads:
            clean_lead = {k: v if pd.notna(v) else '' for k, v in lead.items()}
            doc_ref = leads_ref.document()
            batch.set(doc_ref, clean_lead)
        batch.commit()
        return jsonify({"message": f"Successfully loaded {len(leads)} leads."}), 200
    except Exception as e:
        print(f"CRITICAL ERROR in load_sheet: {e}")
        return jsonify({"error": f"An unexpected server error occurred: {e}"}), 500

@app.route('/api/leads', methods=['POST'])
def add_single_lead():
    uid, error_response = get_user_from_token(request)
    if error_response: return error_response
    try:
        data = request.get_json()
        if not data or 'client name' not in data or not data['client name']:
            return jsonify({"error": "Client name is required."}), 400
        data['score'] = int(data.get('score', 0))
        leads_ref = db.collection('users').document(uid).collection('leads')
        leads_ref.add(data)
        return jsonify({"message": "Lead added successfully."}), 201
    except Exception as e:
        return jsonify({"error": f"An error occurred: {e}"}), 500

@app.route('/api/leads/<lead_id>/notes', methods=['POST'])
def add_lead_note(lead_id):
    uid, error_response = get_user_from_token(request)
    if error_response: return error_response
    try:
        data = request.get_json()
        note_text = data.get('text')
        if not note_text:
            return jsonify({"error": "Note text is required."}), 400
        notes_ref = db.collection('users').document(uid).collection('leads').document(lead_id).collection('notes')
        notes_ref.add({
            "text": note_text,
            "timestamp": firestore.SERVER_TIMESTAMP
        })
        return jsonify({"message": "Note added successfully."}), 201
    except Exception as e:
        return jsonify({"error": f"Could not add note: {e}"}), 500

@app.route('/api/leads/<lead_id>/score', methods=['PUT'])
def update_lead_score(lead_id):
    uid, error_response = get_user_from_token(request)
    if error_response: return error_response
    try:
        data = request.get_json()
        new_score = data.get('score')
        if new_score is None or not isinstance(new_score, int):
            return jsonify({"error": "Invalid score provided."}), 400
        lead_ref = db.collection('users').document(uid).collection('leads').document(lead_id)
        lead_ref.update({"score": new_score})
        return jsonify({"message": "Score updated successfully."}), 200
    except Exception as e:
        return jsonify({"error": f"Could not update score: {e}"}), 500

@app.route('/api/clear-leads', methods=['POST'])
def clear_leads():
    uid, error_response = get_user_from_token(request)
    if error_response: return error_response
    try:
        leads_ref = db.collection('users').document(uid).collection('leads')
        docs = leads_ref.stream()
        batch = db.batch()
        for doc in docs:
            batch.delete(doc.reference)
        batch.commit()
        return jsonify({"message": "All leads deleted."}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to clear leads: {e}"}), 500

@app.route('/api/sequences', methods=['GET', 'POST'])
def handle_sequences():
    uid, error_response = get_user_from_token(request)
    if error_response: return error_response
    sequences_ref = db.collection('users').document(uid).collection('sequences')
    if request.method == 'POST':
        try:
            data = request.get_json()
            data['created_at'] = firestore.SERVER_TIMESTAMP
            sequences_ref.add(data)
            return jsonify({"message": "Sequence saved."}), 201
        except Exception as e:
            return jsonify({"error": f"Could not save sequence: {e}"}), 500
    else:
        try:
            docs = sequences_ref.order_by("created_at", direction=firestore.Query.DESCENDING).stream()
            sequences = [{"id": doc.id, **doc.to_dict()} for doc in docs]
            return jsonify(sequences), 200
        except Exception as e:
            return jsonify({"error": f"Could not fetch sequences: {e}"}), 500

@app.route('/api/sequences/<sequence_id>', methods=['PUT', 'DELETE'])
def handle_single_sequence(sequence_id):
    uid, error_response = get_user_from_token(request)
    if error_response: return error_response
    sequence_ref = db.collection('users').document(uid).collection('sequences').document(sequence_id)
    if request.method == 'PUT':
        try:
            data = request.get_json()
            sequence_ref.update(data)
            return jsonify({"message": "Sequence updated."}), 200
        except Exception as e:
            return jsonify({"error": f"Could not update sequence: {e}"}), 500
    elif request.method == 'DELETE':
        try:
            sequence_ref.delete()
            return jsonify({"message": "Sequence deleted."}), 200
        except Exception as e:
            return jsonify({"error": f"Could not delete sequence: {e}"}), 500

@app.route('/api/start-campaign', methods=['POST'])
def start_campaign():
    uid, error_response = get_user_from_token(request)
    if error_response: return error_response
    user_settings = get_user_settings(uid)
    gemini_api_key = user_settings.get("gemini_key")
    if not gemini_api_key:
        return Response("data: ❌ Gemini AI API Key not found.\n\ndata: ___END___\n\n", mimetype='text/event-stream')
    try:
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        return Response(f"data: ❌ Invalid Gemini API Key.\n\ndata: ___END___\n\n", mimetype='text/event-stream')
    data = request.get_json()
    sequence = data.get('sequence', {})
    user_prompt = sequence.get('steps', [{}])[0].get('prompt', '')
    campaign_name = sequence.get('name', f"Campaign - {datetime.now().strftime('%Y-%m-%d')}")
    if not user_prompt:
        return Response("data: ❌ Prompt is empty.\n\ndata: ___END___\n\n", mimetype='text/event-stream')
    
    def generate_and_send():
        try:
            leads_ref = db.collection('users').document(uid).collection('leads')
            leads_docs = list(leads_ref.stream())
            total_leads = len(leads_docs)
            if total_leads == 0:
                yield "data: 🤷 No leads found.\n\ndata: ___END___\n\n"
                return
            yield f"data: 🚀 Starting Campaign '{campaign_name}' for {total_leads} leads...\n\n"
            leads_df = pd.DataFrame([doc.to_dict() for doc in leads_docs])
            emails_sent_count = 0
            for index, lead in leads_df.iterrows():
                try:
                    personalized_prompt = user_prompt
                    for col_name in leads_df.columns:
                        placeholder = f"[{col_name}]"
                        value = str(lead.get(col_name, ''))
                        personalized_prompt = re.sub(re.escape(placeholder), value, personalized_prompt, flags=re.IGNORECASE)
                    
                    master_prompt = f"""
                    Act as a world-class business development expert. Your task is to write a professional, persuasive, and personalized cold email.
                    **Your Instruction:** "{personalized_prompt}"
                    **Instructions for the email body:**
                    - Write a compelling and professional email based on the instruction above.
                    - The email should be friendly, clear, and concise.
                    - It must have a strong value proposition and a clear call to action.
                    - Do NOT include a subject line in the body.
                    - Sign off with the name "Rozeena".
                    Return ONLY the HTML body of the email.
                    """

                    email_address = str(lead.get('email', '')).strip()
                    client_name = str(lead.get('client name', 'there'))
                    if not email_address:
                        yield f"data: ⚠️ Skipping '{client_name}' (missing email).\n\n"
                        continue
                    yield f"data: 🤖 ({index + 1}/{total_leads}) Generating for {client_name}...\n\n"
                    
                    response = model.generate_content(master_prompt)
                    time.sleep(2)
                    final_email_body = response.text
                    
                    subject_prompt = f"Based on the following email, write one short and engaging subject line. Only return the text of the subject line itself, and nothing else. Do not include the word 'Subject:'.\n\nEmail Body:\n{final_email_body}"
                    subject_response = model.generate_content(subject_prompt)
                    subject = subject_response.text.strip().replace('"', '').replace('*', '').split('\n')[0]

                    yield f"data: 📧 Sending to {email_address}...\n\n"
                    success, status = send_email_helper(email_address, subject, final_email_body, user_settings)
                    if success:
                        emails_sent_count += 1
                        yield f"data: ✅ Sent to {email_address}.\n\n"
                    else:
                        yield f"data: ❌ Failed for {email_address}: {status}\n\n"
                    time.sleep(1)
                except Exception as e:
                    yield f"data: ❌ Error on lead {lead.get('client name', 'Unknown')}: {e}\n\n"
            
            campaign_summary = {
                "name": campaign_name, "date": firestore.SERVER_TIMESTAMP,
                "leads_targeted": total_leads, "emails_sent": emails_sent_count, "status": "Completed"
            }
            db.collection('users').document(uid).collection('campaigns').add(campaign_summary)
            yield "data: 📈 Campaign summary saved.\n\n"
        except Exception as e:
            yield f"data: ❌ Critical error: {e}\n\n"
        yield "data: ___END___\n\n"
    return Response(stream_with_context(generate_and_send()), mimetype='text/event-stream')

@app.route('/api/create-checkout-session', methods=['POST'])
def create_checkout_session():
    uid, error_response = get_user_from_token(request)
    if error_response: return error_response
    try:
        data = request.get_json()
        price_id = data['price_id']
        checkout_session = stripe.checkout.Session.create(
            line_items=[{'price': price_id, 'quantity': 1}],
            mode='subscription',
            success_url=YOUR_DOMAIN + '/dashboard.html?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=YOUR_DOMAIN + '/pricing.html',
            client_reference_id=uid
        )
        return jsonify({'url': checkout_session.url})
    except Exception as e:
        return jsonify(error=str(e)), 403

if __name__ == '__main__':
    app.run(port=5002, debug=True)
