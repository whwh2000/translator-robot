import streamlit as st
from google import genai
from gtts import gTTS
import io
import re

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

# --- 3. DYNAMIC RESET LOGIC ---
if "prev_lang" not in st.session_state:
    st.session_state.prev_lang = "Korean"

# --- 4. AUDIO HELPER (Mobile Optimized) ---
def get_audio(text, lang_name):
    lang_code = LANG_MAP.get(lang_name, "en")
    
    # Remove phonetic guides in brackets
    clean_text = re.sub(r'\(.*?\)', '', text)
    
    # List of labels to strip from the audio voice
    patterns_to_remove = [
        r'^Formal\s*:\s*', 
        r'^Informal\s*:\s*', 
        r'^Reply\s*\d+\s*:\s*', 
        r'^Translation\s*:\s*',
        r'^\d+\.\s*'
    ]
    
    for pattern in patterns_to_remove:
        clean_text = re.sub(pattern, '', clean_text, flags=re.IGNORECASE)

    # For non-latin scripts, keep only those characters
    if lang_name in ["Korean", "Japanese", "Russian", "Ukrainian"]:
        target_chars = re.findall(r'[\u3040-\u30FF\u4E00-\u9FAF\uAC00-\uD7AF\u0400-\u04FF0-9?.!, ]+', clean_text)
        clean_text = "".join(target_chars)
    
    clean_text = clean_text.strip()
    
    if not clean_text:
        return None

    try:
        # Generate Audio
        tts = gTTS(text=clean_text, lang=lang_code)
        audio_fp = io.BytesIO()
        tts.write_to_fp(audio_fp)
        audio_fp.seek(0) # Move to the start of the file
        return audio_fp.read()
    except Exception as e:
        st.error(f"Audio Error: {e}")
        return None

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("Robot Settings")
    target_lang = st.selectbox("Pick a Language:", list(LANG_MAP.keys()))
    
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
    if st.button("Clear History Manually"):
        st.session_state.clear()
        st.rerun()

# --- 6. MAIN INTERFACE ---
st.title(f"🤖 Magic {target_lang} Robot")

user_input = st.text_input("Type in English and press Enter:", key="main_input_field")

if user_input and user_input != st.session_state.get("last_input"):
    with st.spinner("🤖 Thinking..."):
        try:
            st.session_state.last_input = user_input
            
            # Step A: User translation
            user_trans_res = st.session_state.ai_client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=f"Translate into natural {target_lang}: '{user_input}'",
                config={'temperature': 0.0}
            )
            st.session_state.user_translation = user_trans_res.text

            # Step B: Robot response
            if mode == "Live Translation":
                prompt = (f"Translate '{user_input}' into {target_lang}. Provide formal, "
                          f"informal, and 3 replies. Each on a NEW line. Format as 'Formal: [text]' etc.")
            else:
                prompt = (f"Reply as a friend in {target_lang} to: '{st.session_state.user_translation}'. "
                          f"Then give 3 follow-up options in {target_lang} with English meanings.")

            robot_res = st.session_state.ai_client.models.generate_content(
                model='gemini-2.0-flash', contents=prompt, config={'temperature': 0.0}
            )
            st.session_state.current_translation = robot_res.text
            
        except Exception as e:
            st.error(f"Robot Error: {e}")

# --- 7. DISPLAY ---
if "user_translation" in st.session_state and mode == "Practice Chat":
    if user_input == st.session_state.get("last_input"):
        st.info(f"**You said in {target_lang}:**\n\n{st.session_state.user_translation}")
        if st.button(f"🔊 Hear your {target_lang}", key="user_audio_btn"):
            audio_data = get_audio(st.session_state.user_translation, target_lang)
            if audio_data:
                st.audio(audio_data, format="audio/mp3")
        st.divider()

if "current_translation" in st.session_state:
    if user_input == st.session_state.get("last_input"):
        st.subheader(f"🤖 Robot ({mode}):")
        lines = st.session_state.current_translation.split('\n')
        
        for i, line in enumerate(lines):
            clean_line = line.strip()
            if clean_line:
                col1, col2 = st.columns([0.85, 0.15])
                with col1:
                    st.write(clean_line)
                with col2:
                    if st.button("🔊", key=f"audio_btn_{i}"):
                        audio_data = get_audio(clean_line, target_lang)
                        if audio_data:
                            # We show the player. On mobile, this is more reliable than autoplay.
                            st.audio(audio_data, format="audio/mp3")