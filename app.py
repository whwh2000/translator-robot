import streamlit as st
from google import genai
from google.genai import types 
from gtts import gTTS
import io
import re
import base64
from streamlit_mic_recorder import mic_recorder

# --- 1. SETUP & SESSION STATE ---
API_KEY = st.secrets.get("GOOGLE_API_KEY")

if "ai_client" not in st.session_state:
    if API_KEY:
        try:
            st.session_state.ai_client = genai.Client(api_key=API_KEY)
        except Exception as e:
            st.error(f"AI Setup Error: {e}")

# --- 2. LANGUAGE CONFIG (Added Spanish & Portuguese) ---
LANG_MAP = {
    "Spanish": "es", "Portuguese": "pt", "Korean": "ko", 
    "Japanese": "ja", "Danish": "da", "Swedish": "sv", 
    "Russian": "ru", "Ukrainian": "uk"
}

if "prev_lang" not in st.session_state:
    st.session_state.prev_lang = "Spanish"

# --- 3. AUDIO HELPER (Updated for Latin Accents) ---
def get_audio_html(text, lang_name):
    lang_code = LANG_MAP.get(lang_name, "en")
    
    # Scrub labels so the voice doesn't read UI markers
    clean_text = re.sub(r'\(.*?\)', '', text)
    patterns = [
        r'^Formal\s*:\s*', r'^Informal\s*:\s*', r'^You\s*\(.*?\)\s*:\s*',
        r'^Reply\s*\d+\s*:\s*', r'^Option\s*\d+\s*:\s*', r'^Robot\s*:\s*',
        r'^Translation\s*:\s*', r'^\d+\.\s*', r'^User\s*Translation\s*:\s*'
    ]
    for p in patterns:
        clean_text = re.sub(p, '', clean_text, flags=re.IGNORECASE)

    # Added support for Spanish/Portuguese accents (á, é, í, ó, ú, ñ, ç, etc.)
    if lang_name in ["Korean", "Japanese", "Russian", "Ukrainian"]:
        chars = re.findall(r'[\u3040-\u30FF\u4E00-\u9FAF\uAC00-\uD7AF\u0400-\u04FF0-9?.!, ]+', clean_text)
        clean_text = "".join(chars)
    
    clean_text = clean_text.strip()
    if not clean_text: return None

    try:
        tts = gTTS(text=clean_text, lang=lang_code)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        b64 = base64.b64encode(fp.read()).decode()
        return f'<audio controls autoplay src="data:audio/mp3;base64,{b64}" style="width: 100%; height: 35px;"></audio>'
    except Exception: return None

# --- 4. CALLBACK FOR CLEARING ---
def on_clear_click():
    st.session_state.main_input_field = ""
    for key in ["responses", "last_input", "recorder", "last_audio_hash"]:
        if key in st.session_state:
            st.session_state[key] = None

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("Robot Settings")
    target_lang = st.selectbox("Pick a Language:", list(LANG_MAP.keys()))
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

# Unified input section
audio_info = mic_recorder(start_prompt="🎙️ Speak to Robot", stop_prompt="Stop & Translate", key='recorder')
manual_input = st.text_input("⌨️ Or type in English:", key="main_input_field", placeholder="How do I get to the beach?")
st.button("🗑️ Clear All", on_click=on_clear_click)

# --- 7. INPUT SELECTION & AI LOGIC (OPTIMIZED) ---
final_input = ""
if audio_info and audio_info.get('bytes'):
    current_audio_hash = hash(audio_info['bytes'])
    if st.session_state.get('last_audio_hash') != current_audio_hash:
        with st.spinner("🤖 Listening..."):
            res = st.session_state.ai_client.models.generate_content(
                model='gemini-2.0-flash',
                contents=["Transcribe to English:", types.Part.from_bytes(data=audio_info['bytes'], mime_type='audio/wav')]
            )
            final_input = res.text.strip()
            st.session_state.last_audio_hash = current_audio_hash

if not final_input and manual_input:
    final_input = manual_input

if final_input and final_input != st.session_state.get("last_input"):
    with st.spinner("🤖 Processing..."):
        st.session_state.last_input = final_input
        
        # COMBINED PROMPT: Gets the translation AND the options in one go.
        if mode == "Live Translation":
            prompt = (f"User said: '{final_input}'. Translate this to {target_lang}. "
                      f"Also provide 3 short conversational replies. "
                      f"Format: 'User Translation: [text]', 'Option 1: [text]', 'Option 2: [text]', 'Option 3: [text]'.")
        else:
            prompt = (f"I am practicing {target_lang}. I said: '{final_input}'. "
                      f"1. Give me a 'User Translation' of what I said. "
                      f"2. Reply to me as a 'Robot' in {target_lang} (with English in brackets). "
                      f"3. Give me 3 'Options' to say back to you. "
                      f"Format: 'User Translation: [text]', 'Robot: [text]', 'Option 1: [text]', 'Option 2: [text]', 'Option 3: [text]'.")

        r_res = st.session_state.ai_client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        st.session_state.responses = r_res.text.split('\n')
        st.rerun()

# --- 8. DISPLAY ---
if st.session_state.get("last_input"):
    st.caption(f"Input: '{st.session_state.last_input}'")

if st.session_state.get("responses"):
    for i, line in enumerate(st.session_state.responses):
        if ":" in line:
            label, content = line.split(":", 1)
            c1, c2 = st.columns([0.85, 0.15])
            with c1:
                if "User" in label: st.success(f"**{label}:** {content}")
                elif "Robot" in label: st.info(f"**{label}:** {content}")
                else: st.write(f"**{label}:** {content}")
            with c2:
                if st.button("🔊", key=f"spk_{i}"):
                    audio_html = get_audio_html(content, target_lang)
                    if audio_html: st.markdown(audio_html, unsafe_allow_html=True)