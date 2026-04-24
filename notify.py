import os
import requests
import logging

logger = logging.getLogger(__name__)

def notifier_moussa(message):
    token = os.getenv("WHATSAPP_TOKEN")
    phone_id = os.getenv("PHONE_NUMBER_ID")
    moussa_phone = os.getenv("MOUSSA_PHONE")
    if not moussa_phone:
        logger.error("MOUSSA_PHONE non défini")
        return
    url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": moussa_phone, "type": "text", "text": {"body": message}}
    try:
        r = requests.post(url, headers=headers, json=payload)
        r.raise_for_status()
        logger.info("Notification envoyée à Moussa")
    except Exception as e:
        logger.error(f"Erreur notification : {e}")
