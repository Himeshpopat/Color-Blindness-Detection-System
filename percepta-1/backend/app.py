import os
import random
from flask import Flask, request, jsonify, send_from_directory
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime
from bson.objectid import ObjectId

app = Flask(__name__)
bcrypt = Bcrypt(app)
CORS(app) 

# --- MongoDB Connection ---
# Ensure your IP is whitelisted in MongoDB Atlas if using a cloud cluster
client = MongoClient("mongodb+srv://sarasant:Percepta@percepta.xmulb2d.mongodb.net/percepta?retryWrites=true&w=majority")
db = client["cvd"]
users = db["user"]
reports = db["reports"]
test_sessions = db["test_sessions"]

# --- Path to Dataset ---
IMAGE_FOLDER = os.path.join('Ishihara blind test cards', 'data')

# --- Diagnostic Plate Mapping ---
DIAGNOSTIC_MAP = {
    "control": ['12'],                                # Visible to everyone
    "protan": ['2', '4', '6', '42', '81', '37'],      # Red deficiency (L-cones)
    "deutan": ['3', '5', '7', '45', '73', '49'],      # Green deficiency (M-cones)
    "tritan": ['1', '8', '9'],                        # Blue-Yellow deficiency (S-cones)
}

@app.route("/api/get_test", methods=["GET"])
def get_test():
    try:
        all_images = [f for f in os.listdir(IMAGE_FOLDER) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        sample_images = random.sample(all_images, 10)
        
        test_set = []
        for filename in sample_images:
            answer = filename.split('_')[0]
            category = "general"
            for key, values in DIAGNOSTIC_MAP.items():
                if answer in values:
                    category = key
                    break
            
            test_set.append({
                "image_url": f"http://127.0.0.1:5000/static_images/{filename}",
                "answer": answer,
                "category": category
            })
        return jsonify(test_set), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/static_images/<path:filename>')
def custom_static(filename):
    return send_from_directory(IMAGE_FOLDER, filename)

# --- Session Tracking Routes ---

@app.route("/api/start_session", methods=["POST"])
def start_session():
    try:
        data = request.get_json()
        session_id = test_sessions.insert_one({
            "username": data.get("username"),
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": "In Progress"
        }).inserted_id
        return jsonify({"session_id": str(session_id)}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/end_session", methods=["POST"])
def end_session():
    try:
        data = request.get_json()
        session_id = data.get("session_id")
        
        test_sessions.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": {"end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}}
        )
        return jsonify({"message": "Session ended successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Authentication Routes ---

@app.route("/signup", methods=["POST"])
def signup():
    try:
        data = request.get_json()
        if users.find_one({"username": data.get("username")}):
            return jsonify({"error": "Username already exists"}), 409
        
        # Hash the password and decode to string for MongoDB storage
        hashed_pw = bcrypt.generate_password_hash(data.get("password")).decode("utf-8")
        
        users.insert_one({
            "name": data.get("name"),
            "age": data.get("age"),
            "username": data.get("username"),
            "email": data.get("email"),
            "password": hashed_pw,
            "createdAt": datetime.utcnow()
        })
        return jsonify({"message": "Signup successful"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")

        user = users.find_one({"username": username})
        
        if not user:
            print(f"Login attempt failed: User '{username}' not found.")
            return jsonify({"error": "Invalid credentials"}), 401

        # Check the hashed password
        if bcrypt.check_password_hash(user["password"], password):
            print(f"Login successful for user: {username}")
            return jsonify({
                "message": "Login successful", 
                "username": user["username"],
                "name": user.get("name", "User")
            }), 200
        else:
            print(f"Login attempt failed: Incorrect password for '{username}'.")
            return jsonify({"error": "Invalid credentials"}), 401
            
    except Exception as e:
        print(f"Login Error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

# --- Reports Route ---

@app.route("/api/save_report", methods=["POST"])
def save_report():
    try:
        data = request.get_json()
        reports.insert_one({
            "username": data.get("username"), 
            "result": data.get("result"),
            "score": data.get("score"), 
            "percentage": data.get("percentage"),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        return jsonify({"message": "Report saved"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/get_reports/<username>", methods=["GET"])
def get_user_reports(username):
    user_reports = list(reports.find({"username": username}).sort("_id", -1))
    for r in user_reports:
        r["_id"] = str(r["_id"])
    return jsonify(user_reports), 200

if __name__ == "__main__":
    app.run(debug=True, port=5000)