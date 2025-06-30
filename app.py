from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import pytesseract
from PIL import Image, ImageEnhance # Added ImageEnhance for preprocessing
from datetime import datetime
import json
import tempfile
import shutil
import re
import boto3
import traceback # Import traceback for detailed error logging

# Toggle for AWS support
USE_AWS = False

# Corrected: Use double underscores for __name__
app = Flask(__name__)

# START OF UPDATED CORS CONFIGURATION
# Ensure CORS is configured correctly for all origins that might access your Flask backend.
# This includes:
# - Streamlit's default local host:port (http://127.0.0.1:8501)
# - The local web server serving your index.html (e.g., http://127.0.0.1:8000 or http://localhost:8000)
# For development, you can use "*" for all origins, but it's less secure for production.
# Using a list of specific origins is better.
CORS(app, resources={r"/upload": {"origins": [
    "http://127.0.0.1:8501", # Streamlit's default local address
    "http://localhost:8501", # Streamlit's alternative local address
    "http://127.0.0.1:8000", # Common local web server address for index.html
    "http://localhost:8000",  # Common local web server alternative address
    "http://127.0.0.1:5500", # Added for VS Code Live Server or similar
    "http://localhost:5500"   # Added for VS Code Live Server or similar
]}})
# END OF UPDATED CORS CONFIGURATION

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- IMPORTANT: Tesseract Path Configuration ---
# You MUST set this to the correct path where Tesseract-OCR is installed on your system.
# For Windows, it's typically 'C:\Program Files\Tesseract-OCR\tesseract.exe'
# For Linux/macOS, it's often just 'tesseract' if it's in your PATH,
# or a specific path like '/usr/local/bin/tesseract'
# This block attempts to set the path and verify Tesseract's presence.
try:
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    # For Linux/macOS, you might use:
    # pytesseract.pytesseract.tesseract_cmd = 'tesseract'
    
    # Try to get Tesseract version to confirm it's accessible and working
    pytesseract.get_tesseract_version()
    print("Tesseract-OCR is configured and found.")
except Exception as e:
    print(f"Error: Tesseract is not properly installed or configured. Please check the path and installation. Error: {e}")
    # In a production environment, you might want to exit or disable OCR functionality
    # For this app, we'll raise an error to ensure Tesseract is set up correctly,
    # as OCR is a core function.
    raise RuntimeError("Tesseract-OCR is required. Please install it and set the correct path in app.py.")


if USE_AWS:
    # Placeholder for AWS DynamoDB setup
    # Make sure your AWS credentials are configured (e.g., via ~/.aws/credentials or environment variables)
    try:
        dynamodb = boto3.resource('dynamodb', region_name='ap-south-1')
        # Replace 'snapbudget_receipts' with your actual DynamoDB table name if different
        table = dynamodb.Table('snapbudget_receipts')
        print(f"Connected to DynamoDB table: {table.name}")
    except Exception as e:
        print(f"Error connecting to DynamoDB: {e}")
        dynamodb = None
        table = None # Ensure table is None if connection fails
else:
    dynamodb = None
    table = None

def upload_to_s3_simulated(file_path, filename):
    """
    Simulates S3 upload by returning a dynamic local URL for the uploaded file.
    Uses request.host_url to create a robust URL that adapts to Flask's actual host/port.
    In a real S3 integration, this would upload to S3 and return the S3 public URL.
    """
    # request.host_url includes scheme and netloc (e.g., http://127.0.0.1:5000/)
    return f"{request.host_url.rstrip('/')}/uploads/{filename}"

def categorize(name):
    """Categorizes an item based on its name."""
    name = name.lower()
    if any(k in name for k in ['milk', 'rice', 'dal', 'bread', 'oil', 'eggs', 'vegetable', 'atta', 'flour', 'sugar', 'salt']):
        return 'Essentials'
    if any(k in name for k in ['chocolate', 'biscuit', 'lays', 'snack', 'chips', 'cold drink', 'soda', 'candy', 'cookies']):
        return 'Snacks'
    if any(k in name for k in ['shirt', 'jeans', 'shoe', 'sandal', 'dress', 'trousers', 'jacket', 'tshirt', 'socks']):
        return 'Clothing'
    if any(k in name for k in ['usb', 'charger', 'headphone', 'phone', 'mouse', 'keyboard', 'laptop', 'tablet', 'speaker']):
        return 'Electronics'
    if any(k in name for k in ['medicine', 'pharmacy', 'pill', 'bandage']):
        return 'Health'
    if any(k in name for k in ['restaurant', 'cafe', 'food', 'dinner', 'lunch', 'breakfast', 'pizza', 'burger']):
        return 'Dining Out'
    if any(k in name for k in ['fuel', 'petrol', 'diesel', 'gas', 'transport']):
        return 'Transport'
    if any(k in name for k in ['electricity', 'water', 'internet', 'rent']):
        return 'Utilities'
    return 'Other'

@app.route('/ping')
def ping():
    """Simple endpoint to check if the backend is running."""
    return "pong"

@app.route('/api/test', methods=['GET'])
def test_connection():
    """Another test endpoint."""
    return jsonify({'message': 'Backend connected successfully!'})

@app.route('/uploads/<path:filename>')
def serve_uploaded_file(filename):
    """Serves uploaded files from the 'uploads' directory."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

def save_result(result):
    """
    Saves the processed receipt result.
    If USE_AWS is True, attempts to save to DynamoDB.
    Otherwise, appends to a local 'results.json' file.
    """
    if USE_AWS and table:
        try:
            # DynamoDB put_item expects direct Python dicts, not JSON strings.
            # The 'result' dict passed here already has 'items' and 'category_breakdown' as dicts/lists.
            table.put_item(Item=result)
            print("Result saved to DynamoDB.")
        except Exception as e:
            print(f"Error saving to DynamoDB: {e}")
            traceback.print_exc() # Print full traceback for DynamoDB error
            # Fallback to local save if DynamoDB fails or not configured
            with open("results.json", "a") as f:
                f.write(json.dumps(result) + "\n")
            print("Result saved locally due to DynamoDB error or AWS not in use.")
    else:
        # Append to a local JSON file (each result on a new line for easier parsing)
        with open("results.json", "a") as f:
            f.write(json.dumps(result) + "\n")
        print("Result saved locally.")


@app.route('/upload', methods=['POST'])
def upload_image():
    """
    Handles image uploads, performs OCR, parses data,
    generates a savings tip, and returns the analysis.
    """
    print("Received upload request.")
    if 'file' not in request.files:
        print("No file part in request.")
        return jsonify({'error': 'No file part in request'}), 400

    file = request.files['file']
    if file.filename == '':
        print("No file selected.")
        return jsonify({'error': 'No file selected'}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    try:
        file.save(filepath)
        print(f"File saved to: {filepath}")
    except Exception as e:
        print(f"Error saving file: {e}")
        traceback.print_exc() # Print full traceback
        return jsonify({'error': f"Failed to save file: {str(e)}"}), 500

    image_url = upload_to_s3_simulated(filepath, filename)
    print(f"Image URL: {image_url}")

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = os.path.join(temp_dir, 'temp_img.png')
            shutil.copy(filepath, temp_path)
            
            # --- Image Preprocessing for improved OCR accuracy ---
            # Convert to grayscale
            img = Image.open(temp_path).convert('L')
            # Increase contrast significantly. Adjust factor as needed (e.g., 1.5 to 3.0)
            img = ImageEnhance.Contrast(img).enhance(2.0)
            # You might also add:
            # img = ImageEnhance.Sharpness(img).enhance(1.5) # Sharpen image
            # img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS) # Upscale (sometimes helps)

            print("Image opened and preprocessed for OCR.")
            # Perform OCR (blocking operation)
            # --psm 6: Assume a single uniform block of text. Often good for receipts.
            extracted_text = pytesseract.image_to_string(img, config='--psm 6')
            print(f"Extracted Text:\n{extracted_text}")

        lines = extracted_text.strip().split('\n')
        items = []
        total = 0.0 # Initialize total as a float
        category_totals = {}
        # Expanded exclude words for better filtering. Added common receipt specific words.
        exclude_words = ['gst', 'total', 'invoice', 'bill', 'phone', 'contact', 'care', 'amount', 'tax', 'subtotal', 'discount', 'change', 'cash', 'card', 'visa', 'mastercard', 'qty', 'quantity', 'rate', 'price', 'item', 'description', 'unit']

        for line in lines:
            line = line.strip()
            if not line or any(word in line.lower() for word in exclude_words):
                continue
            
            # Updated regex to be more robust for prices (allowing commas and optional decimals)
            # It looks for a sequence of characters (item name) followed by optional separators
            # and then a number with optional commas and up to two decimal places.
            # Example: "Product A 123.45" or "Item 1, 99.00" or "My Item 50"
            match = re.match(r'(.+?)\s*[\.:₹\s]?[,\s]*([\d,]+(?:\.\d{1,2})?)$', line)
            if match:
                name = match.group(1).strip()
                price_str = match.group(2).replace(',', '') # Remove commas before conversion
                try:
                    price = float(price_str) # Convert to float for accurate pricing
                    if 0.01 <= price <= 100000.0: # Filter out unrealistic prices, allow small values (e.g., 0.50)
                        items.append({'name': name, 'price': price})
                        total += price
                        cat = categorize(name)
                        category_totals[cat] = category_totals.get(cat, 0.0) + price # Use 0.0 for float sums
                except ValueError: # Catch errors if price conversion fails
                    print(f"Could not parse price from line: '{line}' - Price string: '{price_str}'")
                    continue
            else:
                # Fallback for lines that might contain a total or sum
                total_match = re.search(r'(?:total|sum|amt|balance)\s*[:₹]?\s*([\d,]+(?:\.\d{1,2})?)$', line.lower())
                if total_match:
                    try:
                        # If a total line is found, use it as the definitive total.
                        # This assumes the last such match is the final total.
                        # Be careful if multiple totals might appear.
                        extracted_total = float(total_match.group(1).replace(',', ''))
                        if extracted_total > 0 and abs(extracted_total - total) < 100: # Check if close to sum of items
                            total = extracted_total
                            print(f"Overriding total with detected final total: {total}")
                        elif total == 0 and extracted_total > 0: # If no items were parsed but a total is found
                             total = extracted_total
                             print(f"Setting total from detected final total: {total} (no items parsed)")
                    except ValueError:
                        print(f"Could not parse total from total line: '{line}'")
                print(f"No item/price match for line: '{line}'")


        essentials = [i for i in items if categorize(i['name']) == 'Essentials']
        snacks = [i for i in items if categorize(i['name']) == 'Snacks']
        electronics_total = category_totals.get('Electronics', 0.0) # Use 0.0 for float default

        # Generate savings tip based on parsed data, now with float formatting
        # Specific tips ordered by priority
        tip = "👏 Balanced receipt—track these patterns over time to stay on target." # Default tip

        if total == 0:
            tip = "🤔 Could not extract any meaningful data. Try a clearer image or manually enter details!"
        elif electronics_total > 1500:
            tip = "⚡ Electronics are expensive—compare prices or delay big upgrades."
        elif len(snacks) >= 3:
            tip = "🍫 Lots of snacks—consider buying in bulk to save long-term."
        elif not essentials and total > 0: # Only suggest if there's actual spend but no essentials
            tip = "📌 No essentials detected—are you skipping household basics?"
        elif 0 < total < 500: # Small total
            tip = "✅ Excellent budgeting—keep up the good discipline!"
        elif total > 2500:
            tip = f"📉 High spend alert: ₹{total:.2f}. Try to set weekly limits."

        result = {
            'username': 'madhu', # Hardcoded username for now. In a real app, integrate Firebase user ID.
            'timestamp': datetime.now().isoformat(),
            'items': items, # Sent as a list of dicts directly
            'total': total,
            'category_breakdown': category_totals, # Sent as a dict directly
            'savings_tip': tip,
            'image_url': image_url
        }

        save_result(result)
        print("Processing successful, sending response.")
        return jsonify(result)

    except pytesseract.TesseractNotFoundError:
        print("Tesseract not found. This error should ideally be caught at app startup.")
        traceback.print_exc() # Print full traceback
        return jsonify({'error': "Tesseract-OCR is not installed or not found. Please check the backend configuration."}), 500
    except Exception as e:
        print(f"An error occurred during image processing: {e}")
        # Log traceback for better debugging server-side
        traceback.print_exc()
        return jsonify({'error': f"Image processing failed: {str(e)}. Check backend logs for details."}), 500

# Corrected: Use double underscores for __name__ and __main__
if __name__ == '__main__':
    # Flask will run on http://0.0.0.0:5000 (accessible from host and other containers)
    # debug=True allows automatic reloading on code changes and provides a debugger.
    app.run(host='0.0.0.0', port=5000, debug=True)