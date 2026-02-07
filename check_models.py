from google import genai
import streamlit as st

# Setup the client using your secret key
client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])

print("--- Available Models ---")
try:
    # This asks Google to list every model your key is allowed to use
    for model in client.models.list():
        print(f"Name: {model.name} | Display: {model.display_name}")
except Exception as e:
    print(f"Error checking models: {e}")