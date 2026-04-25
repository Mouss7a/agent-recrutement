import os
import logging
from flask import Flask, request
from agent import AgentRecrutement
from voice import transcrire_vocal
from notify import notifier_moussa
from sheets import sauvegarder_candidate

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

agent = AgentRecrutement()
sessions = {}

@app.route("/webhook", methods=["GET"])
def verify():
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if token == os.getenv("VERIFY_TOKEN"):
        return challenge
    return "Token invalide", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    try:
        entry = data["entry"][0]["changes"][0]["value"]
        if "messages" not in entry:
            return "OK", 200
        message = entry["messages"][0]
        phone = message["from"]
        msg_type = message["type"]
        if phone not in sessions:
            sessions[phone] = {"historique": [], "etape": "debut", "score": 0, "infos": {}, "suspicion_ia": 0}
        session = sessions[phone]
        if session.get("etape") in ["termine", "rejete"]:
            return "OK", 200
        texte = ""
        if msg_type == "text":
            texte = message["text"]["body"]
        elif msg_type == "audio":
            audio_id = message["audio"]["id"]
            token = os.getenv("WHATSAPP_TOKEN")
            texte = transcrire_vocal(audio_id, token)
            if not texte:
                envoyer_message(phone, "Je n'ai pas pu comprendre ton vocal. Tu peux réécrire en texte ?")
                return "OK", 200
        else:
            envoyer_message(phone, "Merci d'envoyer uniquement des messages texte ou vocaux.")
            return "OK", 200
        if not texte.strip():
            return "OK", 200
        reponse, session_maj, alerte = agent.traiter_message(texte, session, phone)
        sessions[phone] = session_maj
        envoyer_message(phone, reponse)
        if alerte and alerte.get("type") == "suspicion_ia":
            notifier_moussa(f"⚠️ SUSPICION IA\n📱 {phone}\n🔢 Niveau: {alerte.get('niveau')}/10\n💬 {texte[:200]}")
        if session_maj.get("etape") in ["termine", "rejete"]:
            score = session_maj.get("score", 0)
            infos = session_maj.get("infos", {})
            suspicion = session_maj.get("suspicion_ia", 0)
            etape = session_maj.get("etape")
            sauvegarder_candidate(phone, infos, score, suspicion, etape)
            if score >= 85:
                notifier_moussa(f"🌟 EXCELLENTE CANDIDATE\n📱 {phone}\n👤 {infos.get('nom','N/A')}\n🎂 {infos.get('age','N/A')} ans\n⭐ Score: {score}/100\n🤖 IA: {suspicion}")
            elif score >= 70:
                notifier_moussa(f"👍 BONNE CANDIDATE\n📱 {phone}\n👤 {infos.get('nom','N/A')}\n⭐ Score: {score}/100\n🤖 IA: {suspicion}")
    except Exception as e:
        logger.error(f"Erreur: {e}")
    return "OK", 200

def envoyer_message(phone, texte):
    import requests
    token = os.getenv("WHATSAPP_TOKEN")
    phone_id = os.getenv("PHONE_NUMBER_ID")
    url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": texte}}
    try:
        r = requests.post(url, headers=headers, json=payload)
        r.raise_for_status()
    except Exception as e:
        logger.error(f"Erreur envoi: {e}")
