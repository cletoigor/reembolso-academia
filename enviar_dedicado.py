#!/usr/bin/env python3
"""Runner mensal do reembolso academia — usa o perfil dedicado `chrome-dedicado`.

Chrome real (channel=chrome) num user-data-dir proprio, logado uma unica vez por
`login_dedicado.py`. NUNCA aponta para o perfil pessoal do Chrome (ver
enviar_perfil_real.py, que deslogou o Igor de tudo em jul/2026).

Upload vai por set_input_files no iframe do Google Picker — sem seletor nativo.

  --dry-run   abre o form, confere login e campos, NAO faz upload nem envia.
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ESTADO = Path(__file__).parent / "enviados.json"

FORM_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLSda3D0-pMe4H6XciC6L51NzuB4TLcqwTEw35gh8tzbxCx137Q/viewform"
)
PROFILE_DIR = str(Path(__file__).parent / "chrome-dedicado")

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

COUNT_FIELDS_JS = """
() => Array.from(document.querySelectorAll('input[type="text"], input[type="email"], textarea'))
        .filter(el => el.offsetParent !== null).length
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

LOGIN_MARKERS = ("sign in", "sign-in", "login", "fazer login", "accounts.google")


def emit(d):
    print(json.dumps(d, ensure_ascii=False), flush=True)


def historico():
    try:
        return json.loads(ESTADO.read_text())
    except Exception:
        return {}


def ja_enviado(mes):
    return historico().get(mes)


def registrar(mes, valor, comprovante, headless):
    """Grava o envio do mes. Idempotencia: o run do dia 16 nao duplica."""
    h = historico()
    h[mes] = {
        "enviado_em": datetime.now().isoformat(timespec="seconds"),
        "valor_usd": valor,
        "comprovante": str(comprovante),
        "headless": headless,
    }
    ESTADO.write_text(json.dumps(h, ensure_ascii=False, indent=2))


def parede_de_login(page):
    """True se o Google interpos uma tela de login em vez do formulario."""
    alvo = f"{page.title() or ''} {page.url}".lower()
    return any(m in alvo for m in LOGIN_MARKERS)


def anexo_presente(page, path):
    """True se o form ja mostra o arquivo anexado (chip com o nome do arquivo).

    Depois que o Picker insere o arquivo, o Google Forms exibe o nome do arquivo
    na pergunta de upload. Se esse chip nao aparece, o anexo NAO colou — mesmo que
    o botao de confirmar tenha sido clicado. Foi o que quebrou agosto/2026.
    """
    nome_arq = Path(path).name
    try:
        body = (page.text_content("body") or "")
    except Exception:
        body = ""
    return nome_arq in body


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
                    break
            except Exception:
                continue

    # Espera o chip do arquivo aparecer NO FORM (nao no picker). So entao o anexo colou.
    for _ in range(15):
        time.sleep(1)
        if anexo_presente(page, path):
            return "OK"
    return "ANEXO_NAO_CONFIRMADO"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--valor")
    ap.add_argument("--comprovante")
    ap.add_argument("--dry-run", action="store_true",
                    help="confere login e campos; nao faz upload nem envia")
    ap.add_argument("--headless", action="store_true",
                    help="sem janela; o Google pode tratar headless como suspeito")
    ap.add_argument("--force", action="store_true",
                    help="envia mesmo se o mes ja constar em enviados.json")
    args = ap.parse_args()

    if not args.dry_run and not (args.valor and args.comprovante):
        ap.error("--valor e --comprovante sao obrigatorios fora do --dry-run")

    mes = datetime.now().strftime("%Y-%m")
    anterior = ja_enviado(mes)
    if anterior and not args.dry_run and not args.force:
        emit({"status": "JA_ENVIADO", "mes": mes, "registro": anterior,
              "msg": "Reembolso deste mes ja foi enviado. Use --force para duplicar."})
        return 0

    if not Path(PROFILE_DIR).exists():
        emit({"status": "PERFIL_INEXISTENTE",
              "msg": f"{PROFILE_DIR} nao existe. Rode login_dedicado.py primeiro."})
        return 1

    with sync_playwright() as pw:
        b = pw.chromium.launch_persistent_context(
            PROFILE_DIR,
            channel="chrome",
            headless=args.headless,
            ignore_default_args=["--enable-automation"],
            args=["--disable-blink-features=AutomationControlled",
                  "--no-first-run", "--no-default-browser-check"],
        )
        try:
            page = b.pages[0] if b.pages else b.new_page()
            page.goto(FORM_URL, wait_until="networkidle", timeout=40000)
            time.sleep(3)

            if parede_de_login(page):
                emit({"status": "SESSAO_EXPIRADA", "title": page.title(), "url": page.url,
                      "msg": "Perfil dedicado caiu do Google. Rode login_dedicado.py."})
                return 1

            if args.dry_run:
                campos = page.evaluate(COUNT_FIELDS_JS)
                ok = campos >= 4
                emit({"status": "DRY_RUN_OK" if ok else "CAMPOS_INSUFICIENTES",
                      "campos_visiveis": campos, "title": page.title(),
                      "msg": "Form acessivel e sessao viva; nada foi enviado." if ok
                             else "Form carregou parcialmente — provavel parede de login."})
                return 0 if ok else 1

            result = {}
            result["fill"] = json.loads(page.evaluate(FILL_JS, [NOME, EMAIL, ACADEMIA, args.valor]))
            if result["fill"].get("totalFields", 0) < 4:
                emit({"status": "CAMPOS_INSUFICIENTES", "detalhe": result["fill"]})
                return 1

            try:
                result["upload"] = (upload(page, args.comprovante)
                                    if Path(args.comprovante).exists() else "ARQUIVO_INEXISTENTE")
            except Exception as e:
                result["upload"] = f"ERRO: {e}"

            if not str(result["upload"]).startswith("OK"):
                result["status"] = "ABORTADO_SEM_UPLOAD"
                emit(result)
                return 1

            time.sleep(1)
            result["checkbox_submit"] = json.loads(page.evaluate(CHECKBOX_SUBMIT_JS))
            time.sleep(6)
            body = (page.text_content("body") or "").lower()
            enviado = any(k in body for k in
                          ["recorded", "registrada", "obrigad", "thanks", "your response"])
            result["status"] = "ENVIADO" if enviado else "INCERTO"
            if enviado:
                registrar(mes, args.valor, args.comprovante, args.headless)
                result["registrado_em"] = str(ESTADO)
            else:
                result["body_preview"] = body[:300]
            emit(result)
            return 0 if enviado else 1
        finally:
            time.sleep(2)
            try:
                b.close()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
