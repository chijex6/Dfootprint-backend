from flask_cors import CORS
from flask_mysqldb import MySQL
from werkzeug.security import check_password_hash
from flask_jwt_extended import JWTManager, create_access_token, jwt_required
from cloudinary.uploader import upload as cloudinary_upload
from cloudinary.exceptions import Error as CloudinaryError
from cloudinary.api import delete_resources
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
from flask import Flask, request, jsonify

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

@app.route('/', methods=['GET'])
def home():
    message = f"Welcome to the D'FOOTPRINTBackend API! This is for testing our API."
    return jsonify({'message': message}), 200

@app.route('/health', methods=['GET'])
def health_check():
    """
    A health check endpoint that returns the status of the service.
    """
    current_time = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    response = {
        "status": "healthy",
        "message": "Service is running smoothly",
        "timestamp": current_time
    }
    return jsonify(response), 200



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


# Add product (with image upload to Google Drive)
@app.route('/api/products/new', methods=['POST'])
def add_product():
    try:
        # Check if the request contains the image file
        if 'image' not in request.files:
            print("Failed no image")
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
