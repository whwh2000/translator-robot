import streamlit as st
from google import genai
from gtts import gTTS
import io
import re
import base64

# --- 1. SETUP & SESSION STATE ---
API_KEY = st.secrets.get("GOOGLE_API_KEY")

if "ai_client" not in st.session_state:
    if API_KEY:
        try:
            st.session_state.ai_client = genai.Client(api_key=API_KEY)
        except Exception as e:
            st.error(f"AI Setup Error: {e}")

# --- 2. LANGUAGE CONFIG ---
LANG_MAP = {
    "Korean": "ko",
    "Japanese": "ja",
    "Danish": "da",
    "Swedish": "sv",
    "Russian": "ru",
    "Ukrainian": "uk"
}

if "prev_lang" not in st.session_state:
    st.session_state.prev_lang = "Korean"

# --- 3. AUDIO HELPER (Base64 + Header Scrubbing) ---
def get_audio_html(text, lang_name):
    lang_code = LANG_MAP.get(lang_name, "en")
    
    # Remove phonetic guides in brackets
    clean_text = re.sub(r'\(.*?\)', '', text)
    
    # Remove labels so the robot doesn't say "Formal" or "Reply 1"
    patterns = [
        r'^Formal\s*:\s*', r'^Informal\s*:\s*', 
        r'^Reply\s*\d+\s*:\s*', r'^Translation\s*:\s*', r'^\d+\.\s*'
    ]
    for p in patterns:
        clean_text = re.sub(p, '', clean_text, flags=re.IGNORECASE)

    # For non-Latin scripts, filter for specific characters
    if lang_name in ["Korean", "Japanese", "Russian", "Ukrainian"]:
        chars = re.findall(r'[\u3040-\u30FF\u4E00-\u9FAF\uAC00-\uD7AF\u0400-\u04FF0-9?.!, ]+', clean_text)
        clean_text = "".join(chars)
    
    clean_text = clean_text.strip()
    if not clean_text:
        return None

    try:
        tts = gTTS(text=clean_text, lang=lang_code)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        
        # Base64 encoding for mobile stability
        b64 = base64.b64encode(fp.read()).decode()
        return f'<audio controls src="data:audio/mp3;base64,{b64}" style="width: 100%; height: 35px;"></audio>'
    except Exception:
        return None

# --- 4. CALLBACK FOR CLEARING (Fixes the Sync Error) ---
def on_clear_click():
    # Reset the input and wipe the translation memory
    st.session_state.main_input_field = ""
    for key in ["current_translation", "user_translation", "last_input"]:
        if key in st.session_state:
            st.session_state[key] = None

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("Robot Settings")
    target_lang = st.selectbox("Pick a Language:", list(LANG_MAP.keys()))
    
    # Auto-reset if language is changed
    if target_lang != st.session_state.prev_lang:
        st.session_state.prev_lang = target_lang
        on_clear_click()
        st.rerun()
        
    mode = st.radio("Choose Mode:", ["Live Translation", "Practice Chat"])
    st.divider()
    if st.button("Deep Cache Clear"):
        st.session_state.clear()
        st.rerun()

# --- 6. MAIN INTERFACE ---
st.title(f"🤖 Magic {target_lang} Robot")

# Input layout with 🗑️ button side-by-side
input_col, clear_col = st.columns([0.82, 0.18])

with input_col:
    user_input = st.text_input("Type in English:", key="main_input_field", placeholder="Talk to the robot...")

with clear_col:
    st.markdown("<div style='padding-top: 28px;'></div>", unsafe_allow_html=True)
    st.button("🗑️", on_click=on_clear_click, help="Clear text and results")

if user_input and user_input != st.session_state.get("last_input"):
    with st.spinner("🤖 Thinking..."):
        try:
            st.session_state.last_input = user_input
            
            # Translate User's Input
            u_res = st.session_state.ai_client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=f"Translate into natural {target_lang}: '{user_input}'",
                config={'temperature': 0.0}
            )
            st.session_state.user_translation = u_res.text

            # Generate Robot Response
            if mode == "Live Translation":
                prompt = (f"Translate '{user_input}' into {target_lang}. Provide formal, "
                          f"informal, and 3 replies. Each on a NEW line. Format as 'Formal: [text]' etc.")
            else:
                prompt = (f"Reply as a friend in {target_lang} to: '{st.session_state.user_translation}'. "
                          f"Then give 3 follow-up options in {target_lang} with English meanings.")

            r_res = st.session_state.ai_client.models.generate_content(
                model='gemini-2.0-flash', contents=prompt, config={'temperature': 0.0}
            )
            st.session_state.current_translation = r_res.text
            
        except Exception as e:
            st.error(f"AI Error: {e}")

# --- 7. DISPLAY ---
# Display User's translation in Practice Mode
if st.session_state.get("user_translation") and mode == "Practice Chat":
    st.info(f"**You said in {target_lang}:**\n\n{st.session_state.user_translation}")
    u_audio = get_audio_html(st.session_state.user_translation, target_lang)
    if u_audio:
        st.markdown(u_audio, unsafe_allow_html=True)
    st.divider()

# Display Robot's translation/replies
if st.session_state.get("current_translation"):
    st.subheader(f"🤖 Robot ({mode}):")
    lines = st.session_state.current_translation.split('\n')
    
    for i, line in enumerate(lines):
        clean_line = line.strip()
        if clean_line:
            col1, col2 = st.columns([0.8, 0.2])
            with col1:
                st.write(clean_line)
            with col2:
                if st.button("🔊", key=f"btn_{i}"):
                    audio_html = get_audio_html(clean_line, target_lang)
                    if audio_html:
                        st.markdown(audio_html, unsafe_allow_html=True)