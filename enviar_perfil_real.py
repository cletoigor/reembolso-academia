#!/usr/bin/env python3
"""APOSENTADO — NAO USAR. Substituido por enviar_dedicado.py.

Abria o PERFIL REAL do Chrome via Playwright. Em jul/2026 isso deslogou o Igor de
tudo (os tokens do perfil nao descriptografam sob --use-mock-keychain) e o Chrome
ainda recusa remote-debugging no user-data-dir padrao. Mantido so como referencia.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.exit(
    "APOSENTADO: este script abre o perfil pessoal do Chrome e ja causou um "
    "deslogamento geral em jul/2026. Use enviar_dedicado.py (perfil chrome-dedicado)."
)

FORM_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLSda3D0-pMe4H6XciC6L51NzuB4TLcqwTEw35gh8tzbxCx137Q/viewform"
)
USER_DATA_DIR = str(Path.home() / "Library/Application Support/Google/Chrome")
PROFILE = "Profile 2"

NOME = "Igor Cleto"
EMAIL = "igorcleot@outlook.com"
ACADEMIA = "Academia contorno do corpo"

FILL_JS = """
(values) => {
    function fill(el, val) {
        if (!el) return 'NOT_FOUND';
        const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
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


def upload(page, path):
    labels = ["Adicionar arquivo", "Add file", "Adicionar arquivos", "Enviar arquivo", "Upload"]
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

    file_input = None
    for _ in range(8):
        for f in page.frames:
            try:
                fi = f.query_selector('input[type="file"]')
            except Exception:
                fi = None
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

    for f in page.frames:
        for lb in ["Fazer upload", "Upload", "Inserir", "Insert", "Selecionar"]:
            try:
                btn = f.query_selector(f'button:has-text("{lb}")')
                if btn and btn.is_visible():
                    btn.click()
                    time.sleep(5)
                    return "OK"
            except Exception:
                continue
    time.sleep(4)
    return "OK_SEM_CONFIRMAR"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--valor", required=True)
    ap.add_argument("--comprovante", required=True)
    args = ap.parse_args()

    with sync_playwright() as pw:
        b = pw.chromium.launch_persistent_context(
            USER_DATA_DIR,
            channel="chrome",
            headless=False,
            args=[f"--profile-directory={PROFILE}",
                  "--disable-blink-features=AutomationControlled",
                  "--no-first-run", "--no-default-browser-check"],
        )
        page = b.pages[0] if b.pages else b.new_page()
        page.goto(FORM_URL, wait_until="networkidle", timeout=40000)
        time.sleep(3)

        title = (page.title() or "").lower()
        if "sign" in title or "login" in title or "fazer login" in title:
            emit({"status": "PRECISA_LOGIN", "title": page.title(),
                  "msg": "Perfil real nao esta logado no Google para este form."})
            b.close()
            return

        result = {}
        result["fill"] = json.loads(page.evaluate(FILL_JS, [NOME, EMAIL, ACADEMIA, args.valor]))
        if result["fill"].get("totalFields", 0) < 4:
            emit({"status": "CAMPOS_INSUFICIENTES", "detalhe": result["fill"]})
            b.close()
            return

        try:
            result["upload"] = upload(page, args.comprovante) if Path(args.comprovante).exists() else "ARQUIVO_INEXISTENTE"
        except Exception as e:
            result["upload"] = f"ERRO: {e}"

        if not str(result["upload"]).startswith("OK"):
            result["status"] = "ABORTADO_SEM_UPLOAD"
            emit(result)
            time.sleep(2)
            b.close()
            return

        time.sleep(1)
        result["checkbox_submit"] = json.loads(page.evaluate(CHECKBOX_SUBMIT_JS))
        time.sleep(6)
        body = (page.text_content("body") or "").lower()
        result["status"] = "ENVIADO" if any(k in body for k in ["recorded","registrada","obrigad","thanks","your response"]) else "INCERTO"
        if result["status"] == "INCERTO":
            result["body_preview"] = body[:300]
        emit(result)
        time.sleep(2)
        b.close()


if __name__ == "__main__":
    main()
