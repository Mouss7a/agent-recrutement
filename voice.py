import os
import requests
from groq import Groq

client_groq = Groq(api_key=os.getenv("GROQ_API_KEY"))

def transcrire_vocal(media_id, whatsapp_token):
    try:
        # Récupérer l'URL du fichier audio
        url_info = f"https://graph.facebook.com/v18.0/{media_id}"
        headers = {"Authorization": f"Bearer {whatsapp_token}"}
        response = requests.get(url_info, headers=headers)
        media_url = response.json().get("url")

        # Télécharger le fichier audio
        audio_response = requests.get(media_url, headers=headers)
        audio_path = f"/tmp/{media_id}.ogg"
        with open(audio_path, "wb") as f:
            f.write(audio_response.content)

        # Transcrire avec Groq Whisper
        with open(audio_path, "rb") as f:
            transcription = client_groq.audio.transcriptions.create(
                file=(f"{media_id}.ogg", f.read()),
                model="whisper-large-v3",
                language="fr"
            )
        
        return transcription.text

    except Exception as e:
        return None
