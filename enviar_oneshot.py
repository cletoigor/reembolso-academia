#!/usr/bin/env python3
"""Envio do reembolso em UMA sessão só: login (se preciso) + preenche + upload + submit,
sem fechar o browser no meio (o perfil isolado perde o cookie ao reabrir)."""

import argparse
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

FORM_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLSda3D0-pMe4H6XciC6L51NzuB4TLcqwTEw35gh8tzbxCx137Q/viewform?pli=1"
)
PROFILE_DIR = str(Path(__file__).parent / "chrome-profile")

NOME = "Igor Cleto"
EMAIL = "igorcleot@outlook.com"
ACADEMIA = "Academia contorno do corpo"

FILL_JS = """
(values) => {
    function fill(el, val) {
        if (!el) return 'NOT_FOUND';
        const proto = el.tagName === 'TEXTAREA'
            ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
        setter.call(el, val);
        ['input','change','blur'].forEach(ev => el.dispatchEvent(new Event(ev,{bubbles:true})));
        return 'OK';
    }
    const inputs = Array.from(document.querySelectorAll('input[type="text"], input[type="email"], textarea'))
        .filter(el => el.offsetParent !== null);
    return JSON.stringify({
        totalFields: inputs.length,
        name: fill(inputs[0], values[0]),
        email: fill(inputs[1], values[1]),
        gym: fill(inputs[2], values[2]),
        amount: fill(inputs[3], values[3])
    });
}
"""

CHECKBOX_SUBMIT_JS = """
() => {
    const result = {};
    const cbs = Array.from(document.querySelectorAll('[role="checkbox"]'));
    if (cbs.length > 0) { cbs[0].click(); result.checkbox='MARCADO'; }
    else {
        const ins = Array.from(document.querySelectorAll('input[type="checkbox"]'));
        if (ins.length) { if(!ins[0].checked) ins[0].click(); result.checkbox=ins[0].checked?'MARCADO':'FALHOU'; }
        else result.checkbox='NAO_ENCONTRADO';
    }
    const btn = Array.from(document.querySelectorAll('[role="button"]')).find(el=>{
        const t=el.textContent.trim().toLowerCase();
        return t==='submit'||t==='enviar'||t==='send';
    });
    if (btn){ btn.click(); result.submit='CLICADO'; } else result.submit='NAO_ENCONTRADO';
    return JSON.stringify(result);
}
"""


def emit(d):
    print(json.dumps(d, ensure_ascii=False), flush=True)


def wait_for_form(page, timeout_s=300):
    """Aguarda os 4 campos de texto aparecerem (usuário loga na mesma janela se preciso)."""
    deadline = time.time() + timeout_s
    warned = False
    while time.time() < deadline:
        try:
            n = page.evaluate(
                "() => Array.from(document.querySelectorAll('input[type=text],input[type=email],textarea'))"
                ".filter(e=>e.offsetParent!==null).length"
            )
        except Exception:
            n = 0
        if n >= 4:
            return True
        if not warned:
            emit({"status": "AGUARDANDO_LOGIN",
                  "msg": "Faca login NESTA janela do Chrome. Nao feche. Assim que o formulario abrir, o script segue sozinho."})
            warned = True
        time.sleep(3)
        # reforca a navegacao para o form apos login
        if "docs.google.com/forms" not in page.url:
            try:
                page.goto(FORM_URL, wait_until="networkidle", timeout=20000)
            except Exception:
                pass
    return False


def upload(page, path):
    # tenta varios rotulos de botao de upload
    labels = ["Adicionar arquivo", "Add file", "Enviar arquivo", "Fazer upload", "Upload", "Adicionar arquivos"]
    clicked = None
    for lb in labels:
        try:
            el = page.query_selector(f'[role="button"]:has-text("{lb}")')
            if el:
                el.click()
                clicked = lb
                break
        except Exception:
            continue
    if not clicked:
        return "BOTAO_UPLOAD_NAO_ENCONTRADO"
    time.sleep(4)

    # procura input[type=file] em qualquer frame (picker abre em iframe)
    file_input = None
    for _ in range(6):
        for f in page.frames:
            fi = f.query_selector('input[type="file"]')
            if fi:
                file_input = fi
                break
        if file_input:
            break
        time.sleep(1)
    if not file_input:
        return "INPUT_FILE_NAO_ENCONTRADO"

    file_input.set_input_files(path)
    time.sleep(6)

    # confirma insercao (Inserir/Insert/Upload/Selecionar)
    for f in page.frames:
        for lb in ["Inserir", "Insert", "Upload", "Fazer upload", "Selecionar"]:
            try:
                btn = f.query_selector(f'button:has-text("{lb}")')
                if btn:
                    btn.click()
                    time.sleep(4)
                    return "OK"
            except Exception:
                continue
    # alguns formularios sobem o arquivo direto sem botao de confirmar
    time.sleep(3)
    return "OK_SEM_CONFIRMAR"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--valor", required=True)
    ap.add_argument("--comprovante", required=True)
    args = ap.parse_args()

    with sync_playwright() as pw:
        b = pw.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False,
            args=["--disable-blink-features=AutomationControlled"])
        page = b.pages[0] if b.pages else b.new_page()
        page.goto(FORM_URL, wait_until="networkidle", timeout=30000)
        time.sleep(2)

        if not wait_for_form(page):
            emit({"status": "TIMEOUT_LOGIN", "msg": "Formulario nao carregou (login nao concluido a tempo)."})
            b.close()
            return

        result = {}
        result["fill"] = json.loads(page.evaluate(FILL_JS, [NOME, EMAIL, ACADEMIA, args.valor]))

        if Path(args.comprovante).exists():
            try:
                result["upload"] = upload(page, args.comprovante)
            except Exception as e:
                result["upload"] = f"ERRO: {e}"
        else:
            result["upload"] = "ARQUIVO_INEXISTENTE"

        # so submete se o upload deu certo
        if not str(result["upload"]).startswith("OK"):
            result["status"] = "ABORTADO_SEM_UPLOAD"
            emit(result)
            time.sleep(2)
            b.close()
            return

        time.sleep(1)
        result["checkbox_submit"] = json.loads(page.evaluate(CHECKBOX_SUBMIT_JS))
        time.sleep(5)
        body = (page.text_content("body") or "").lower()
        result["status"] = "ENVIADO" if ("recorded" in body or "registrada" in body or "thanks" in body or "obrigad" in body) else "INCERTO"
        if result["status"] == "INCERTO":
            result["body_preview"] = body[:300]
        emit(result)
        time.sleep(2)
        b.close()


if __name__ == "__main__":
    main()
