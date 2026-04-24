import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def sauvegarder_candidate(phone, infos, score, suspicion, statut):
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not creds_json or not sheet_id:
        _sauvegarder_local(phone, infos, score, suspicion, statut)
        return
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        sheet = gc.open_by_key(sheet_id).sheet1
        if not sheet.row_values(1):
            sheet.append_row(["Date", "Téléphone", "Nom", "Âge", "Ville", "Pays", "Expérience (mois)", "Chiffre FCFA", "Management", "Taux confirmation", "Ordinateur", "Langues", "Score", "Suspicion IA", "Statut"])
        ligne = [
            datetime.now().strftime("%d/%m/%Y %H:%M"),
            phone,
            infos.get("nom", ""),
            infos.get("age", ""),
            infos.get("ville", ""),
            infos.get("pays", ""),
            infos.get("experience_mois", ""),
            infos.get("chiffre", ""),
            infos.get("management", ""),
            infos.get("taux_confirmation", ""),
            infos.get("ordinateur", ""),
            infos.get("langues", ""),
            score,
            f"{suspicion}/10",
            statut.upper()
        ]
        sheet.append_row(ligne)
        logger.info(f"Candidate sauvegardée : {phone}")
    except Exception as e:
        logger.error(f"Erreur Google Sheets : {e}")
        _sauvegarder_local(phone, infos, score, suspicion, statut)

def _sauvegarder_local(phone, infos, score, suspicion, statut):
    try:
        fichier = "candidates.json"
        candidates = []
        if os.path.exists(fichier):
            with open(fichier, "r") as f:
                candidates = json.load(f)
        candidates.append({
            "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "phone": phone,
            "infos": infos,
            "score": score,
            "suspicion_ia": suspicion,
            "statut": statut
        })
        with open(fichier, "w") as f:
            json.dump(candidates, f, ensure_ascii=False, indent=2)
        logger.info(f"Sauvegarde locale : {phone}")
    except Exception as e:
        logger.error(f"Erreur sauvegarde locale : {e}")
