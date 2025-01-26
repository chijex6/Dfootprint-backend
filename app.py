from flask_cors import CORS
from flask_mysqldb import MySQL
from werkzeug.security import check_password_hash
from flask_jwt_extended import JWTManager, create_access_token, jwt_required
from cloudinary.uploader import upload as cloudinary_upload
from cloudinary.exceptions import Error as CloudinaryError
import uuid
from reciptGen import create_invoice_in_memory
from datetime import datetime
from cloudinary.api import delete_resources
from datetime import datetime, timedelta
from datetime import datetime
from dotenv import load_dotenv
import platform
import os
from flask import Flask, request, jsonify, send_file

load_dotenv()



app = Flask(__name__)

# MySQL Configuration
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')
app.config['MYSQL_PORT'] = int(os.getenv('MYSQL_PORT'))  # Cast port to integer
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
cloudinary_config = {
    "api_key": os.getenv("CLOUDINARY_API_KEY"),
    "api_secret": os.getenv("CLOUDINARY_API_SECRET"),
    "cloud_name": os.getenv("CLOUDINARY_CLOUD_NAME"),
}

# Initialize Backblaze B2 bucket (pseudo-code)


application_key_id = os.getenv("B2_KEY_ID")
application_key = os.getenv("B2_APPLICATION_KEY")


mysql = MySQL(app)

# Google Drive API credentials file
CREDENTIALS_FILE = '/etc/secrets/auth.json'
CORS(app)
# JWT Configuration
jwt = JWTManager(app)

import time

start_time = time.time()

@app.route('/health', methods=['GET'])
def health_check():
    uptime = time.time() - start_time
    return jsonify({
        "status": "success",
        "message": "Backend is live and running!",
        "system": {
            "os": platform.system(),
            "os_version": platform.version(),
            "architecture": platform.architecture()[0],
            "python_version": platform.python_version()
        },
        "uptime_seconds": round(uptime, 2)
    }), 200


@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data['email']
    password = data['password']

    cursor = mysql.connection.cursor()
    cursor.execute('SELECT * FROM admins WHERE email = %s', (username,))
    admin = cursor.fetchone()
    cursor.close()

    if admin and check_password_hash(admin[2], password):
    # Set the expiration time to 1 day
        expires = timedelta(days=1)  # 1 day expiration

        # Create the access token with the specified expiration
        token = create_access_token(identity=admin[1], expires_delta=expires)
        return jsonify({'token': token}), 200

def delete_from_cloudinary(public_id):
    try:
        # Deletes the resource by its public_id
        response = delete_resources(public_id)
        print(f"Cloudinary Delete Response: {response}")
        return response.get("deleted", {}).get(public_id) == "deleted"
    except CloudinaryError as e:
        print(f"Error deleting from Cloudinary: {e}")
        return False


def upload_image_to_storage(image_file):
    """
    Upload an image to Cloudinary or Backblaze B2 based on the configured storage type.

    Args:
        image_file: The uploaded file from the request.

    Returns:
        tuple: (image_url, file_id) if successful, otherwise (None, None).
    """
  # Default to Cloudinary

    try:

            response = cloudinary_upload(image_file, folder="dfootprint")
            image_url = response.get("secure_url")
            file_id = response.get("public_id")
            print("cloudinary", image_url, file_id)
            return image_url, file_id

    except (CloudinaryError, Exception) as e:
        print(f"Error uploading image to Cloundinary: {e}")
        return None, None

@app.route("/api/orders/invoice", methods=["POST"])
def generate_invoice():
    try:
        # Parse the order payload from the request
        order = request.get_json()

        # Format the data for the invoice generator
        invoice_data = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'id': str(order['id']),  # Ensure the ID is a string
            'name': order['name'],
            'email': order['email'],
            'number': str(order['number']),  # Convert number to string
            'Delivery Company': order['Delivery Company'],
            'State': order['State'],
            'Location': order['Location'],
            'Pickup Address': order.get('Pickup Address', "N/A"),  # Handle missing pickup address
            'items': [
                {
                    'name': item['name'],
                    'size': str(item['size']),  # Convert size to string
                    'unit_price': f"{float(item['unit_price']):.2f}",  # Convert string to float, then format
                    'total': f"{float(item['total']):.2f}"  # Convert total to float, then format
                }
                for item in order['items']
            ],
            'subtotal': f"{float(order['subtotal']):.2f}",  # Convert subtotal to float, then format
            'tax': f"{float(order['tax']):.2f}",  # Convert tax to float, then format
            'total': f"{float(order['total']):.2f}"  # Convert total to float, then format
        }

        order_id = str(order['id'])
        # Format your data here if needed
        pdf_buffer = create_invoice_in_memory(invoice_data)
        response = send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=f"Invoice_{order_id}.pdf",
            mimetype='application/pdf'
        )
        response.headers['Access-Control-Expose-Headers'] = 'Content-Disposition'
        response.headers['Content-Disposition'] = f'attachment; filename="Invoice_{order_id}.pdf"'
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 500



# Add product (with image upload to Google Drive)
@app.route('/api/products/new', methods=['POST'])
def add_product():
    try:
        # Check if the request contains the image file
        if 'image' not in request.files:
            return jsonify({'error': 'No image provided'}), 400
        
        image = request.files['image']

        # Upload the image to the configured storage
        image_url, file_id = upload_image_to_storage(image)
        if not image_url or not file_id:
            return jsonify({'error': 'Failed to upload image'}), 500
        
        # Extract other form fields
        name = request.form.get('name')
        price = request.form.get('price')
        description = request.form.get('description')
        category = request.form.get('category')
        size = request.form.get('size')
        disabledSizes = request.form.get('disabledSizes')

        # Validate form fields
        if not name or not price or not category or not size:
            return jsonify({'error': 'Missing required fields'}), 400

        # Insert product into the database
        cursor = mysql.connection.cursor()
        cursor.execute('''INSERT INTO productlist (name, price, category, image, size, description, disabledSizes, file_id)
                          VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''', 
                       (name, price, category, image_url, size, description, disabledSizes, file_id))
        mysql.connection.commit()
        cursor.close()

        return jsonify({'message': 'Product added successfully'}), 201

    except Exception as e:
        print(f"Error adding product: {e}")
        return jsonify({'error': 'An error occurred while adding the product'}), 500
    
@app.route('/api/products', methods=['GET'])
def get_products():
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT id, name, price, image_url FROM products")
        rows = cursor.fetchall()
        cursor.close()

        # Format the response as a list of dictionaries
        products = [{'id': row[0], 'name': row[1], 'price': row[2], 'image_url': row[3]} for row in rows]

        return jsonify(products), 200

    except Exception as e:
        print(f"Error fetching products: {e}")
        return jsonify({'error': 'Failed to fetch products'}), 500

# Mock database for demonstration
orders_db = []

@app.route('/api/orders', methods=['GET'])
def get_order():
    try:
        order_id = request.args.get('order_id')
        if not order_id or len(order_id) != 12 or not order_id.startswith("ORD-"):
            return jsonify({"error": "Invalid Order ID format."}), 400
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT product_name, product_size, product_quantity FROM track WHERE order_id = %s", (order_id,))
        data = cursor.fetchall()
        products = [{'name': row[0], 'size': row[1], 'quantity': row[2]} for row in data]
        cursor.close()
        return jsonify(products), 200
    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'error': 'Failed to fetch orders'}), 500

@app.route('/api/orders/metadata', methods=['GET'])
def get_order_metadata():
    try:
        # Get the order_id from the query parameters
        order_id = request.args.get('order_id')

        # Validate the order_id format
        if not order_id or len(order_id) != 12 or not order_id.startswith("ORD-"):
            return jsonify({"error": "Invalid Order ID format."}), 400

        # Check if the order exists in the orders table
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT status, date_created, estimated_time FROM orders WHERE order_id = %s", (order_id,))
        order_metadata = cursor.fetchone()

        if not order_metadata:
            print("Order ID not found.")
            return jsonify({"error": "Order ID not found."}), 404

        # Extract order metadata
        status, date_created, estimated_time = order_metadata

        # Query the tracking details for the given order_id
        cursor.execute('''
            SELECT 
                customer_name, customer_email, customer_contact, 
                product_name, product_quantity, total_amount
            FROM track 
            WHERE order_id = %s
        ''', (order_id,))
        tracking_data = cursor.fetchall()

        if not tracking_data:
            return jsonify({"error": "No tracking data found for this Order ID."}), 404

        # Build the response
        response = {
            "order_id": order_id,
            "status": status,
            "date_created": date_created.strftime('%Y-%m-%d %H:%M:%S'),
            "estimated_time": estimated_time.strftime('%Y-%m-%d %H:%M:%S') if estimated_time else None,
            "tracking_data": [
                {
                    "name": row[0],
                    "email": row[1],
                    "contact": row[2],
                    "product": row[3],
                    "quantity": row[4],
                    "total": row[5]
                }
                for row in tracking_data
            ]
        }

        cursor.close()
        return jsonify(response), 200

    except Exception as e:
        print(f"Error fetching order metadata: {e}")
        return jsonify({"error": "An internal server error occurred."}), 500

@app.route('/api/products/manage', methods=['GET', 'POST'])
def manage_products():
    try:
        if request.method == 'GET':
            # Fetch orders and restructure them to match frontend expectations
            cursor = mysql.connection.cursor()
            cursor.execute('''
              SELECT 
                o.order_id AS product_id, 
                o.status, 
                o.batch,
                t.customer_name, 
                t.customer_contact, 
                t.product_name,
                o.date_created, 
                t.customer_email
            FROM orders o
            LEFT JOIN (
                SELECT 
                    order_id, 
                    MAX(customer_name) AS customer_name, 
                    MAX(customer_contact) AS customer_contact, 
                    MAX(product_name) AS product_name,
                    MAX(customer_email) AS customer_email
                FROM track
                GROUP BY order_id
            ) t ON o.order_id = t.order_id
            ORDER BY o.batch IS NULL DESC, o.batch, o.date_created DESC;
            ''')
            data = cursor.fetchall()

            # Flatten and structure data
            products = [
                {
                    "product_id": row[0],
                    "status": row[1],
                    "batch": row[2],
                    "date_created": row[6].strftime('%Y-%m-%d %H:%M:%S'),
                    "tracking_data": {
                        "customer_name": row[3],
                        "contact": row[4],
                        "items": [row[5]],
                        "email": row[7]
                    },
                }
                for row in data
            ]

            cursor.close()
            return jsonify(products), 200

        elif request.method == 'POST':
            # Handle status updates for products
            data = request.json
            product_ids = data.get("product_ids", [])
            new_status = data.get("status")

            if not product_ids or not new_status:
                return jsonify({"error": "Product IDs and status are required."}), 400

            cursor = mysql.connection.cursor()
            cursor.execute('''
                UPDATE orders 
                SET status = %s 
                WHERE order_id IN (%s)
            ''' % (','.join(['%s'] * len(product_ids))), (new_status, *product_ids))

            mysql.connection.commit()
            cursor.close()
            return jsonify({"message": "Products updated successfully."}), 200

    except Exception as e:
        print(f"Error managing products: {e}")
        return jsonify({"error": str(e)}), 500



# Route: Create a new batch
@app.route('/api/products/create_batch', methods=['POST'])
def create_batch():
    try:
        batch_name = request.json.get("batch_name")
        product_ids = request.json.get("product_ids", [])

        if not batch_name or not product_ids:
            return jsonify({"message": "Batch name and product IDs are required"}), 400

        cursor = mysql.connection.cursor()

        # Link products to the batch in batch_products table
        for product_id in product_ids:
            cursor.execute(
                """Update orders 
                SET batch = %s
                WHERE order_id = %s """,
                (batch_name, product_id),
            )

        mysql.connection.commit()
        cursor.close()

        return jsonify({"message": "Batch created successfully"}), 201
    except Exception as e:
        print(f"Error creating batch: {e}")
        return jsonify({"message": "Failed to create batch"}), 500


# Route: Update batch status
@app.route('/api/products/update_batch_status', methods=['POST'])
def update_batch_status():
    try:
        batch_name = request.json.get("batch_name")
        status = request.json.get("status")

        if not batch_name or not status:
            return jsonify({"message": "Batch name and status are required"}), 400

        cursor = mysql.connection.cursor()
        if batch_name == "New Batch":
            cursor.execute(
                "UPDATE orders SET status = %s WHERE batch IS NULL", (status,)
            )
        else:
            cursor.execute(
                "UPDATE orders SET status = %s WHERE batch = %s", (status, batch_name)
            )

        mysql.connection.commit()
        cursor.close()


        return jsonify({"message": "Batch status updated successfully"}), 200
    except Exception as e:
        print(f"Error updating batch status: {e}")
        return jsonify({"message": "Failed to update batch status"}), 500


# Route: Update product status
@app.route('/api/products/update_status', methods=['POST'])
def update_product_status():
    try:
        product_id = request.json.get("product_id")
        status = request.json.get("status")

        if not product_id or not status:
            return jsonify({"message": "Product ID and status are required"}), 400

        cursor = mysql.connection.cursor()

        # Update the product status
        cursor.execute(
            "UPDATE orders SET status = %s WHERE order_id = %s", (status, product_id)
        )

        mysql.connection.commit()
        cursor.close()

        return jsonify({"message": "Product status updated successfully"}), 200
    except Exception as e:
        print(f"Error updating product status: {e}")
        return jsonify({"message": "Failed to update product status"}), 500

@app.route('/api/orders/details', methods=['GET'])
def get_order_details():
    """
    Fetch detailed order metadata, including grouped tracking information and customer details.
    """
    try:
        cursor = mysql.connection.cursor()

        # Query to fetch grouped order details
        cursor.execute('''
            SELECT 
                o.order_id, 
                o.status AS order_status,
                o.date_created AS order_date, 
                t.product_name, 
                t.product_size, 
                t.total_amount, 
                t.product_quantity, 
                t.status AS product_status, 
                t.customer_name, 
                t.customer_email, 
                t.customer_contact
            FROM 
                orders o
            LEFT JOIN 
                track t ON o.order_id = t.order_id
            ORDER BY 
                o.date_created DESC
        ''')

        # Process query results into a grouped structure
        rows = cursor.fetchall()
        cursor.close()

        if not rows:
            return jsonify({"message": "No orders found"}), 404

        grouped_data = {}
        for row in rows:
            order_id = row['order_id']
            if order_id not in grouped_data:
                grouped_data[order_id] = {
                    "order_id": order_id,
                    "status": row['order_status'],
                    "date_created": row['order_date'],
                    "customer_name": row['customer_name'],
                    "customer_email": row['customer_email'],
                    "customer_contact": row['customer_contact'],
                    "items": []
                }

            grouped_data[order_id]["items"].append({
                "product_name": row['product_name'],
                "product_size": row['product_size'],
                "total_amount": row['total_amount'],
                "product_quantity": row['product_quantity'],
                "product_status": row['product_status']
            })

        # Convert grouped_data to a list of orders
        orders = list(grouped_data.values())

        return jsonify({"orders": orders}), 200

    except Exception as e:
        print(f"Error fetching order details: {e}")
        return jsonify({'error': 'An error occurred while fetching order details'}), 500


# Update product
@app.route('/api/products/<product_id>', methods=['PUT'])
def update_product(product_id):
    data = request.json  # Parse JSON data
    name = data.get('name')
    price = data.get('price')
    description = data.get('description')
    category = data.get('category')
    size = data.get('size')
    disabledSizes = data.get('disabledSizes')

    # Debugging logs to verify incoming data
    print("Received data:", data)

    cursor = mysql.connection.cursor()
    cursor.execute('''UPDATE productlist
                      SET name = %s, price = %s, description = %s, category = %s, size = %s, disabledSizes = %s
                      WHERE id = %s''',
                   (name, price, description, category, size, disabledSizes, product_id))
    mysql.connection.commit()
    cursor.close()

    return jsonify({'message': 'Product updated successfully'}), 200




@app.route('/api/products/delete/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    try:
        # Retrieve the product from the database
        print('ready')
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT file_id FROM productlist WHERE id = %s", (product_id,))
        result = cursor.fetchone()
        print("done", result)
        if not result:
            return jsonify({'error': 'Product not found'}), 404
        
        file_id = result[0]
        print(file_id)

        # Delete the file from Google Drive
        if file_id and not delete_from_cloudinary(file_id):
            return jsonify({'error': 'Failed to delete image from Google Drive'}), 500

        # Delete the product from the database
        print("running")
        cursor.execute("DELETE FROM productlist WHERE id = %s", (product_id,))
        mysql.connection.commit()
        cursor.close()
        print("done")

        return jsonify({'message': 'Product deleted successfully'}), 200

    except Exception as e:
        print(f"Error deleting product: {e}")
        return jsonify({'error': 'An error occurred while deleting the product'}), 500

# Update order status
@app.route('/update-order/<order_id>', methods=['PUT'])
@jwt_required()
def update_order(order_id):
    try:
        data = request.json
        status = data['status']

        cursor = mysql.connection.cursor()
        cursor.execute('''UPDATE orders 
                        SET status = %s, updated_at = %s 
                        WHERE id = %s''', 
                    (status, datetime.utcnow(), order_id))
        mysql.connection.commit()
        cursor.close()

        return jsonify({'message': 'Order updated successfully'}), 200
    except Exception as e:
        print(e)

@app.route('/api/product-list', methods=['GET'])
def get_product():
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT id, name, price, image, description, category, size, disabledSizes FROM productlist')
    products = cursor.fetchall()
    cursor.close()

    # Convert the result to a list of dictionaries
    products_list = [{'id': row[0], 'name': row[1], 'price': row[2], 'image': row[3], 'description': row[4], 'category': row[5], 'size': row[6], 'disabledSizes': row[7],} for row in products]

    return jsonify(products_list), 200

# Group orders by status
@app.route('/orders', methods=['GET'])
def get_orders():
    status = request.args.get('status')

    cursor = mysql.connection.cursor()
    cursor.execute('SELECT * FROM orders WHERE status = %s', (status,))
    orders = cursor.fetchall()
    cursor.close()

    return jsonify(orders), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
