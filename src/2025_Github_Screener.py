import os
import sys
import base64
import re
from collections import Counter
from datetime import datetime

# Third-party libraries
import yaml
from github import Github, GithubException
from tqdm import tqdm
import matplotlib.pyplot as plt
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

# ===================================================================
# SETUP & CONFIGURATION
# ===================================================================

# Ermittelt den absoluten Pfad zum Verzeichnis, in dem das Skript liegt (also .../src)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Geht eine Ebene nach oben zum Projekt-Hauptverzeichnis
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# --- Pfade zu Eingabedateien und Vorlagen ---
CONFIG_FILE = os.path.join(PROJECT_ROOT, 'static', 'config.yml')
STOP_WORDS_FILE = os.path.join(PROJECT_ROOT, 'static', 'stopwords.txt')
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, 'static','templates')

# --- Pfad zum Ausgabe-Verzeichnis ---
BASE_OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'output')

# Template Settings
BASE_TEMPLATE = 'base_template_2.html'
CSS_THEME = 'mordern_white_2.css' 

# ===================================================================
# NEU: Funktion zur Überprüfung der Pfade
# ===================================================================

def clear_screen():
    """Löscht den Inhalt des Terminals, plattformunabhängig."""
    # Für Windows
    if os.name == 'nt':
        _ = os.system('cls')
    # Für Mac und Linux (os.name ist 'posix')
    else:
        _ = os.system('clear')

def check_and_prepare_paths():
    """
    Überprüft, ob alle benötigten Dateien und Verzeichnisse existieren.
    Erstellt das Ausgabe-Verzeichnis, falls es nicht existiert.
    Beendet das Skript mit einer Fehlermeldung, wenn etwas fehlt.
    """
    print("🔎 Überprüfe Konfiguration und Pfade...")
    
    paths_to_check = {
        "Konfigurationsdatei": CONFIG_FILE,
        "Stoppwörter-Datei": STOP_WORDS_FILE,
        "Template-Verzeichnis": TEMPLATE_DIR
    }
    
    missing_paths = []
    for description, path in paths_to_check.items():
        if not os.path.exists(path):
            missing_paths.append(f"  - {description} nicht gefunden unter: {path}")

    # Wenn Pfade fehlen, gib alle auf einmal aus und beende das Programm
    if missing_paths:
        print("\n❌ Fehler: Folgende benötigte Dateien oder Verzeichnisse fehlen:")
        for error in missing_paths:
            print(error)
        sys.exit("\nProgramm wird aufgrund fehlender Konfiguration beendet.")

    # Erstelle das Ausgabe-Verzeichnis, falls es nicht existiert
    os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)
    
    print("✅ Alle Pfade sind korrekt und das Ausgabe-Verzeichnis ist bereit.\n")

# ===================================================================
# HELPER FUNCTIONS (Analysis & PDF Generation)
# ===================================================================

def load_stop_words(filename):
    """Lädt Stoppwörter aus der angegebenen Datei."""
    if not os.path.exists(filename):
        print(f"⚠️  Warnung: Stoppwörter-Datei '{filename}' nicht gefunden. Fahre ohne Stoppwörter fort.")
        return set()
    
    with open(filename, 'r', encoding='utf-8') as f:
        words = {line.strip().lower() for line in f if line.strip() and not line.startswith('#')}
    return words

def load_or_create_config():
    """Lädt die Konfiguration oder startet die interaktive Einrichtung."""
    config = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            config = yaml.safe_load(f) or {}

    if not all(config.get(key) for key in ['GITHUB_USER', 'ACCESS_TOKEN']):
        print("Konfiguration nicht gefunden oder unvollständig. Bitte jetzt einrichten.")
        config['GITHUB_USER'] = input("Gib deinen GitHub-Benutzernamen ein: ")
        config['ACCESS_TOKEN'] = input("Gib dein GitHub Personal Access Token ein: ")
        with open(CONFIG_FILE, 'w') as f:
            yaml.dump(config, f)
        print(f"✅ Konfiguration wurde in '{CONFIG_FILE}' gespeichert.\n")
    return config

def process_and_count_words(text, counter, stop_words):
    """Extrahiert und zählt Wörter aus einem Text."""
    if not text:
        return
    words = re.findall(r'[a-z0-9]+', text.lower())
    for word in words:
        if word not in stop_words and len(word) >= 3:
            counter[word] += 1

# GEÄNDERT: Die Grafik wird jetzt im `output` Ordner gespeichert
def create_language_pie_chart(language_stats):
    """Erstellt ein Kuchendiagramm der Sprachen und speichert es als PNG im Output-Ordner."""
    output_path = os.path.join(BASE_OUTPUT_DIR, 'languages.png')
    # ... (Rest der Funktion bleibt gleich, verwendet aber den neuen output_path)
    if not language_stats:
        print("Keine Sprachdaten für Diagramm gefunden.")
        return None
    
    sorted_langs = dict(sorted(language_stats.items(), key=lambda item: item[1], reverse=True))
    top_n = 6
    top_langs = list(sorted_langs.keys())[:top_n]
    top_values = [sorted_langs[lang] for lang in top_langs]
    
    if len(sorted_langs) > top_n:
        other_value = sum(list(sorted_langs.values())[top_n:])
        top_langs.append('Andere')
        top_values.append(other_value)

    colors = ['#14F195', '#9945FF', '#03A9F4', '#FFC107', '#E91E63', '#4CAF50', '#795548']
    
    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(aspect="equal"))
    wedges, texts, autotexts = ax.pie(top_values, autopct='%1.1f%%', startangle=140, colors=colors[:len(top_values)], pctdistance=0.85, wedgeprops=dict(width=0.4, edgecolor='w'))
    
    plt.setp(autotexts, size=10, weight="bold", color="white")
    
    legend = ax.legend(wedges, top_langs, title="Sprachen", loc="center", bbox_to_anchor=(0.5, 0.5), prop={'size': 12}, title_fontproperties={'size': 14, 'weight': 'bold'})
    
    plt.setp(legend.get_texts(), color='black')
    plt.setp(legend.get_title(), color='black')

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, transparent=True)
    plt.close()
    return output_path


# Ersetze die komplette Funktion
def generate_report(data, base_template_file, css_file):
    """Erstellt den finalen Report als HTML und PDF."""
    print("\n---")
    print("🚀 Report wird erstellt...")

    # Grafik für Sprachen-Chart erstellen und Pfad für Template speichern
    chart_path = create_language_pie_chart(data['language_stats'])
    if chart_path:
        data['language_chart_path'] = os.path.basename(chart_path)
    
    # NEU: Den relativen Pfad zur CSS-Datei für die HTML-Datei erstellen
    # Von 'output/report.html' zu 'static/css/theme.css'
    css_path_for_html = f'../static/css/{css_file}'
    data['css_file_path'] = css_path_for_html

    try:
        env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
        # GEÄNDERT: Lade das universelle Grundgerüst
        template = env.get_template(base_template_file)
    except Exception as e:
        print(f"❌ Fehler: Das Template '{base_template_file}' im Ordner '{TEMPLATE_DIR}' konnte nicht geladen werden. ({e})")
        return
        
    # Die Daten, inkl. dem CSS-Pfad, werden in das Template eingefügt
    html_out = template.render(data)
    
    # Dateinamen definieren (im Output-Verzeichnis)
    base_filename = os.path.join(BASE_OUTPUT_DIR, f"GitHub_Report_{data['GITHUB_USER']}")
    html_filename = f"{base_filename}.html"
    pdf_filename = f"{base_filename}.pdf"

    # HTML-Datei speichern
    with open(html_filename, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"✅ HTML-Report '{html_filename}' wurde erstellt!")

    # PDF erstellen (base_url zeigt auf den Output-Ordner, um das Bild zu finden)
    HTML(string=html_out, base_url=BASE_OUTPUT_DIR).write_pdf(pdf_filename)
    print(f"✅ PDF-Report '{pdf_filename}' wurde erstellt!")
    print("---")


# ===================================================================
# MAIN FUNCTION
# ===================================================================

def main():
    """Hauptfunktion des Skripts."""
    # 1. Pfade prüfen und vorbereiten
    clear_screen()
    check_and_prepare_paths()
    
    # 2. Konfiguration laden
    config = load_or_create_config()
    ACCESS_TOKEN = os.environ.get('GITHUB_TOKEN') or config['ACCESS_TOKEN']
    GITHUB_USER = config['GITHUB_USER']
    
    # 3. Stoppwörter laden (einmalig)
    stop_words = load_stop_words(STOP_WORDS_FILE)

    print(f"Initialisiere Analyse für Benutzer: {GITHUB_USER}...")
    g = Github(ACCESS_TOKEN)

    try:
        user = g.get_user(GITHUB_USER)
    except GithubException as e:
        # ... (Fehlerbehandlung bleibt gleich) ...
        sys.exit()

    # --- Datensammlung ---
    total_lines_of_code, total_lines_of_docs, total_commits = 0, 0, 0
    language_stats, keyword_counts = Counter(), Counter()
    repo_names, repo_data_list = [], []
    first_activity_date, last_activity_date = None, None

    print("Fetching all public repositories...")
    repos = list(user.get_repos())
    repo_count = len(repos)
    print(f"Starting analysis of {repo_count} repositories...")
    print("---")

    for repo in tqdm(repos, desc="Analyzing Repositories"):
        repo_names.append(repo.full_name)
        if first_activity_date is None or repo.created_at < first_activity_date: first_activity_date = repo.created_at
        if last_activity_date is None or repo.pushed_at > last_activity_date: last_activity_date = repo.pushed_at
        
        process_and_count_words(re.sub(r'[-_]', ' ', repo.name), keyword_counts, stop_words)

        try:
            for lang, byte_count in repo.get_languages().items():
                language_stats[lang] += byte_count
            
            try:
                readme = repo.get_readme()
                readme_content = base64.b64decode(readme.content).decode('utf-8', errors='ignore')
                total_lines_of_docs += len(readme_content.splitlines())
                process_and_count_words(readme_content, keyword_counts, stop_words)
            except GithubException: pass

            tree = repo.get_git_tree(repo.default_branch, recursive=True).tree
            for element in tree:
                if element.type == 'blob' and 0 < element.size < 1_000_000:
                    try:
                        blob_content = repo.get_git_blob(element.sha).content
                        decoded_content = base64.b64decode(blob_content).decode('utf-8', errors='ignore')
                        total_lines_of_code += len(decoded_content.splitlines())
                        
                        process_and_count_words(readme_content, keyword_counts, stop_words)
                    except Exception: pass
            
            commit_stats = repo.get_stats_commit_activity()
            if commit_stats:
                total_commits += sum(stat.total for stat in commit_stats)
            
            repo_data_list.append({
                "name": repo.name, 
                "url": repo.html_url,
                "description": repo.description or "Keine Beschreibung vorhanden.",
                "pushed_at": repo.pushed_at
            })

        except GithubException as e:
            print(f"\nCould not fully analyze repository '{repo.full_name}': {e.data.get('message', 'API Error')}")
    
    print("\n---")
    print("✅ Analysis complete!")
    
    # --- Report-Erstellung ---
    # Daten für das Template bündeln
    report_data = {
        "GITHUB_USER": GITHUB_USER,
        "USER_NAME": user.name or GITHUB_USER,
        "USER_URL": user.html_url,
        "AVATAR_URL": user.avatar_url,
        "REPO_COUNT": repo_count,
        "TOTAL_COMMITS": f"{total_commits:,}",
        "TOTAL_LOC": f"{total_lines_of_code:,}",
        "FIRST_ACTIVITY": first_activity_date.strftime('%d. %B %Y') if first_activity_date else 'N/A',
        "LAST_ACTIVITY": last_activity_date.strftime('%d. %B %Y') if last_activity_date else 'N/A',
        "GENERATION_DATE": datetime.now().strftime('%d. %B %Y'),
        "language_stats": language_stats,
        "top_keywords": keyword_counts.most_common(20), # Top 20 Keywords als Liste übergeben
        "repo_list": sorted(repo_data_list, key=lambda x: x['pushed_at'], reverse=True)[:5]
    }
    
    generate_report(report_data, base_template_file=BASE_TEMPLATE, css_file=CSS_THEME)



if __name__ == '__main__':
    main()