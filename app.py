from collections import defaultdict
from flask import Flask, request, jsonify
from collections import defaultdict
import io
from flask_cors import CORS
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
import uuid
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime, timedelta

from dotenv import load_dotenv
import os

load_dotenv()



app = Flask(__name__)

# MySQL Configuration
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')
app.config['MYSQL_PORT'] = int(os.getenv('MYSQL_PORT'))  # Cast port to integer
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')

mysql = MySQL(app)

# Google Drive API credentials file
CREDENTIALS_FILE = './etc/secrets/auth.json'
CORS(app)
# JWT Configuration
jwt = JWTManager(app)

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

# Add product
SCOPES = ['https://www.googleapis.com/auth/drive.file']
credentials = service_account.Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
service = build('drive', 'v3', credentials=credentials)

# Function to upload file to Google Drive
def upload_image_to_drive(file):
    try:
        # Secure the filename
        filename = secure_filename(file.filename)

        # Create an in-memory file-like object from the uploaded file
        file_stream = io.BytesIO(file.read())  # Read the file content into memory

        # Prepare the media upload for Google Drive
        media = MediaIoBaseUpload(file_stream, mimetype=file.mimetype)
        file_metadata = {'name': filename, 'parents': ['1mAUUgrtfUpsTWOaBaM8g0gZQAaURppG9']}
        
        # Upload the file to Google Drive
        uploaded_file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()

        # Change permissions to make it publicly accessible
        permission_body = {
            'role': 'reader',
            'type': 'anyone'
        }
        service.permissions().create(
            fileId=uploaded_file.get('id'),
            body=permission_body,
        ).execute()

        # Get the file's Google Drive ID and construct the URL
        file_id = uploaded_file.get('id')
        direct_image_url = f"https://drive.google.com/uc?id={file_id}"

        return direct_image_url, file_id  # Return both the URL and file ID

    except Exception as e:
        print(f"Error uploading image: {e}")
        return None, None



created_at = datetime.now()
# Add product (with image upload to Google Drive)
@app.route('/api/products/new', methods=['POST'])
def add_product():
    try:
        # Check if the request contains the image file
        if 'image' not in request.files:
            return jsonify({'error': 'No image provided'}), 400
        
        image = request.files['image']

        # Upload the image to Google Drive
        image_url, file_id = upload_image_to_drive(image)
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


def delete_image_from_drive(file_id):
    try:
        service.files().delete(fileId=file_id).execute()
        return True
    except Exception as e:
        print(f"Error deleting file: {e}")
        return False

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
        if file_id and not delete_image_from_drive(file_id):
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
