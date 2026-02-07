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

# --- 2. LANGUAGE CONFIG ---
LANG_MAP = {
    "Korean": "ko", "Japanese": "ja", "Danish": "da", 
    "Swedish": "sv", "Russian": "ru", "Ukrainian": "uk"
}

if "prev_lang" not in st.session_state:
    st.session_state.prev_lang = "Korean"

# --- 3. AUDIO HELPER (Mobile Base64 + Label Scrubbing) ---
def get_audio_html(text, lang_name):
    lang_code = LANG_MAP.get(lang_name, "en")
    
    # 1. Remove phonetic guides in brackets
    clean_text = re.sub(r'\(.*?\)', '', text)
    
    # 2. Scrub labels so the voice doesn't read the UI markers
    patterns = [
        r'^Formal\s*:\s*', r'^Informal\s*:\s*', r'^You\s*\(.*?\)\s*:\s*',
        r'^Reply\s*\d+\s*:\s*', r'^Option\s*\d+\s*:\s*', r'^Robot\s*:\s*',
        r'^Translation\s*:\s*', r'^\d+\.\s*'
    ]
    for p in patterns:
        clean_text = re.sub(p, '', clean_text, flags=re.IGNORECASE)

    # 3. Native script filter
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
        return f'<audio controls src="data:audio/mp3;base64,{b64}" style="width: 100%; height: 35px;"></audio>'
    except Exception: return None

# --- 4. CALLBACK FOR CLEARING ---
def on_clear_click():
    st.session_state.main_input_field = ""
    for key in ["current_translation", "user_translation", "last_input", "recorder", "last_audio_hash"]:
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

st.write("🎙️ Step 1: Speak to the robot")
audio_info = mic_recorder(start_prompt="Start Recording", stop_prompt="Stop & Translate", key='recorder')

st.write("---")
st.write("⌨️ Step 2: Or type here")
input_col, clear_col = st.columns([0.82, 0.18])

with input_col:
    manual_input = st.text_input("English Text:", key="main_input_field", placeholder="Ask something...")

with clear_col:
    st.markdown("<div style='padding-top: 28px;'></div>", unsafe_allow_html=True)
    st.button("🗑️", on_click=on_clear_click)

# --- 7. INPUT SELECTION ---
final_input = ""
if audio_info and audio_info.get('bytes'):
    current_audio_hash = hash(audio_info['bytes'])
    if st.session_state.get('last_audio_hash') != current_audio_hash:
        with st.spinner("🤖 Transcribing..."):
            try:
                response = st.session_state.ai_client.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=[
                        "Transcribe this audio into English text. Only return the text.",
                        types.Part.from_bytes(data=audio_info['bytes'], mime_type='audio/wav')
                    ]
                )
                final_input = response.text.strip()
                st.session_state.last_audio_hash = current_audio_hash
            except Exception as e:
                st.error(f"Voice Error: {e}")

if not final_input and manual_input:
    final_input = manual_input

# --- 8. AI LOGIC ---
if final_input and final_input != st.session_state.get("last_input"):
    with st.spinner("🤖 Thinking..."):
        try:
            st.session_state.last_input = final_input
            
            # Step 1: Always get the translation of what the user just said
            u_res = st.session_state.ai_client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=f"Translate into natural {target_lang}: '{final_input}'. Only return the translation."
            )
            st.session_state.user_translation = u_res.text

            # Step 2: Get the Robot's list (Formal/Informal OR Conversational)
            if mode == "Live Translation":
                prompt = (f"Translate '{final_input}' into {target_lang}. "
                          f"Provide: 1 Formal version, 1 Informal version, and 3 short replies. "
                          f"Format: 'Formal: [text]', 'Informal: [text]', 'Reply 1: [text]', 'Reply 2: [text]', 'Reply 3: [text]'. "
                          f"Each on a NEW line.")
            else:
                prompt = (f"You are a friendly conversation partner in {target_lang}. "
                          f"User said: '{final_input}'. "
                          f"Provide: "
                          f"1. A direct reply in {target_lang} (with English meaning in brackets). "
                          f"2. Three follow-up options for the user to say back to you in {target_lang} (with English meanings). "
                          f"Format: 'Robot: [text]', 'Option 1: [text]', 'Option 2: [text]', 'Option 3: [text]'. "
                          f"Each on a NEW line.")

            r_res = st.session_state.ai_client.models.generate_content(
                model='gemini-2.0-flash', contents=prompt
            )
            st.session_state.current_translation = r_res.text
            st.rerun()
            
        except Exception as e:
            st.error(f"AI Error: {e}")

# --- 9. DISPLAY ---
if st.session_state.get("last_input"):
    st.caption(f"Input: '{st.session_state.last_input}'")

# Display User's own translation first (with Audio)
if st.session_state.get("user_translation"):
    col_a, col_b = st.columns([0.8, 0.2])
    with col_a:
        st.info(f"**You ({target_lang}):** {st.session_state.user_translation}")
    with col_b:
        st.write(" ")
        if st.button("🔊", key="user_audio"):
            u_audio = get_audio_html(st.session_state.user_translation, target_lang)
            if u_audio: st.markdown(u_audio, unsafe_allow_html=True)

# Display Robot Response list
if st.session_state.get("current_translation"):
    st.subheader(f"🤖 Robot ({mode}):")
    lines = st.session_state.current_translation.split('\n')
    for i, line in enumerate(lines):
        clean_line = line.strip()
        if clean_line:
            c1, c2 = st.columns([0.8, 0.2])
            with c1: st.write(clean_line)
            with c2:
                if st.button("🔊", key=f"btn_{i}"):
                    player = get_audio_html(clean_line, target_lang)
                    if player: st.markdown(player, unsafe_allow_html=True)