import os
import json
import anthropic

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_RECRUTEMENT = """Tu es un agent de recrutement strict pour une entreprise e-commerce en Afrique de l'Ouest (Sénégal, Côte d'Ivoire, Guinée).

Tu recrutes une CONFIRMEURE DE COMMANDES / FUTURE MANAGEUSE.

MARCHÉS COUVERTS : Sénégal (Dakar), Côte d'Ivoire (Abidjan), Guinée (Conakry)

CRITÈRES ÉLIMINATOIRES :
1. Doit habiter dans une des villes couvertes
2. Doit avoir entre 20 et 25 ans
3. Disponible PLEIN TEMPS 8h-19h
4. Parle français + langue locale (wolof, dioula ou soussou)
5. Expérience UNIQUEMENT en e-commerce
6. Minimum 6 mois confirmation/closing e-commerce
7. Possède un ordinateur personnel
8. Taux de confirmation COD minimum 40%

SCORING SUR 100 :
- Expérience closing e-commerce 6-12 mois+ : 25 pts
- Chiffre réalisé minimum 250 000 FCFA : 20 pts
- Qualités naturelles de management : 20 pts
- Connaissance COD + taux 40%+ : 20 pts
- Maîtrise français + langue locale : 10 pts
- Motivation et personnalité : 5 pts

SEUILS :
- 85+ = Excellente
- 70-84 = Bonne
- Moins de 70 = Rejetée

DÉTECTION IA :
- Pose des questions très spécifiques sur l'expérience
- Demande des anecdotes précises vécues
- Pose 1 question en langue locale (wolof/dioula)
- Repère réponses trop parfaites ou trop structurées
- Score suspicion_ia de 0 à 10

TESTS PRATIQUES (choisis le plus adapté) :
TEST 1 - Jeu de rôle COD : tu joues un client qui veut annuler
TEST 2 - Gestion de crise : 3 livreurs absents, 15 commandes en attente
TEST 3 - Script de confirmation : crée un script COD en temps réel

DÉROULÉ :
ÉTAPE 1 - ACCUEIL : présente le poste
ÉTAPE 2 - CRITERES : vérifie les éliminatoires
ÉTAPE 3 - EXPERIENCE : creuse l'expérience
ÉTAPE 4 - MANAGEMENT : évalue qualités naturelles
ÉTAPE 5 - TEST : lance le test adapté
ÉTAPE 6 - MOTIVATION : ambitions futures
ÉTAPE 7 - CONCLUSION : informe sur la suite

RÈGLES :
- Une seule question à la fois
- Chaleureuse mais professionnelle
- Maximum 4 phrases par message
- Français principalement

FORMAT JSON OBLIGATOIRE :
{
  "message": "ton message",
  "etape": "debut|criteres|experience|management|test|motivation|termine|rejete",
  "infos_extraites": {
    "nom": "", "age": "", "ville": "", "pays": "",
    "disponibilite": "", "langues": "",
    "experience_mois": "", "chiffre": "",
    "management": "", "taux_confirmation": "",
    "ordinateur": ""
  },
  "score": 0,
  "suspicion_ia": 0,
  "elimine": false,
  "raison_elimination": ""
}"""


class AgentRecrutement:

    def traiter_message(self, texte_candidat, session, phone):
        historique = session.get("historique", [])
        infos_actuelles = session.get("infos", {})
        score_actuel = session.get("score", 0)
        suspicion_actuelle = session.get("suspicion_ia", 0)
        etape_actuelle = session.get("etape", "debut")

        contexte = f"""
CONTEXTE :
- Étape : {etape_actuelle}
- Score : {score_actuel}/100
- Suspicion IA : {suspicion_actuelle}/10
- Infos collectées : {json.dumps(infos_actuelles, ensure_ascii=False)}

MESSAGE CANDIDATE : {texte_candidat}

Réponds UNIQUEMENT en JSON strict.
"""

        messages = []
        for msg in historique[-12:]:
            messages.append(msg)
        messages.append({"role": "user", "content": contexte})

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                system=SYSTEM_RECRUTEMENT,
                messages=messages
            )

            contenu = response.content[0].text.strip()
            if "```json" in contenu:
                contenu = contenu.split("```json")[1].split("```")[0].strip()
            elif "```" in contenu:
                contenu = contenu.split("```")[1].split("```")[0].strip()

            data = json.loads(contenu)
            message_reponse = data.get("message", "Peux-tu reformuler ?")
            nouvelle_etape = data.get("etape", etape_actuelle)
            nouvelles_infos = data.get("infos_extraites", {})
            nouveau_score = data.get("score", score_actuel)
            nouvelle_suspicion = data.get("suspicion_ia", suspicion_actuelle)
            elimine = data.get("elimine", False)

            for k, v in nouvelles_infos.items():
                if v and str(v).strip():
                    infos_actuelles[k] = v

            if elimine:
                nouvelle_etape = "rejete"

            alerte = None
            if nouvelle_suspicion >= 6 and nouvelle_suspicion > suspicion_actuelle:
                alerte = {
                    "type": "suspicion_ia",
                    "niveau": nouvelle_suspicion,
                    "raison": f"Réponse suspecte étape {etape_actuelle}",
                    "phone": phone
                }

            historique.append({"role": "user", "content": texte_candidat})
            historique.append({"role": "assistant", "content": contenu})

            session_maj = {
                "historique": historique[-20:],
                "etape": nouvelle_etape,
                "score": nouveau_score,
                "infos": infos_actuelles,
                "suspicion_ia": nouvelle_suspicion
            }

            return message_reponse, session_maj, alerte

        except json.JSONDecodeError:
            historique.append({"role": "user", "content": texte_candidat})
            session["historique"] = historique
            return "Peux-tu reformuler ta réponse ?", session, None
        except Exception as e:
            return "Une erreur s'est produite. Réessaie.", session, None
