from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import os

app = Flask(__name__)

# 🔹 Scheduling Data (In-memory; use DB in production)
schedules = {}  # {customer_id: {"date": "YYYY-MM-DD HH:MM", "service": "Consultation", "status": "booked"}}
AVAILABLE_SLOTS = ["09:00", "10:00", "11:00", "14:00", "15:00", "16:00"]  # Example hours

# ✅ Get Available Slots for a Date
@app.route('/scheduling/available/<date>', methods=['GET'])
def get_available_slots(date):
    try:
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        available = []
        for slot in AVAILABLE_SLOTS:
            time_str = f"{date} {slot}"
            if not any(schedule["date"] == time_str for schedule in schedules.values()):
                available.append(slot)
        return jsonify({"date": date, "available_slots": available}), 200
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

# ✅ Book an Appointment
@app.route('/scheduling', methods=['POST'])
def book_appointment():
    data = request.json
    customer_id = data.get('customer_id')  # Could be sender_id from chatbot
    date = data.get('date')  # YYYY-MM-DD
    time = data.get('time')  # HH:MM
    service = data.get('service', "Chatbot Consultation")

    if not all([customer_id, date, time]):
        return jsonify({"error": "Missing required fields"}), 400

    if time not in AVAILABLE_SLOTS:
        return jsonify({"error": "Invalid time slot"}), 400

    full_date = f"{date} {time}"
    if any(schedule["date"] == full_date for schedule in schedules.values()):
        return jsonify({"error": "Slot already booked"}), 400

    schedules[customer_id] = {"date": full_date, "service": service, "status": "booked"}
    return jsonify({"message": "Appointment booked", "details": schedules[customer_id]}), 201

# ✅ Cancel an Appointment
@app.route('/scheduling/<customer_id>', methods=['DELETE'])
def cancel_appointment(customer_id):
    if customer_id in schedules:
        del schedules[customer_id]
        return jsonify({"message": "Appointment canceled"}), 200
    return jsonify({"error": "Appointment not found"}), 404

# ✅ View Customer’s Schedule
@app.route('/scheduling/<customer_id>', methods=['GET'])
def view_appointment(customer_id):
    if customer_id in schedules:
        return jsonify({"appointment": schedules[customer_id]}), 200
    return jsonify({"error": "No appointment found"}), 404

# ✅ Run Flask Server for Local Testing or Render Deployment
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10002, debug=True)  # Default for local testing; Render overrides