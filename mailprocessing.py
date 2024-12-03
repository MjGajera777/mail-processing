import re
import time
import openai
import base64
import os
import json
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError  # Import HttpError

# ChatGPT API Configuration
openai.api_key = "test"

# Gmail API Configuration
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# Selenium WebDriver Configuration
CHROMEDRIVER_PATH = "chromedriver.exe"
URL = "https://test.apiclient.com/SIRIUS/reports/search.html?screenId=DOC_MANAGEMENT_REPORT#"

def get_email_content(payload):
    """Extract and decode the email content from the payload."""
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain':
                encoded_content = part['body'].get('data')
                if encoded_content:
                    decoded_content = base64.urlsafe_b64decode(encoded_content).decode("utf-8")
                    return decoded_content
    return None

def authenticate_gmail():
    """Authenticate with Gmail API and return the service object."""
    creds = None
    token_path = "token.json"
    creds_path = "creds.json"

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(token_path, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)

def get_unread_emails(service):
    """Fetch unread emails matching the subject condition."""
    results = service.users().messages().list(userId="me", labelIds=["INBOX"], q="is:unread").execute()
    messages = results.get("messages", [])
    
    for message in messages:
        msg = service.users().messages().get(userId="me", id=message["id"]).execute()
        payload = msg["payload"]
        headers = payload.get("headers", [])
        
        # Debug: Print headers to check their structure
        # print("Email Headers:", headers)

        subject = next((header["value"] for header in headers if header["name"] == "Subject"), "")
        if "Invoice Status" in subject:
            print("Email found!")
            email_content = get_email_content(payload)
            if email_content:
                return email_content, msg["threadId"], headers  # Return threadId instead of message_id
    
    return None, None, None

def analyze_email_content(email_content):
    """Send email content to OpenAI API for analysis."""
    prompt = f"""
    Analyze the following email content and give response of both the points inside an ARRAY:
    1. Is it asking about an invoice status? Respond only with "Yes" if confidence score is 80% or more, otherwise respond "No"
    2. Extract the document number if present, otherwise respond with False.
    Email Content:
    {email_content}
    """
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=100,
        temperature=0.7
    )

    result = response['choices'][0]['message']['content'].strip()
    return result

def fetch_status_from_website(document_number):
    """Automate the website actions using Selenium."""
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service)
    
    try:
        driver.get(URL)
        time.sleep(5)
        
        username_field = driver.find_elements(By.NAME, "login")
        if username_field:
            username_field[0].send_keys('parthchoksi@botsinbusiness.com')
            password_field = driver.find_element(By.NAME, "password")
            password_field.send_keys("Centerviews@123")
            password_field.send_keys(Keys.RETURN)
            time.sleep(5)
        
        document_number_field = driver.find_elements(By.NAME, "documentNumber")
        document_number_field[0].send_keys(document_number)
        search_button = driver.find_elements(By.NAME, "action.search.submit")
        search_button[0].send_keys(Keys.RETURN)
        time.sleep(5)
        
        status_header = driver.find_elements(By.CLASS_NAME, "col-10")[0].find_elements(By.XPATH, "./*")[0].text
        
        if status_header == "Status":
            status_of_invoice = driver.find_elements(By.CLASS_NAME, "col-10")[1].text
        else:
            status_of_invoice = False
        
        return status_of_invoice
    finally:
        driver.quit()

def reply_to_email(service, thread_id, reply_content, recipient_email):
    """Reply to the email with the retrieved status."""
    raw_message = f"From: me\nTo: {recipient_email}\nSubject: Re: Invoice Status\nContent-Type: text/plain; charset=UTF-8\n\n{reply_content}"
    raw_message_encoded = base64.urlsafe_b64encode(raw_message.encode("utf-8")).decode("utf-8")
    
    message = {
        "raw": raw_message_encoded,
        "threadId": thread_id  # Use threadId for the reply
    }
    
    try:
        service.users().messages().send(userId="me", body=message).execute()
        print("Reply sent successfully.")
    except HttpError as error:
        print(f"An error occurred: {error}")

def main():
    # Authenticate and get the Gmail API service
    service = authenticate_gmail()

    # Get unread emails
    email_content, thread_id, headers = get_unread_emails(service)
    if not email_content:
        print("No unread emails found.")
        return

    # Extract sender email (assuming it's in the headers)
    recipient_email = next((header["value"] for header in headers if header["name"] == "From"), "")

    # Analyze email content
    analysis = analyze_email_content(email_content)

    if analysis:
        # Clean the analysis
        cleaned_analysis = json.loads(analysis.replace('```json\n', '').replace('\n```', '').strip())
        print("ChatGPT Analysis:")
        print("Is the inquirer asking status of invoice? ",cleaned_analysis[0])
        print("What is the document number provided?",cleaned_analysis[1])

        if cleaned_analysis[0] == 'Yes' and cleaned_analysis[1] != False:
            document_number = cleaned_analysis[1]
            # print(f"Extracted Document Number: {document_number}")

            # Fetch status from the website
            print("Starting to fetch invoice status from web portal...")
            status = fetch_status_from_website(document_number)
            print(f"Completed fetching the invoice status for the document: {document_number}")
            print(f"Invoice Status: {status}")

            # Prepare the reply content
            reply_content = f"The status of the invoice with Document Number {document_number} is: {status}."

            # Send the reply using threadId
            print("Starting the reply back to the mail...")

            reply_to_email(service, thread_id, reply_content, recipient_email)
        else:
            print("Email does not meet the confidence threshold for invoice inquiry.")
    else:
        print("Analysis failed, no valid response received from OpenAI.")

if __name__ == "__main__":
    main()
