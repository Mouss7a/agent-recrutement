import os
import logging
import requests
import base64
import json
from flask import Flask, request
from agent import AgentRecrutement
from voice import transcrire_vocal
from notify import notifier_moussa
from sheets import sauvegarder_candidate
from upstash_redis import Redis

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

agent = AgentRecrutement()

# Redis pour persistance sessions
redis = Redis(
    url=os.getenv("UPSTASH_REDIS_REST_URL"),
    token=os.getenv("UPSTASH_REDIS_REST_TOKEN")
)

FORMATS_NON_SUPPORTES = [
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
]

def get_session(phone):
    try:
        data = redis.get(f"session:{phone}")
        if data:
            return json.loads(data)
    except:
        pass
    return {
        "historique": [], "etape": "debut", "score": 0,
        "infos": {}, "suspicion_ia": 0, "vocal_attendu": False,
        "genre_score": 0, "vocal_refuse_count": 0,
        "vocal_incompris_count": 0, "dernier_message_vocal": False,
        "rapport_final": None
    }

def save_session(phone, session):
    try:
        redis.set(f"session:{phone}", json.dumps(session), ex=86400)
    except Exception as e:
        logger.error(f"Erreur sauvegarde session: {e}")

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

        session = get_session(phone)

        if session.get("etape") in ["termine", "rejete"]:
            return "OK", 200

        texte = ""
        document_contenu = None
        token_wa = os.getenv("WHATSAPP_TOKEN")

        if msg_type == "text":
            texte = message["text"]["body"]

        elif msg_type == "audio":
            audio_id = message["audio"]["id"]
            texte = transcrire_vocal(audio_id, token_wa)
            if not texte:
                vocal_incompris = session.get("vocal_incompris_count", 0)
                if vocal_incompris == 0:
                    envoyer_message(phone, "Je n'ai pas bien entendu votre vocal. Pouvez-vous le renvoyer en parlant un peu plus clairement ? 🎤")
                    session["vocal_incompris_count"] = 1
                    save_session(phone, session)
                else:
                    envoyer_message(phone, "Je n'arrive toujours pas à comprendre. Pouvez-vous écrire votre réponse en texte ? ✍️")
                    session["vocal_incompris_count"] = 0
                    save_session(phone, session)
                return "OK", 200
            session["dernier_message_vocal"] = True
            session["vocal_incompris_count"] = 0

        elif msg_type in ["document", "image"]:
            if msg_type == "document":
                media_info = message["document"]
                mime_type = media_info.get("mime_type", "")
                if mime_type in FORMATS_NON_SUPPORTES:
                    envoyer_message(phone, "Je ne peux pas lire ce format. Pouvez-vous me faire un résumé vocal ou écrit de votre expérience ? 🎤")
                    texte = "[candidate a envoyé un fichier non supporté]"
                else:
                    media_id = media_info["id"]
                    document_contenu = telecharger_et_analyser_document(media_id, token_wa, mime_type)
                    texte = "[candidate a envoyé un document PDF]"
            else:
                media_id = message["image"]["id"]
                document_contenu = telecharger_et_analyser_image(media_id, token_wa)
                texte = "[candidate a envoyé une image]"
        else:
            envoyer_message(phone, "Merci d'envoyer uniquement des messages texte, vocaux, images ou documents PDF. 🙏")
            return "OK", 200

        if not texte.strip():
            return "OK", 200

        reponse, session_maj, alerte, rapport_final = agent.traiter_message(
            texte, session, phone, document_contenu
        )

        session_maj["dernier_message_vocal"] = False
        save_session(phone, session_maj)
        envoyer_message(phone, reponse)

        if alerte and alerte.get("type") == "suspicion_ia":
            notifier_moussa(f"⚠️ SUSPICION IA\n📱 {phone}\n🔢 Niveau: {alerte.get('niveau')}/10\n💬 {texte[:200]}")

        if session_maj.get("etape") in ["termine", "rejete"]:
            score = session_maj.get("score", 0)
            infos = session_maj.get("infos", {})
            suspicion = session_maj.get("suspicion_ia", 0)
            etape = session_maj.get("etape")
            sauvegarder_candidate(phone, infos, score, suspicion, etape)

            if score >= 70 and etape == "termine":
                envoyer_rapport_whatsapp(phone, score, infos, suspicion, rapport_final, session_maj)

    except Exception as e:
        logger.error(f"Erreur: {e}")
    return "OK", 200


def envoyer_rapport_whatsapp(phone, score, infos, suspicion, rapport, session):
    try:
        r = rapport or {}
        scoring = r.get("scoring_detail", {})
        criteres = r.get("criteres", {})
        vocaux = r.get("performance_vocale", {})
        analyse = r.get("analyse_ia", {})

        recommandation = analyse.get("recommandation", "ATTENDRE")
        emoji_reco = "🟢" if recommandation == "APPELER" else "🟡" if recommandation == "ATTENDRE" else "🔴"

        fiche = f"""🎯 NOUVELLE CANDIDATE — RAPPORT COMPLET

👤 IDENTITÉ
- Nom : {infos.get('nom', 'N/A')}
- Âge : {infos.get('age', 'N/A')} ans
- Ville : {infos.get('ville', 'N/A')} / {infos.get('pays', 'N/A')}
- Téléphone : {phone}

📊 SCORE GLOBAL : {score}/100
- Expérience closing : {scoring.get('experience', {}).get('points', '?')}/25
- Chiffre réalisé : {scoring.get('chiffre', {}).get('points', '?')}/20
- Management : {scoring.get('management', {}).get('points', '?')}/20
- COD + taux : {scoring.get('cod_taux', {}).get('points', '?')}/20
- Langues : {scoring.get('langues', {}).get('points', '?')}/10
- Motivation : {scoring.get('motivation', {}).get('points', '?')}/5

✅ CRITÈRES VALIDÉS
- Disponibilité 8h-19h : {'✅' if criteres.get('disponibilite') else '❌'}
- Mobilité bureau : {'✅' if criteres.get('mobilite_bureau') else '❌'}
- Ordinateur : {'✅' if criteres.get('ordinateur') else '❌'}
- Langue locale : {'✅' if criteres.get('langue_locale') else '❌'}
- Expérience COD : {criteres.get('experience_mois', '?')} mois
- Taux confirmation : {criteres.get('taux_confirmation', '?')}%
- Chiffre réalisé : {criteres.get('chiffre_fcfa', '?')} FCFA

🎤 PERFORMANCE VOCALE
- Vocal 1 (présentation) : {vocaux.get('vocal1_presentation', 'N/A')}
- Vocal 2 (dilemme) : {vocaux.get('vocal2_dilemme', 'N/A')}
- Vocal 3 (jeu de rôle) : {vocaux.get('vocal3_jeu_role', 'N/A')}
- Panique détectée : {'⚠️ Oui' if vocaux.get('panique_detectee') else '✅ Non'}
- Bégaiement détecté : {'⚠️ Oui' if vocaux.get('begaiement_detecte') else '✅ Non'}
- Difficulté compréhension : {'⚠️ Oui' if vocaux.get('difficulte_comprehension') else '✅ Non'}

🤖 ANALYSE IA
- Suspicion triche : {suspicion}/10
- Cohérence vocal/texte : {analyse.get('coherence_vocal_texte', 'N/A')}
- Points forts : {analyse.get('points_forts', 'N/A')}
- Points faibles : {analyse.get('points_faibles', 'N/A')}

{emoji_reco} RECOMMANDATION : {recommandation}"""

        notifier_moussa(fiche)

    except Exception as e:
        logger.error(f"Erreur envoi rapport: {e}")
        notifier_moussa(f"✅ CANDIDATE TERMINÉE\n📱 {phone}\n👤 {infos.get('nom','N/A')}\n⭐ Score: {score}/100")


def telecharger_et_analyser_document(media_id, token, mime_type):
    try:
        url_info = f"https://graph.facebook.com/v18.0/{media_id}"
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(url_info, headers=headers)
        media_url = response.json().get("url")
        file_response = requests.get(media_url, headers=headers)
        file_data = base64.standard_b64encode(file_response.content).decode("utf-8")

        import anthropic
        client_doc = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client_doc.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "document", "source": {"type": "base64", "media_type": mime_type, "data": file_data}},
                    {"type": "text", "text": "Analyse ce document de candidature. Extrais en JSON : nom_complet, experience_mois, taux_confirmation, chiffre_ventes_fcfa, competences_cles, ville_pays, langues_parlees, outils_utilises, points_forts, points_faibles."}
                ]
            }]
        )
        return response.content[0].text
    except Exception as e:
        logger.error(f"Erreur lecture document: {e}")
        return None


def telecharger_et_analyser_image(media_id, token):
    try:
        url_info = f"https://graph.facebook.com/v18.0/{media_id}"
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(url_info, headers=headers)
        media_url = response.json().get("url")
        image_response = requests.get(media_url, headers=headers)
        image_data = base64.standard_b64encode(image_response.content).decode("utf-8")
        content_type = image_response.headers.get("Content-Type", "image/jpeg")

        import anthropic
        client_img = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client_img.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": content_type, "data": image_data}},
                    {"type": "text", "text": "Analyse cette image. Extrais en JSON toutes les informations visibles : statistiques, taux de confirmation, chiffres de vente, expérience, compétences, outils utilisés."}
                ]
            }]
        )
        return response.content[0].text
    except Exception as e:
        logger.error(f"Erreur lecture image: {e}")
        return None


def envoyer_message(phone, texte):
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
