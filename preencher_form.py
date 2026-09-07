#!/usr/bin/env python3
"""Preenche e envia o Google Form de reembolso de academia da Revelo via Playwright."""

import argparse
import json
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

FORM_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLSda3D0-pMe4H6XciC6L51NzuB4TLcqwTEw35gh8tzbxCx137Q/viewform?pli=1"
)
PROFILE_DIR = str(Path(__file__).parent / "chrome-profile")
CDP_PORT = 9234

NOME = "Igor Cleto"
EMAIL = "igorcleot@outlook.com"
ACADEMIA = "Academia contorno do corpo"

FILL_JS = """
(values) => {
    function fill(el, val) {
        if (!el) return 'NOT_FOUND';
        const proto = el.tagName === 'TEXTAREA'
            ? HTMLTextAreaElement.prototype
            : HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
        setter.call(el, val);
        ['input', 'change', 'blur'].forEach(ev =>
            el.dispatchEvent(new Event(ev, { bubbles: true }))
        );
        return 'OK';
    }
    const inputs = Array.from(
        document.querySelectorAll('input[type="text"], input[type="email"], textarea')
    ).filter(el => el.offsetParent !== null);
    return JSON.stringify({
        totalFields: inputs.length,
        name:   fill(inputs[0], values[0]),
        email:  fill(inputs[1], values[1]),
        gym:    fill(inputs[2], values[2]),
        amount: fill(inputs[3], values[3])
    });
}
"""

CHECKBOX_SUBMIT_JS = """
() => {
    const result = {};
    const checkboxes = Array.from(document.querySelectorAll('[role="checkbox"]'));
    if (checkboxes.length > 0) {
        checkboxes[0].click();
        result.checkbox = 'MARCADO';
    } else {
        const inputs = Array.from(document.querySelectorAll('input[type="checkbox"]'));
        if (inputs.length > 0) {
            if (!inputs[0].checked) inputs[0].click();
            result.checkbox = inputs[0].checked ? 'MARCADO' : 'FALHOU';
        } else {
            result.checkbox = 'NAO_ENCONTRADO';
        }
    }
    const btn = Array.from(document.querySelectorAll('[role="button"]'))
        .find(el => {
            const t = el.textContent.trim().toLowerCase();
            return t === 'submit' || t === 'enviar' || t === 'send';
        });
    if (btn) {
        btn.click();
        result.submit = 'CLICADO';
    } else {
        result.submit = 'NAO_ENCONTRADO';
    }
    return JSON.stringify(result);
}
"""


def emit(data):
    print(json.dumps(data), flush=True)


def run_login(pw):
    browser = pw.chromium.launch_persistent_context(
        PROFILE_DIR, headless=False, args=["--disable-blink-features=AutomationControlled"]
    )
    page = browser.pages[0] if browser.pages else browser.new_page()
    page.goto("https://accounts.google.com")
    emit({"status": "LOGIN_ABERTO", "msg": "Faca login no Google e feche o browser quando terminar."})
    try:
        page.wait_for_event("close", timeout=300_000)
    except Exception:
        pass
    browser.close()
    emit({"status": "LOGIN_OK"})


def upload_via_picker(page, comprovante_path):
    """Clica em 'Adicionar arquivo', encontra o input no iframe do picker e faz upload."""
    page.click('[role="button"]:has-text("Adicionar arquivo")', timeout=5000)
    time.sleep(3)

    picker_frame = None
    for f in page.frames:
        if "picker" in f.url:
            picker_frame = f
            break

    if not picker_frame:
        return "PICKER_NAO_ENCONTRADO"

    file_input = picker_frame.query_selector('input[type="file"]')
    if not file_input:
        return "INPUT_NAO_ENCONTRADO"

    file_input.set_input_files(comprovante_path)
    time.sleep(5)

    try:
        picker_frame.click('button:has-text("Inserir")', timeout=5000)
    except Exception:
        try:
            picker_frame.click('button:has-text("Insert")', timeout=3000)
        except Exception:
            return "INSERIR_NAO_ENCONTRADO"

    time.sleep(3)
    return "OK"


def run_form(pw, valor, comprovante_path):
    result = {}
    browser = pw.chromium.launch_persistent_context(
        PROFILE_DIR,
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
    )
    page = browser.pages[0] if browser.pages else browser.new_page()

    page.goto(FORM_URL, wait_until="networkidle", timeout=30_000)
    time.sleep(2)

    title = page.title()
    if "login" in title.lower() or "sign in" in title.lower():
        emit({"status": "PRECISA_LOGIN", "msg": "Google Form requer login. Rode com --login primeiro."})
        browser.close()
        return

    fill_result = page.evaluate(FILL_JS, [NOME, EMAIL, ACADEMIA, valor])
    result["fill"] = json.loads(fill_result)

    if result["fill"].get("totalFields", 0) < 4:
        emit({"status": "CAMPOS_INSUFICIENTES", "msg": f"Encontrados {result['fill']['totalFields']} campos, esperava 4."})
        browser.close()
        return

    if comprovante_path and Path(comprovante_path).exists():
        try:
            upload_status = upload_via_picker(page, comprovante_path)
            result["upload"] = upload_status
        except Exception as e:
            result["upload"] = f"ERRO: {e}"
    else:
        result["upload"] = "SEM_ARQUIVO"

    time.sleep(1)
    cs_result = page.evaluate(CHECKBOX_SUBMIT_JS)
    result["checkbox_submit"] = json.loads(cs_result)

    time.sleep(5)
    body_text = page.text_content("body") or ""
    if "recorded" in body_text.lower() or "registrada" in body_text.lower() or "thanks" in body_text.lower():
        result["status"] = "ENVIADO"
    else:
        result["status"] = "INCERTO"
        result["body_preview"] = body_text[:300]

    emit(result)
    time.sleep(2)
    browser.close()


def main():
    parser = argparse.ArgumentParser(description="Preenche form reembolso academia Revelo")
    parser.add_argument("--valor", help="Valor em USD (ex: 18.50)")
    parser.add_argument("--comprovante", help="Caminho do arquivo de comprovante")
    parser.add_argument("--login", action="store_true", help="Abrir browser para login Google")
    args = parser.parse_args()

    with sync_playwright() as pw:
        if args.login:
            run_login(pw)
        elif args.valor:
            run_form(pw, args.valor, args.comprovante)
        else:
            emit({"status": "ERRO", "msg": "Use --valor ou --login"})
            sys.exit(1)


if __name__ == "__main__":
    main()
