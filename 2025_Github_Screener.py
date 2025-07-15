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
from wordcloud import WordCloud
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

# ===================================================================
# CONFIGURATION & CONSTANTS
# ===================================================================

CONFIG_FILE = 'config.yml'
STOP_WORDS = {
    'https', 'http', 'href', 'com', 'github', 'bash', 'www', 'org', 'de', 'a', 'about', 'an', 'and', 'are', 
    'as', 'at', 'be', 'by', 'for', 'from', 'how', 'i', 'in', 'is', 'it', 'of', 'on', 'or', 'that', 'the', 
    'this', 'to', 'was', 'what', 'when', 'where', 'who', 'will', 'with', 'he', 'she', 'they', 'we', 'me', 
    'you', 'my', 'your', 'our', 'do', 'not', 'have', 'were', 'if', 'then', 'else', 'while', 'code', 'file', 
    'files', 'gem', 'build', 'setup', 'config', 'run', 'installation', 'usage', 'license', 'mit', 'gpl', 
    'data', 'lib', 'docs', 'new', 'get', 'use', 'using', 'via', 'from', 'these', 'those', 'example', 
    'examples', 'please', 'feel', 'free', 'more', 'also', 'just', 'like', 'some', 'any', 'all', 'its', 
    'can', 'readme', 'md', 'out', 'there', 'because', 'been', 'through', 'into', 'only', 'repo', 
    'repository', 'project', 'projects', 'app', 'application', 'service', 'api', 'client', 'server', 
    'test', 'tests', 'feature', 'features', 'version', 'update', 'release', 'change', 'fix', 'add', 
    'remove', 'refactor', 'style', 'chore', 'ci', 'performance', 'security', 'support', 'help', 
    'contact', 'information', 'details', 'note', 'important'
}

# ===================================================================
# HELPER FUNCTIONS (Analysis & PDF Generation)
# ===================================================================

def load_or_create_config():
    """Lädt die Konfiguration oder startet die interaktive Einrichtung."""
    config = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            config = yaml.safe_load(f) or {}

    if not all(config.get(key) and config[key] not in ('USER_NAME', 'YOUR_TOKEN') for key in ['GITHUB_USER', 'ACCESS_TOKEN']):
        print("Konfiguration nicht gefunden oder unvollständig. Bitte jetzt einrichten.")
        config['GITHUB_USER'] = input("Gib deinen GitHub-Benutzernamen ein: ")
        config['ACCESS_TOKEN'] = input("Gib dein GitHub Personal Access Token ein: ")
        with open(CONFIG_FILE, 'w') as f:
            yaml.dump(config, f)
        print(f"✅ Konfiguration wurde in '{CONFIG_FILE}' gespeichert.\n")
    return config

def process_and_count_words(text, counter):
    """Extrahiert und zählt Wörter aus einem Text."""
    if not text:
        return
    words = re.findall(r'[a-z0-9]+', text.lower())
    for word in words:
        if word not in STOP_WORDS and len(word) >= 3:
            counter[word] += 1

def create_language_chart(language_stats, output_path='languages.png'):
    """Erstellt ein Balkendiagramm der Sprachen und speichert es als PNG."""
    if not language_stats:
        print("Keine Sprachdaten für Diagramm gefunden.")
        return False
    
    sorted_langs = dict(sorted(language_stats.items(), key=lambda item: item[1], reverse=True))
    total_bytes = sum(sorted_langs.values())
    
    top_langs = list(sorted_langs.keys())[:7]
    top_percentages = [(sorted_langs[lang] / total_bytes) * 100 for lang in top_langs]
    
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.barh(top_langs, top_percentages, color='#0366d6')
    
    ax.invert_yaxis()
    ax.set_xlabel('Nutzung in %', fontsize=10)
    ax.set_title('Top Programmiersprachen', fontsize=14, weight='bold')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.tick_params(axis='y', length=0)
    
    for bar in bars:
        width = bar.get_width()
        ax.text(width + 1, bar.get_y() + bar.get_height()/2, f'{width:.1f}%', va='center')

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, transparent=True)
    plt.close()
    return True

def create_keyword_cloud(keyword_counts, output_path='keywords.png'):
    """Erstellt eine Wortwolke der Keywords und speichert sie als PNG."""
    if not keyword_counts:
        print("Keine Keywords für Wortwolke gefunden.")
        return False

    wc = WordCloud(width=800, height=400, background_color="white", colormap="magma", max_words=40, prefer_horizontal=0.9)
    wc.generate_from_frequencies(keyword_counts)
    wc.to_file(output_path)
    return True

def generate_pdf_report(data):
    """Erstellt den finalen PDF-Report aus den gesammelten Daten."""
    print("\n---")
    print("🚀 Generating PDF report...")

    # Grafiken erstellen
    data['language_chart_path'] = 'languages.png' if create_language_chart(data['language_stats']) else None
    data['keyword_cloud_path'] = 'keywords.png' if create_keyword_cloud(data['keyword_counts']) else None
    
    # Template laden und mit Daten füllen
    try:
        env = Environment(loader=FileSystemLoader('.'))
        template = env.get_template("template.html")
    except Exception as e:
        print(f"❌ Fehler: Das Template 'template.html' konnte nicht geladen werden. Stelle sicher, dass es im selben Ordner liegt. ({e})")
        return
        
    html_out = template.render(data)
    
    # PDF erstellen
    pdf_filename = f"GitHub_Report_{data['GITHUB_USER']}.pdf"
    HTML(string=html_out, base_url='.').write_pdf(pdf_filename)
    
    print(f"✅ PDF report '{pdf_filename}' has been successfully created!")
    print("---")


# ===================================================================
# MAIN FUNCTION
# ===================================================================

def main():
    """Hauptfunktion des Skripts."""
    config = load_or_create_config()
    
    ACCESS_TOKEN = os.environ.get('GITHUB_TOKEN') or config['ACCESS_TOKEN']
    GITHUB_USER = config['GITHUB_USER']

    print(f"Initializing screener for user: {GITHUB_USER}...")
    g = Github(ACCESS_TOKEN)

    try:
        user = g.get_user(GITHUB_USER)
    except GithubException as e:
        if e.status == 404:
            print(f"Error: User '{GITHUB_USER}' not found.")
        elif e.status == 401:
            print("Error: GitHub Token is invalid or does not have the necessary permissions.")
        else:
            print(f"An unexpected error occurred: {e}")
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
        
        process_and_count_words(re.sub(r'[-_]', ' ', repo.name), keyword_counts)

        try:
            for lang, byte_count in repo.get_languages().items():
                language_stats[lang] += byte_count
            
            try:
                readme = repo.get_readme()
                readme_content = base64.b64decode(readme.content).decode('utf-8', errors='ignore')
                total_lines_of_docs += len(readme_content.splitlines())
                process_and_count_words(readme_content, keyword_counts)
            except GithubException: pass

            tree = repo.get_git_tree(repo.default_branch, recursive=True).tree
            for element in tree:
                if element.type == 'blob' and 0 < element.size < 1_000_000:
                    try:
                        blob_content = repo.get_git_blob(element.sha).content
                        decoded_content = base64.b64decode(blob_content).decode('utf-8', errors='ignore')
                        total_lines_of_code += len(decoded_content.splitlines())
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
    
    # --- Konsolenausgabe ---
    print(f"\n📊 Results for {user.name or GITHUB_USER} (@{GITHUB_USER})")
    # (Die detaillierte Konsolenausgabe kann hier bei Bedarf beibehalten oder gekürzt werden)

    # --- PDF-Erstellung ---
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
        "keyword_counts": keyword_counts,
        "repo_list": sorted(repo_data_list, key=lambda x: x['pushed_at'], reverse=True)[:5] # Top 5 nach letztem Push
    }
    
    generate_pdf_report(report_data)


if __name__ == '__main__':
    main()