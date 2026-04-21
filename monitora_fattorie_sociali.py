"""
Monitoraggio automatico degli elenchi regionali di agricoltura sociale
======================================================================
Versione definitiva - tutte le 14 regioni

ISTRUZIONI PER L'USO MANUALE (sul tuo PC):
1. Installa le dipendenze (una sola volta):
   pip install requests beautifulsoup4

2. Eseguilo con:
   python monitora_fattorie_sociali.py

ISTRUZIONI PER GITHUB ACTIONS:
- Carica questo file nella cartella principale del repository
- Carica monitora.yml in .github/workflows/
- Girerà ogni lunedì alle 8:00 automaticamente

CONFIGURAZIONE EMAIL:
- Funziona con Gmail
- Vai su myaccount.google.com → Sicurezza → Password per le app
- Genera una password per "Posta" e inseriscila in EMAIL_PASSWORD
"""

import hashlib
import json
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ============================================================
# CONFIGURAZIONE EMAIL (opzionale ma consigliata)
# ============================================================
EMAIL_MITTENTE = ""        # es. "tuaemail@gmail.com"
EMAIL_PASSWORD = ""        # password per le app Gmail
EMAIL_DESTINATARIO = ""    # dove ricevere le notifiche
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# ============================================================
# FILE DI STATO
# ============================================================
FILE_STATO = "stato_monitoraggio.json"

# ============================================================
# CONFIGURAZIONE REGIONI
# ============================================================
# tipo:
#   "file"   → scarica e confronta il file all'URL indicato
#   "pagina" → scarica la pagina, trova il link al PDF tramite
#              il filtro, scarica e confronta quel PDF
#   "html"   → scarica la pagina e confronta il contenuto HTML
#
# filtro_testo: True  → cerca la parola nel TESTO VISIBILE del link
#               False → cerca la parola nell'URL (href) del link
# ============================================================
REGIONI = {
    "Abruzzo": {
        "tipo": "manuale",
        "url_pagina": "https://www2.regione.abruzzo.it/content/fattorie-sociali",
        "nota": "Albo Regionale Fattorie Sociali — il server blocca le richieste automatiche, verifica manualmente",
    },
    "Calabria": {
        "tipo": "file",
        "url_file": "https://www.regione.calabria.it/website/portalmedia/userfiles/file/fattori_sociali%2009_20.pdf",
        "nota": "Elenco Fattorie Sociali",
    },
    "Campania": {
        "tipo": "pagina",
        "url_pagina": "https://www.regione.campania.it/regione/it/tematiche/agricoltura-sociale-in-campania-fattorie-sociali",
        "filtro": "registro-fattorie-sociali",
        "filtro_testo": False,
        "nota": "Registro Fattorie Sociali",
    },
    "Emilia-Romagna": {
        "tipo": "pagina",
        "url_pagina": "https://agricoltura.regione.emilia-romagna.it/agriturismo-e-multifunzionalita/agricoltura-sociale",
        "filtro": "elenco-fattorie-sociali",
        "filtro_testo": False,
        "nota": "Elenco Fattorie Sociali",
    },
    "Friuli-Venezia Giulia": {
        "tipo": "file",
        "url_file": "https://www.ersa.fvg.it/export/sites/ersa/consumatore/fattorie/Tipologie/Allegati/Elenco-Regionale-Fattorie-Sociali-28_04_2025.pdf",
        "nota": "Elenco Regionale Fattorie Sociali",
    },
    "Liguria": {
        "tipo": "file",
        "url_file": "https://www.agriligurianet.it/en/impresa/politiche-di-sviluppo/agricoltura-sociale/item/download/9989_6436dadd5419fd3b7beb80a49a41c267.html",
        "nota": "Registro Aziende Agricole Sociali",
    },
    "Lombardia": {
        "tipo": "file",
        "url_file": "https://www.regione.lombardia.it/content/dam/rl/canali-tematici-servizi/10-agricoltura/13-fattorie-didattiche-e-sociali/ser-fattorie-sociali-della-lombardia-agr/allegati/Allegati%20(fattorie%20sociali).zip",
        "nota": "Elenco Fattorie Sociali (ZIP)",
    },
    "Marche": {
        "tipo": "manuale",
        "url_pagina": "https://www.regione.marche.it/Regione-Utile/Agricoltura-Sviluppo-Rurale-e-Pesca/Agricoltura-sociale",
        "nota": "Elenco EROAS — il server blocca le richieste automatiche, verifica manualmente",
    },
    "Piemonte": {
        "tipo": "pagina",
        "url_pagina": "https://www.regione.piemonte.it/web/temi/agricoltura/ricerca-innovazione-multifunzionalita/elenco-regionale-delle-fattorie-sociali-piemonte",
        "filtro": "fattorie sociali",
        "filtro_testo": True,  # cerca nel testo del link perché l'URL contiene solo il numero dell'atto
        "nota": "Elenco Regionale Fattorie Sociali",
    },
    "Puglia": {
        "tipo": "pagina",
        "url_pagina": "https://filiereagroalimentari.regione.puglia.it/agricoltura-sociale",
        "filtro": "Fattorie+Sociali",
        "filtro_testo": False,
        "nota": "Elenco Regionale Fattorie Sociali",
    },
    "Sardegna": {
        "tipo": "html",
        "url_pagina": "https://domino.agenzialaore.it/servizionline/SUAP.nsf/xpSezFattorieSociali.xsp",
        "nota": "Elenco Fattorie Sociali (tabella online)",
    },
    "Sicilia": {
        "tipo": "pagina",
        "url_pagina": "https://www.regione.sicilia.it/istituzioni/regione/strutture-regionali/assessorato-agricoltura-sviluppo-rurale-pesca-mediterranea/dipartimento-agricoltura/agricoltura-sociale-sicilia",
        "filtro": "elenco_regionale_operatori_agricoltura_sociale",
        "filtro_testo": False,
        "nota": "Elenco Regionale Operatori Agricoltura Sociale",
    },
    "Valle d'Aosta": {
        "tipo": "pagina",
        "url_pagina": "https://www.regione.vda.it/agricoltura/multifunzionalita_in_agricoltura/Agricoltura_sociale/el-regionale-fatt_i.aspx",
        "filtro": "fattorie sociali",
        "filtro_testo": True,  # cerca nel testo del link
        "nota": "Elenco Regionale Fattorie Sociali",
    },
    "Veneto": {
        "tipo": "file",
        "url_file": "https://sharing.regione.veneto.it/index.php/s/dCQjdBxmND74Q9A/download",
        "nota": "Elenco Regionale Fattorie Sociali",
    },
}


# ============================================================
# FUNZIONI
# ============================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def calcola_hash(contenuto: bytes) -> str:
    return hashlib.sha256(contenuto).hexdigest()


def scarica(url: str) -> tuple:
    """Scarica il contenuto di un URL. Restituisce (contenuto, errore)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.content, ""
    except requests.exceptions.HTTPError as e:
        return None, f"Errore HTTP {e.response.status_code}"
    except requests.exceptions.ConnectionError:
        return None, "Errore di connessione"
    except requests.exceptions.Timeout:
        return None, "Timeout"
    except Exception as e:
        return None, str(e)


def trova_link_in_pagina(html: bytes, url_base: str, filtro: str, filtro_testo: bool) -> tuple:
    """
    Cerca in una pagina HTML un link che soddisfa il filtro.
    Se filtro_testo=True cerca nel testo visibile del link,
    altrimenti cerca nell'href.
    Restituisce (url_trovato, errore).
    """
    soup = BeautifulSoup(html, "html.parser")
    filtro_lower = filtro.lower()

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        testo = link.get_text(strip=True).lower()

        if filtro_testo:
            if filtro_lower in testo:
                return urljoin(url_base, href), ""
        else:
            if filtro_lower in href.lower():
                return urljoin(url_base, href), ""

    return None, f"Nessun link trovato con filtro '{filtro}'"


def controlla_regione(nome: str, config: dict, stato: dict) -> dict:
    """Controlla una singola regione e aggiorna lo stato."""
    tipo = config["tipo"]
    risultato = {
        "regione": nome,
        "nota": config["nota"],
        "aggiornato": False,
        "prima_rilevazione": False,
        "errore": "",
        "url": "",
    }

    stato_regione = stato.get(nome, {})

    # --- TIPO MANUALE ---
    # Il server blocca le richieste automatiche.
    # Lo script segnala solo un promemoria di verifica manuale.
    if tipo == "manuale":
        risultato["errore"] = ""
        risultato["manuale"] = True
        risultato["url"] = config.get("url_pagina", "")
        return risultato

    # --- TIPO FILE ---
    if tipo == "file":
        url = config["url_file"]
        risultato["url"] = url
        contenuto, errore = scarica(url)
        if errore:
            risultato["errore"] = errore
            return risultato

    # --- TIPO PAGINA ---
    elif tipo == "pagina":
        url_pagina = config["url_pagina"]
        filtro = config["filtro"]
        filtro_testo = config.get("filtro_testo", False)

        html, errore = scarica(url_pagina)
        if errore:
            risultato["errore"] = f"Errore scaricando la pagina: {errore}"
            return risultato

        url_file, errore = trova_link_in_pagina(html, url_pagina, filtro, filtro_testo)
        if errore:
            risultato["errore"] = errore
            return risultato

        risultato["url"] = url_file

        # Se l'URL del PDF è cambiato, è già un aggiornamento
        url_precedente = stato_regione.get("url_file", "")
        if url_precedente and url_file != url_precedente:
            risultato["aggiornato"] = True
            stato[nome] = stato_regione
            stato[nome]["url_file"] = url_file
            stato[nome]["ultimo_controllo"] = datetime.now().isoformat()
            stato[nome]["ultima_modifica"] = datetime.now().isoformat()
            return risultato

        stato_regione["url_file"] = url_file

        contenuto, errore = scarica(url_file)
        if errore:
            risultato["errore"] = f"Errore scaricando il PDF: {errore}"
            return risultato

    # --- TIPO HTML ---
    # Estrae solo il testo delle tabelle, ignorando header/footer
    # e elementi dinamici (token di sessione, timestamp) che
    # causerebbero falsi positivi ad ogni esecuzione
    elif tipo == "html":
        url_pagina = config["url_pagina"]
        risultato["url"] = url_pagina
        html, errore = scarica(url_pagina)
        if errore:
            risultato["errore"] = errore
            return risultato
        soup = BeautifulSoup(html, "html.parser")
        tabelle = soup.find_all("table")
        if tabelle:
            testo = " ".join(t.get_text(separator=" ", strip=True) for t in tabelle)
        else:
            testo = soup.get_text(separator=" ", strip=True)
        contenuto = testo.encode("utf-8")

    # Confronto hash
    hash_attuale = calcola_hash(contenuto)
    hash_precedente = stato_regione.get("hash", "")

    if hash_precedente == "":
        risultato["prima_rilevazione"] = True
    elif hash_attuale != hash_precedente:
        risultato["aggiornato"] = True

    stato_regione["hash"] = hash_attuale
    stato_regione["ultimo_controllo"] = datetime.now().isoformat()
    if risultato["aggiornato"]:
        stato_regione["ultima_modifica"] = datetime.now().isoformat()

    stato[nome] = stato_regione
    return risultato


def carica_stato() -> dict:
    if Path(FILE_STATO).exists():
        with open(FILE_STATO, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def salva_stato(stato: dict):
    with open(FILE_STATO, "w", encoding="utf-8") as f:
        json.dump(stato, f, indent=2, ensure_ascii=False)


def invia_email(aggiornamenti: list):
    if not EMAIL_MITTENTE or not EMAIL_DESTINATARIO:
        print("  (Notifica email non configurata, salto invio)")
        return

    oggetto = f"🌱 Aggiornamento fattorie sociali - {datetime.now().strftime('%d/%m/%Y')}"
    corpo = (
        f"Rilevati {len(aggiornamenti)} aggiornamento/i "
        f"in data {datetime.now().strftime('%d/%m/%Y alle %H:%M')}.\n\n"
        "REGIONI AGGIORNATE:\n"
    )
    for a in aggiornamenti:
        corpo += f"\n  📍 {a['regione']} — {a['nota']}\n     {a['url']}\n"
    corpo += "\nRicordati di scaricare il nuovo file, aggiornare il CSV e la mappa QGIS.\n"

    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_MITTENTE
        msg["To"] = EMAIL_DESTINATARIO
        msg["Subject"] = oggetto
        msg.attach(MIMEText(corpo, "plain", "utf-8"))
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_MITTENTE, EMAIL_PASSWORD)
            server.send_message(msg)
        print(f"  ✓ Email inviata a {EMAIL_DESTINATARIO}")
    except Exception as e:
        print(f"  ✗ Errore invio email: {e}")


# ============================================================
# MAIN
# ============================================================
def main():
    print("=== Monitoraggio Elenchi Fattorie Sociali ===")
    print(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")

    stato = carica_stato()
    aggiornamenti = []
    errori = []
    manuali = []

    for nome, config in REGIONI.items():
        print(f"Controllo {nome}...", end=" ", flush=True)
        risultato = controlla_regione(nome, config, stato)

        if risultato.get("manuale"):
            print("⚠️  verifica manuale richiesta")
            manuali.append(risultato)
        elif risultato["errore"]:
            print(f"✗ ERRORE: {risultato['errore']}")
            errori.append(risultato)
        elif risultato["prima_rilevazione"]:
            print("✓ Prima rilevazione (hash salvato)")
        elif risultato["aggiornato"]:
            print("🔔 AGGIORNATO!")
            aggiornamenti.append(risultato)
        else:
            print("✓ Nessuna modifica")

    salva_stato(stato)

    print(f"\n--- RIEPILOGO ---")
    print(f"Regioni controllate: {len(REGIONI)}")
    print(f"Aggiornamenti rilevati: {len(aggiornamenti)}")
    print(f"Verifica manuale richiesta: {len(manuali)}")
    print(f"Errori: {len(errori)}")

    if aggiornamenti:
        print("\nREGIONI AGGIORNATE:")
        for a in aggiornamenti:
            print(f"  🔔 {a['regione']} — {a['url']}")
        invia_email(aggiornamenti)

    if manuali:
        print("\nREGIONI DA VERIFICARE MANUALMENTE:")
        for m in manuali:
            print(f"  ⚠️  {m['regione']} — {m['url']}")
            print(f"      {m['nota']}")

    if errori:
        print("\nERRORI (da verificare manualmente):")
        for e in errori:
            print(f"  ✗ {e['regione']}: {e['errore']}")

    # Codice uscita 1 se ci sono aggiornamenti (utile per GitHub Actions)
    sys.exit(1 if aggiornamenti else 0)


if __name__ == "__main__":
    main()
