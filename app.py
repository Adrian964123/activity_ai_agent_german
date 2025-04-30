import os
import json
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from openai import OpenAI

# Umgebungsvariablen aus .env-Datei laden
load_dotenv()

# API-Schlüssel aus Umgebungsvariablen holen
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEOCODING_API_KEY = os.getenv("GEOCODING_API_KEY")

# Prüfen, ob die API-Schlüssel vorhanden sind
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY nicht gefunden. Bitte in der .env-Datei definieren.")
if not GEOCODING_API_KEY:
    print("Warnung: GEOCODING_API_KEY nicht gefunden. Geocoding-Funktionen werden nicht verfügbar sein.")

# OpenAI Client initialisieren
client = OpenAI(api_key=OPENAI_API_KEY)

class FreizeitaktivitätenAgent:
    def __init__(self):
        self.model = "gpt-3.5-turbo"
        
    def get_coordinates(self, location):
        """
        Konvertiert einen Ortsnamen in Geokoordinaten
        """
        if not GEOCODING_API_KEY:
            print("Geocoding nicht verfügbar. API-Schlüssel fehlt.")
            return None
            
        try:
            url = f"https://maps.googleapis.com/maps/api/geocode/json?address={location}&key={GEOCODING_API_KEY}"
            response = requests.get(url)
            data = response.json()
            
            if data["status"] == "OK":
                lat = data["results"][0]["geometry"]["location"]["lat"]
                lng = data["results"][0]["geometry"]["location"]["lng"]
                return lat, lng
            else:
                print(f"Geocoding-Fehler: {data['status']}")
                return None
        except Exception as e:
            print(f"Fehler bei der Koordinatenbestimmung: {e}")
            return None
    
    def get_activities(self, location, preferences=None, weather=None, time_of_day=None, budget=None):
        """
        Generiert Freizeitaktivitätsempfehlungen basierend auf Ort und Präferenzen
        """
        # Systemprompt, der die Rolle des KI-Agenten definiert
        system_prompt = """
        Du bist ein hilfreicher KI-Assistent, der Freizeitaktivitäten in der angegebenen Gegend empfiehlt.
        Gib fünf konkrete Empfehlungen basierend auf den angegebenen Parametern.
        Strukturiere deine Antwort als JSON mit folgenden Feldern für jede Aktivität:
        - name: Name der Aktivität
        - description: Kurze Beschreibung
        - location: Wo die Aktivität stattfindet
        - category: Kategorie (z.B. Sport, Kultur, Gastronomie)
        - cost_level: Preiskategorie (€, €€, €€€)
        - best_time: Beste Tageszeit
        - weather_suitable: Bei welchem Wetter geeignet
        - family_friendly: Boolean, ob familienfreundlich
        
        Die gesamte Antwort MUSS ein valides JSON-Objekt sein mit dem Format:
        {"activities": [Liste der Aktivitäten als JSON-Objekte]}
        """
        
        # Anfrage mit den vom Benutzer angegebenen Parametern zusammenstellen
        user_query = f"Empfehle mir Freizeitaktivitäten in {location}."
        
        if preferences:
            user_query += f" Meine Interessen sind: {preferences}."
        if weather:
            user_query += f" Das aktuelle Wetter ist: {weather}."
        if time_of_day:
            user_query += f" Tageszeit: {time_of_day}."
        if budget:
            user_query += f" Mein Budget ist: {budget}."
            
        try:
            # Neue API-Version mit Client-Instanz verwenden
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ],
                response_format={"type": "json_object"}
            )
            
            # Antwort parsen
            content = response.choices[0].message.content
            
            # Versuchen, das JSON zu parsen
            try:
                result = json.loads(content)
                return result
            except json.JSONDecodeError:
                return {"error": "Konnte kein valides JSON aus der Antwort extrahieren", "raw_response": content}
                
        except Exception as e:
            print(f"Fehler bei der OpenAI API-Anfrage: {e}")
            
            # Falls response_format nicht unterstützt wird
            if "response_format" in str(e):
                try:
                    response = client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_query + " Antworte NUR im JSON-Format."}
                        ]
                    )
                    content = response.choices[0].message.content
                    try:
                        result = json.loads(content)
                        return result
                    except json.JSONDecodeError:
                        return {"error": "Konnte kein valides JSON aus der Antwort extrahieren", "raw_response": content}
                except Exception as inner_e:
                    return {"error": str(inner_e)}
            
            return {"error": str(e)}
    
    def filter_recommendations(self, recommendations, filters):
        """
        Filtert Empfehlungen nach bestimmten Kriterien
        """
        filtered = recommendations.copy()
        
        if "activities" not in filtered:
            return filtered
            
        if "category" in filters:
            filtered["activities"] = [a for a in filtered["activities"] if a["category"].lower() == filters["category"].lower()]
            
        if "max_cost" in filters:
            cost_levels = {"€": 1, "€€": 2, "€€€": 3}
            max_cost = cost_levels.get(filters["max_cost"], 3)
            filtered["activities"] = [a for a in filtered["activities"] 
                                     if cost_levels.get(a["cost_level"], 0) <= max_cost]
            
        if "family_friendly" in filters and filters["family_friendly"]:
            filtered["activities"] = [a for a in filtered["activities"] if a.get("family_friendly", False)]
            
        return filtered

# Flask-App initialisieren
app = Flask(__name__)
agent = FreizeitaktivitätenAgent()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_activities', methods=['POST'])
def activities():
    # Formular-Daten extrahieren
    data = request.form
    location = data.get('location', '')
    preferences = data.get('preferences', '')
    weather = data.get('weather', '')
    time_of_day = data.get('time_of_day', '')
    budget = data.get('budget', '')
    
    # Leere Eingaben als None setzen
    if not preferences:
        preferences = None
    if not weather:
        weather = None
    if not time_of_day:
        time_of_day = None
    if not budget:
        budget = None
    
    # Aktivitäten vom Agent abrufen
    recommendations = agent.get_activities(
        location=location,
        preferences=preferences,
        weather=weather,
        time_of_day=time_of_day,
        budget=budget
    )
    
    # Filteroptionen verarbeiten
    filters = {}
    if data.get('filter_category'):
        filters['category'] = data.get('filter_category')
    if data.get('filter_max_cost'):
        filters['max_cost'] = data.get('filter_max_cost')
    if data.get('filter_family_friendly') == 'on':
        filters['family_friendly'] = True
    
    # Empfehlungen filtern, wenn Filter angegeben wurden
    if filters:
        recommendations = agent.filter_recommendations(recommendations, filters)
    
    # Überprüfen, ob Fehler aufgetreten sind
    if "error" in recommendations:
        return render_template('results.html', 
                              error=recommendations["error"], 
                              raw_response=recommendations.get("raw_response", ""),
                              location=location)
    
    # Ergebnisse rendern
    return render_template('results.html', 
                          recommendations=recommendations,
                          location=location)

@app.route('/api/activities', methods=['POST'])
def api_activities():
    # API-Endpunkt für AJAX-Anfragen
    data = request.get_json()
    location = data.get('location', '')
    preferences = data.get('preferences', '')
    weather = data.get('weather', '')
    time_of_day = data.get('time_of_day', '')
    budget = data.get('budget', '')
    
    # Leere Eingaben als None setzen
    if not preferences:
        preferences = None
    if not weather:
        weather = None
    if not time_of_day:
        time_of_day = None
    if not budget:
        budget = None
    
    # Aktivitäten vom Agent abrufen
    recommendations = agent.get_activities(
        location=location,
        preferences=preferences,
        weather=weather,
        time_of_day=time_of_day,
        budget=budget
    )
    
    # Ergebnisse als JSON zurückgeben
    return jsonify(recommendations)

if __name__ == "__main__":
    # Module importieren
    import requests
    
    # Prüfen, ob wir in IPython/Jupyter ausgeführt werden
    try:
        __IPYTHON__
        print("In IPython/Jupyter: Bitte führe die Anwendung in einer normalen Python-Umgebung aus!")
    except NameError:
        # Normale Python-Umgebung, starte die App
        app.run(debug=True)