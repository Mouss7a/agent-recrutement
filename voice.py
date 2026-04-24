import os
import requests
import tempfile
import logging

logger = logging.getLogger(__name__)

def telecharger_audio(audio_id):
    token = os.getenv("WHATSAPP_TOKEN")
    url_info = f"https://graph.facebook.com/v18.0/{audio_id}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(url_info, headers=headers)
        r.raise_for_status()
        audio_url = r.json().get("url")
        if not audio_url:
            return None
        r_audio = requests.get(audio_url, headers=headers)
        r_audio.raise_for_status()
        return r_audio.content
    except Exception as e:
        logger.error(f"Erreur téléchargement audio : {e}")
        return None

def transcrire_vocal(audio_id):
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        return None
    audio_bytes = telecharger_audio(audio_id)
    if not audio_bytes:
        return None
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(audio_bytes)
            temp_path = f.name
        with open(temp_path, "rb") as audio_file:
            response = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {openai_key}"},
                files={"file": ("audio.ogg", audio_file, "audio/ogg")},
                data={"model": "whisper-1", "language": "fr", "response_format": "text"}
            )
            response.raise_for_status()
            return response.text.strip()
    except Exception as e:
        logger.error(f"Erreur Whisper : {e}")
        return None
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except:
                pass
