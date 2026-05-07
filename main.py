
import streamlit as st
# from google import genai
import google.generativeai as genai
import json
import os
import time
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

# Load environment variables (for local development)
load_dotenv()

# --- Configuration ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found. Please set it in .env or Streamlit secrets.")
    st.stop()

# Configure Gemini API
genai.configure(api_key=GEMINI_API_KEY)
# client = genai.Client(api_key = st.secrets["GEMINI_API_KEY"])
# model = genai.GenerativeModel('gemini-pro-vision')
model = genai.GenerativeModel('gemini-2.5-flash')

# Google Sheets configuration
SERVICE_ACCOUNT_FILE = 'service_account.json' # Make sure this file is in your project root
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
# SPREADSHEET_NAME = 'Receipts Data' # Change this to your Google Sheet name
SPREADSHEET_NAME = 'receipts-ocr' # Change this to your Google Sheet name

# --- CSS Styling and Animations ---
st.markdown(
    """
    <style>
    body {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .main-header {
        color: #4CAF50;
        text-align: center;
        font-size: 2.5em;
        margin-bottom: 20px;
    }
    .stButton>button {
        background-color: #4CAF50;
        color: white;
        padding: 10px 20px;
        border: none;
        border-radius: 5px;
        cursor: pointer;
        font-size: 1em;
        transition: background-color 0.3s ease;
    }
    .stButton>button:hover {
        background-color: #45a049;
    }
    .stAlert {
        border-radius: 8px;
    }

    /* Scanning Bar Animation */
    .scanner-container {
        position: relative;
        width: 100%;
        height: 10px; /* Height of the scanning bar */
        background-color: #eee;
        border-radius: 5px;
        overflow: hidden; /* Hide the bar when it's outside */
        margin-top: 20px;
        margin-bottom: 20px;
        box-shadow: inset 0 0 5px rgba(0,0,0,0.2);
    }
    .scanner-bar {
        position: absolute;
        top: 0;
        left: -100%; /* Start off-screen to the left */
        width: 100%;
        height: 100%;
        background: linear-gradient(to right, transparent, rgba(76, 175, 80, 0.5), transparent);
        animation: scan 2s infinite linear;
        animation-fill-mode: forwards; /* Keep the last frame state */
    }
    @keyframes scan {
        0% { transform: translateX(0%); }
        100% { transform: translateX(200%); } /* Move across the container + off-screen */
    }

    /* Success Toast Animation */
    .success-toast {
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%) scale(0.8);
        background-color: #4CAF50;
        color: white;
        padding: 40px 60px;
        border-radius: 15px;
        box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        z-index: 1000;
        opacity: 0;
        visibility: hidden;
        transition: all 0.5s ease-in-out;
        text-align: center;
        font-size: 2.5em;
        font-weight: bold;
    }
    .success-toast.show {
        opacity: 1;
        visibility: visible;
        transform: translate(-50%, -50%) scale(1);
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --- Helper Functions ---

def parse_gemini_response(text_response):
    """Parses JSON text response from Gemini and extracts data."""
    try:
        text_response1 = text_response.split("json")[1].replace("```","")
        data = json.loads(text_response1)
        merchant_name = data.get('merchant_name')
        date = data.get('date')
        total_amount = data.get('total_amount')
        category = data.get('category')

        # Basic cleanup and formatting
        date = date if date else "Unknown"
        total_amount = f"{float(total_amount):.2f}" if total_amount else "0.00"
        category = category if category else "Other"

        return {
            "Merchant Name": merchant_name,
            "Date": date,
            "Total Amount": total_amount,
            "Category": category
        }
    except json.JSONDecodeError:
        st.error(f"Gemini returned non-JSON response: {text_response}")
        return None
    except Exception as e:
        st.error(f"Error parsing Gemini response: {e}")
        return None

@st.cache_resource
def get_gspread_client():
    """Authenticates with Google Sheets using service account."""
    try:
        # creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        gcp_service_account_info = st.secrets["GCP_JSON"]
        creds = Credentials.from_service_account_info(gcp_service_account_info, scopes=SCOPES)
        gc = gspread.authorize(creds)
        return gc
    except Exception as e:
        st.error(f"Failed to authenticate with Google Sheets. "
                 f"Ensure '{SERVICE_ACCOUNT_FILE}' exists and is valid, and APIs are enabled. Error: {e}")
        return None

def append_to_sheet(data_row):
    """Appends a row of data to the specified Google Sheet."""
    gc = get_gspread_client()
    if not gc:
        return False
    try:
        spreadsheet = gc.open(SPREADSHEET_NAME)
        worksheet = spreadsheet.worksheet(spreadsheet.sheet1.title) # Get the first worksheet
        worksheet.append_row(data_row)
        return True
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Google Sheet '{SPREADSHEET_NAME}' not found. "
                 "Please check the name and ensure the service account has access.")
        return False
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"First worksheet not found in '{SPREADSHEET_NAME}'.")
        return False
    except Exception as e:
        st.error(f"Error appending data to Google Sheet: {e}")
        return False

# --- Main Streamlit App ---

st.markdown('<h1 class="main-header">🧾 Receipt Scanner Pro</h1>', unsafe_allow_html=True)
st.markdown("Take a photo of your receipt to extract details and save to Google Sheets!")

uploaded_file = st.camera_input("Take a photo of your receipt")

if 'show_success_toast' not in st.session_state:
    st.session_state.show_success_toast = False

if st.session_state.show_success_toast:
    st.markdown('<div class="success-toast show">✅ Success!</div>', unsafe_allow_html=True)
    time.sleep(2) # Display toast for 2 seconds
    st.session_state.show_success_toast = False
    st.rerun() # Rerun to hide the toast

if uploaded_file is not None:
    st.image(uploaded_file, caption="Receipt Photo", use_column_width=True)

    if st.button("Process Receipt"):
        st.session_state.show_success_toast = False # Reset toast state

        # Display scanning animation
        scan_placeholder = st.empty()
        scan_placeholder.markdown('<div class="scanner-container"><div class="scanner-bar"></div></div>', unsafe_allow_html=True)

        try:
            # Prepare image for Gemini API
            image_parts = [
                {
                    "mime_type": uploaded_file.type,
                    "data": uploaded_file.getvalue()
                },
            ]

            # Craft a precise prompt for Gemini
            prompt = """
            Extract the following information from the receipt image provided. 
            Respond ONLY with a JSON object containing the keys: `merchant_name`, `date`, `total_amount`, and `category`.
            For `total_amount`, extract the final total amount.
            For `category`, classify it as one of the following: Food, Transport, Utilities, Shopping, Entertainment, Healthcare, Other, Unknown.
            If a field is not found, use `null`.

            Example JSON format:
            {
              "merchant_name": "Starbucks",
              "date": "2023-10-26",
              "total_amount": "12.50",
              "category": "Food"
            }
            """

            # Send to Gemini API
            response = model.generate_content([prompt, image_parts[0]])
            extracted_text = response.text.strip()

            # Remove the scanning animation
            scan_placeholder.empty()

            # Parse Gemini response
            extracted_data = parse_gemini_response(extracted_text)

            if extracted_data:
                st.subheader("Extracted Data:")
                st.json(extracted_data)

                # Prepare data for Google Sheet
                sheet_row = [
                    extracted_data.get("Merchant Name", "N/A"),
                    extracted_data.get("Date", "N/A"),
                    extracted_data.get("Total Amount", "N/A"),
                    extracted_data.get("Category", "N/A")
                ]

                # Append to Google Sheet
                if append_to_sheet(sheet_row):
                    st.session_state.show_success_toast = True
                    st.rerun() # Rerun to display the toast
                else:
                    st.error("Failed to save data to Google Sheet.")
            else:
                st.error("Could not extract data from the receipt. Please try another image or check the Gemini API response.")

        except Exception as e:
            scan_placeholder.empty() # Ensure animation is removed on error
            st.error(f"An unexpected error occurred during processing: {e}")
            st.info("Please ensure your Gemini API key is correct and the image is clear.")

st.sidebar.markdown("---")
st.sidebar.subheader("How to Use:")
st.sidebar.markdown(
    """
    1. **Take a clear photo** of your receipt using the camera input.
    2. Click the "**Process Receipt**" button.
    3. The app will extract details (Merchant, Date, Total, Category).
    4. If successful, the data will be appended to your specified Google Sheet, and a success toast will appear!
    """
)
st.sidebar.subheader("Google Sheet Setup:")
st.sidebar.markdown(
    f"""
    - **Name:** `{SPREADSHEET_NAME}`
    - **Headers (first row):** `Merchant Name`, `Date`, `Total Amount`, `Category`
    - Ensure `service_account.json` is in the root directory and the service account has `Editor` access to the sheet.
    """
)
