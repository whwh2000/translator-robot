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

# Track language to clear app on change
if "prev_lang" not in st.session_state:
    st.session_state.prev_lang = "Korean"

# --- 3. AUDIO HELPER (Mobile Base64 Injection) ---
def get_audio_html(text, lang_name):
    lang_code = LANG_MAP.get(lang_name, "en")
    
    # 1. Clean phonetic guides and headers
    clean_text = re.sub(r'\(.*?\)', '', text)
    patterns = [
        r'^Formal\s*:\s*', r'^Informal\s*:\s*', 
        r'^Reply\s*\d+\s*:\s*', r'^Translation\s*:\s*', r'^\d+\.\s*'
    ]
    for p in patterns:
        clean_text = re.sub(p, '', clean_text, flags=re.IGNORECASE)

    # 2. Script filtering for Non-Latin languages
    if lang_name in ["Korean", "Japanese", "Russian", "Ukrainian"]:
        chars = re.findall(r'[\u3040-\u30FF\u4E00-\u9FAF\uAC00-\uD7AF\u0400-\u04FF0-9?.!, ]+', clean_text)
        clean_text = "".join(chars)
    
    clean_text = clean_text.strip()
    if not clean_text:
        return None

    try:
        # Generate speech
        tts = gTTS(text=clean_text, lang=lang_code)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        
        # Convert to Base64 string for mobile browser stability
        b64 = base64.b64encode(fp.read()).decode()
        # Return HTML5 audio tag string
        return f'<audio controls src="data:audio/mp3;base64,{b64}" style="width: 100%; height: 30px;"></audio>'
    except Exception as e:
        return f"<span>Audio Error: {e}</span>"

# --- 4. SIDEBAR ---
with st.sidebar:
    st.header("Robot Settings")
    target_lang = st.selectbox("Pick a Language:", list(LANG_MAP.keys()))
    
    # Reset app if language changes
    if target_lang != st.session_state.prev_lang:
        st.session_state.prev_lang = target_lang
        for key in ["current_translation", "user_translation", "last_input"]:
            if key in st.session_state:
                del st.session_state[key]
        if "main_input_field" in st.session_state:
            st.session_state.main_input_field = ""
        st.rerun()

    mode = st.radio("Choose Mode:", ["Live Translation", "Practice Chat"])
    st.divider()
    if st.button("Clear History"):
        st.session_state.clear()
        st.rerun()

# --- 5. MAIN INTERFACE ---
st.title(f"🤖 Magic {target_lang} Robot")

user_input = st.text_input("Type in English:", key="main_input_field")

if user_input and user_input != st.session_state.get("last_input"):
    with st.spinner("Thinking..."):
        try:
            st.session_state.last_input = user_input
            
            # Translate User Input
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

# --- 6. DISPLAY ---
if "user_translation" in st.session_state and mode == "Practice Chat":
    if user_input == st.session_state.get("last_input"):
        st.info(f"**You said:**\n\n{st.session_state.user_translation}")
        audio_html = get_audio_html(st.session_state.user_translation, target_lang)
        if audio_html:
            st.markdown(audio_html, unsafe_allow_html=True)
        st.divider()

if "current_translation" in st.session_state:
    if user_input == st.session_state.get("last_input"):
        st.subheader(f"🤖 Robot ({mode}):")
        lines = st.session_state.current_translation.split('\n')
        
        for i, line in enumerate(lines):
            clean_line = line.strip()
            if clean_line:
                # Layout for text and audio button
                col1, col2 = st.columns([0.8, 0.2])
                with col1:
                    st.write(clean_line)
                with col2:
                    if st.button("🔊", key=f"btn_{i}"):
                        audio_player = get_audio_html(clean_line, target_lang)
                        if audio_player:
                            st.markdown(audio_player, unsafe_allow_html=True)