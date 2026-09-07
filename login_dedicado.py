#!/usr/bin/env python3
"""Login interativo ÚNICO na conta dedicada, num perfil Chrome novo e separado.
Usa o Chrome real (channel=chrome) num user-data-dir dedicado (nao o perfil pessoal),
com atenuacao da deteccao de automacao. O usuario digita as credenciais na janela;
o Claude NUNCA digita senha. A sessao fica gravada e dura meses."""

import json
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROFILE_DIR = str(Path(__file__).parent / "chrome-dedicado")
SESSION_COOKIES = {"SID", "SSID", "LSID", "__Secure-1PSID", "__Secure-3PSID"}


def emit(d):
    print(json.dumps(d, ensure_ascii=False), flush=True)


def session_cookies(cookies):
    """Nomes dos cookies de sessao Google presentes na lista."""
    return sorted(
        {c["name"] for c in cookies
         if c["name"] in SESSION_COOKIES and "google.com" in c.get("domain", "")}
    )


def cookies_em_disco():
    """Confere o que o Chrome realmente gravou no perfil (sobrevive ao proximo run)."""
    db = Path(PROFILE_DIR) / "Default" / "Cookies"
    if not db.exists():
        return []
    tmp = Path(tempfile.gettempdir()) / "reembolso_cookies_check.db"
    try:
        shutil.copy(db, tmp)
        con = sqlite3.connect(tmp)
        nomes = [r[0] for r in con.execute(
            "select name from cookies where host_key like '%google.com'"
        )]
        con.close()
        return sorted(set(nomes) & SESSION_COOKIES)
    except Exception:
        return []
    finally:
        tmp.unlink(missing_ok=True)


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch_persistent_context(
            PROFILE_DIR,
            channel="chrome",
            headless=False,
            ignore_default_args=["--enable-automation"],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        page = b.pages[0] if b.pages else b.new_page()
        page.goto("https://accounts.google.com/", timeout=60000)
        emit({"status": "LOGIN_ABERTO",
              "msg": "Faca login nesta janela. Marque 'continuar conectado' se aparecer. "
                     "O script detecta a sessao sozinho; pode fechar o browser quando ele avisar."})

        # Espera a sessao aparecer nos cookies — fechar a janela nao prova login.
        logado = False
        for _ in range(300):  # ate 10 min
            try:
                if session_cookies(b.cookies()):
                    logado = True
                    emit({"status": "SESSAO_DETECTADA",
                          "msg": "Login confirmado. Pode fechar o browser."})
                    break
                if page.is_closed():
                    break
            except Exception:
                pass  # navegacao em curso
            time.sleep(2)

        # Da tempo de o Chrome gravar os cookies em disco antes de encerrar.
        if logado:
            for _ in range(30):
                if page.is_closed():
                    break
                time.sleep(2)

        try:
            b.close()
        except Exception:
            pass

    if not logado:
        emit({"status": "LOGIN_FALHOU",
              "msg": f"Nenhum cookie de sessao Google gravado em {PROFILE_DIR}. "
                     "A automacao continua sem sessao."})
        return 1

    persistidos = cookies_em_disco()
    if not persistidos:
        emit({"status": "SESSAO_NAO_PERSISTIU",
              "msg": "Login funcionou na janela mas nada foi gravado no disco — "
                     "a sessao morre no proximo run."})
        return 1

    emit({"status": "LOGIN_OK", "cookies_persistidos": persistidos,
          "perfil": PROFILE_DIR})
    return 0


if __name__ == "__main__":
    sys.exit(main())
