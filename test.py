from flask import Flask
from flask_mysqldb import MySQL
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Flask app setup
app = Flask(__name__)

# MySQL Configuration
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')
app.config['MYSQL_PORT'] = int(os.getenv('MYSQL_PORT'))  # Ensure it's an integer

# Initialize MySQL
mysql = MySQL(app)

# Table creation function
def create_table():
    try:
        # Open a cursor to perform database operations
        cursor = mysql.connection.cursor()
        cursor.execute("""
            Delete from productlist

        """)
        mysql.connection.commit()  # Commit the transaction
        cursor.close()  # Close the cursor
        print("Table `productlist` created successfully!")
    except Exception as e:
        print(f"Error creating table: {e}")

# Route for testing server
@app.route('/')
def home():
    return "Flask MySQL Integration is working!"

if __name__ == '__main__':
    with app.app_context():
        create_table()  # Ensure the table is created before the app runs
    app.run(debug=True)
