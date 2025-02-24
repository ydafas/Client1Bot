from flask import Flask, request, jsonify
import os

app = Flask(__name__)

# 🔹 Inventory Data (In-memory; use a DB in production)
inventory = {
    "chatbot_basic": {"name": "Basic Chatbot", "quantity": 10, "price": 199},
    "chatbot_pro": {"name": "Pro Chatbot", "quantity": 5, "price": 499},
    "chatbot_enterprise": {"name": "Enterprise Chatbot", "quantity": 3, "price": 999}
}

# ✅ Get Inventory Status
@app.route('/inventory/<product_id>', methods=['GET'])
def get_inventory(product_id):
    if product_id in inventory:
        return jsonify({
            "product": inventory[product_id]["name"],
            "quantity": inventory[product_id]["quantity"],
            "price": inventory[product_id]["price"],
            "available": inventory[product_id]["quantity"] > 0
        }), 200
    return jsonify({"error": "Product not found"}), 404

# ✅ Update Inventory (e.g., after a sale)
@app.route('/inventory/<product_id>', methods=['POST'])
def update_inventory(product_id):
    if product_id not in inventory:
        return jsonify({"error": "Product not found"}), 404

    data = request.json
    quantity_change = data.get('quantity_change', 0)  # Positive for adding, negative for removing

    if inventory[product_id]["quantity"] + quantity_change < 0:
        return jsonify({"error": "Insufficient stock"}), 400

    inventory[product_id]["quantity"] += quantity_change
    return jsonify({
        "product": inventory[product_id]["name"],
        "new_quantity": inventory[product_id]["quantity"],
        "message": "Inventory updated"
    }), 200

# ✅ Add New Product (Admin Use)
@app.route('/inventory', methods=['POST'])
def add_product():
    data = request.json
    product_id = data.get('product_id')
    name = data.get('name')
    quantity = data.get('quantity', 0)
    price = data.get('price', 0)

    if not all([product_id, name, quantity, price]):
        return jsonify({"error": "Missing required fields"}), 400

    inventory[product_id] = {"name": name, "quantity": quantity, "price": price}
    return jsonify({"message": "Product added", "product": inventory[product_id]}), 201

# ✅ Run Flask Server for Local Testing or Render Deployment
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10001, debug=True)  # Default for local testing; Render overrides