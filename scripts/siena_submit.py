"""Preenche e submete o formulário Ashby da Siena mapeando campos por label de pergunta.

Localiza cada campo pelo texto da pergunta (resiliente a UUIDs que mudam),
preenche, anexa o CV, marca consent, clica em Submit e verifica confirmação.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

ROOT = Path("/Users/hendrixfreire/Projetos/candidatura-agent")
CFG = json.loads((ROOT / "config.json").read_text())
PROFILE = json.loads((ROOT / "data/profile.json").read_text())

URL = "https://jobs.ashbyhq.com/siena/7627e178-473e-4ebd-b193-62ffefafdae0/application?utm_source=zLmkeq71qy"
RESUME = "/Users/hendrixfreire/Documents/CVs/cv_siena_deployment_manager.pdf"
SHOT_DIR = ROOT / "reports/screenshots/job-siena-manual"
SHOT_DIR.mkdir(parents=True, exist_ok=True)

# Respostas discursivas (aprovadas pelo usuário)
A_AI_WORKFLOW = """AI isn't a tool I reach for occasionally — it's the backbone of how I deliver for accounts. I run a daily, production ecosystem of agents (Claude, Codex, Hermes Agent, OpenCode), each routed to what it does best: Claude for analysis and writing, Codex for code and pipeline scaffolding, Hermes for orchestrating multi-step operational workflows, OpenCode for refactors and local iteration.

For accounts, this shows up concretely: when a brand's data pipeline needs a new connector or transformation, I scaffold it with an agent in minutes instead of days, then verify every line myself. When I need to diagnose why a client's reporting throughput dipped, I point an agent at the logs and the Lakehouse layers and get a structured hypothesis to validate — not a black-box answer. I train the team the same way: demo days, shared prompt libraries, "which model handles which case" threads.

The role AI plays in account management is leverage. It lets a small function own outcomes for ten-plus concurrent brands without dropping quality. I treat it as an extension of the team — delegated to, reviewed, and held to the same standard as a human collaborator. That's exactly the posture Siena is selling to its own customers."""

A_DEPLOYMENT_WRONG = """A consumer-brand analytics rollout where I'd underestimated the integration surface. We'd scoped the deployment around three primary data sources, but the brand was actually running across seven disconnected platforms — two of them legacy exports that nobody had flagged in kick-off. Two weeks in, the Gold layer was reconciling cleanly for the flagship dashboards but silently dropping ~15% of transactions from the secondary channels. The client noticed before we did, in a stakeholder review.

What broke wasn't technical — it was discovery. I'd trusted the kickoff inventory instead of instrumenting it. I turned it around in three moves. First, I froze the rollout and was direct with the client: here's the gap, here's the impact, here's the fix timeline — no spin. Second, I ran a full source audit with an agent parsing every export schema, so the map matched reality, not the kickoff doc. Third, I rebuilt the ingestion with explicit reconciliation checks that surface drift automatically — the same monitoring posture I now apply to every account.

The deployment shipped on the revised date and the client expanded scope the following quarter. The lesson I carry forward: deployments fail at the seams, not the center — instrument discovery, make automation health visible, and tell the client before they tell you."""

A_MULTI_ACCOUNT = """I run on a few principles that scale across concurrent accounts. First, written over meeting — every account has a living status doc: what shipped, what's blocked, what's next, who owns it. Anyone can see the state of an account without asking me, which kills the status-meeting tax. Second, proactive monitoring over reactive status — I watch automation rate, pipeline freshness, and escalation patterns, and I flag the dip before the client does. Evidence, not gut feel.

Third, I break complex rollouts into workstreams with explicit owners and visible blockers, so no account stalls on a single person's calendar. Fourth, I push back early on scope creep — it's cheaper to renegotiate a timeline than to miss one quietly. Fifth, I lean on AI leverage hard: scaffolding, transformation scripts, and monitoring are agent-assisted so my time goes to judgment, stakeholder alignment, and the diagnosis work that actually needs a human.

The throughline is making status visible. When every account's state is written down, monitored, and current, managing ten feels close to managing two. When it isn't, even one can slip. I'd rather over-communicate a green account than leave a red one hidden."""

SALARY_USD = "110000"
START_DATE = "2026-08-03"
CX_OPS_ANSWER = "Yes"  # 5+ yrs em CX ops/implementation
PT_TIMEZONE_ANSWER = "Yes"
PORTFOLIO_LINK = ""  # campo opcional — deixar vazio


def find_input_by_question(page, question_substring: str, input_type: str = None):
    """Localiza um input/textarea cuja pergunta ancestral contém o texto."""
    JS = r"""(args) => {
      const [q, wantType] = args;
      const ql = q.toLowerCase();
      const els = [...document.querySelectorAll("input,textarea,select")];
      for (const el of els) {
        if (wantType && el.type !== wantType) continue;
        let n = el;
        for (let i = 0; i < 7 && n; i++) {
          n = n.parentElement;
          if (!n) break;
          const t = (n.innerText || "").toLowerCase();
          if (t.length > 5 && t.length < 600 && t.includes(ql)) {
            return {found: true, id: el.id, name: el.name, type: el.type, tag: el.tagName.toLowerCase()};
          }
        }
      }
      return {found: false};
    }"""
    res = page.evaluate(JS, [question_substring, input_type])
    return res


def fill_text(page, question: str, value: str, input_type: str = None) -> bool:
    """Preenche via JS direto no elemento localizado pela pergunta (resiliente a IDs vazios)."""
    JS = r"""(args) => {
      const [q, wantType, val] = args;
      const ql = q.toLowerCase();
      const els = [...document.querySelectorAll("input,textarea,select")];
      for (const el of els) {
        if (wantType && el.type !== wantType) continue;
        let n = el;
        for (let i = 0; i < 7 && n; i++) {
          n = n.parentElement;
          if (!n) break;
          const t = (n.innerText || "").toLowerCase();
          if (t.length > 5 && t.length < 600 && t.includes(ql)) {
            return {found: true, id: el.id, name: el.name, type: el.type, tag: el.tagName.toLowerCase(), value: val};
          }
        }
      }
      return {found: false};
    }"""
    res = page.evaluate(JS, [question, input_type, value])
    if not res.get("found"):
        print(f"  [NOT FOUND] {question!r}")
        return False
    # Preenche via JS no próprio elemento, usando native setter + eventos (React-aware)
    fill_js = r"""(args) => {
      const [id, name, val, tag, ftype] = args;
      let el = id ? document.getElementById(id) : (name ? document.querySelector(`[name="${name}"]`) : null);
      if (!el) return {ok:false, reason:"element not resolved"};
      el.scrollIntoView({block:"center"});
      el.focus();
      const nativeSetter = (proto) => Object.getOwnPropertyDescriptor(proto, "value")?.set;
      let setter = null;
      if (el instanceof HTMLInputElement) setter = nativeSetter(HTMLInputElement.prototype);
      else if (el instanceof HTMLTextAreaElement) setter = nativeSetter(HTMLTextAreaElement.prototype);
      else if (el instanceof HTMLSelectElement) setter = nativeSetter(HTMLSelectElement.prototype);
      if (setter) setter.call(el, val); else el.value = val;
      el.dispatchEvent(new Event("input", {bubbles:true}));
      el.dispatchEvent(new Event("change", {bubbles:true}));
      el.dispatchEvent(new Event("blur", {bubbles:true}));
      return {ok:true, id:el.id, type:el.type, valueNow: el.value};
    }"""
    r2 = page.evaluate(fill_js, [res.get("id"), res.get("name"), value, res.get("tag"), res.get("type")])
    print(f"  [fill] {question[:45]!r} -> {value[:35]!r}: {r2}")
    return bool(r2.get("ok"))


def check_yesno(page, question: str, answer: str) -> bool:
    """Clica no botão/label 'Yes' ou 'No' dentro da seção da pergunta.
    Ashby renderiza como radio-like: labels 'Yes'/'No' clicáveis agrupados por pergunta."""
    JS = r"""(args) => {
      const [q, ans] = args;
      const ql = q.toLowerCase();
      // Procura todos os elementos clicáveis com texto exato 'Yes'/'No'
      const want = ans.toLowerCase();
      const candidates = [...document.querySelectorAll("label, button, span, div, input")];
      // Primeiro: acha o wrapper da pergunta
      let questionWrapper = null;
      for (const el of [...document.querySelectorAll("div, section, fieldset")]) {
        const t = (el.innerText || "").toLowerCase();
        if (t.includes(ql) && t.length < 700) {
          // pega o menor wrapper que contém a pergunta (mais específico)
          if (!questionWrapper || el.querySelectorAll("*").length < questionWrapper.querySelectorAll("*").length) {
            questionWrapper = el;
          }
        }
      }
      if (!questionWrapper) return {clicked: false, reason: "question wrapper not found"};
      // Dentro do wrapper, acha o elemento cujo texto é exatamente 'yes' ou 'no'
      const inner = [...questionWrapper.querySelectorAll("label, button, span, div, input[type=radio], input[type=checkbox]")];
      for (const el of inner) {
        const own = (el.innerText || el.value || "").trim().toLowerCase();
        // Aceita match exato ou texto principal
        if (own === want) {
          // Se for input radio/checkbox, clica nele; senão clica no label
          const target = (el.tagName === "INPUT") ? el : (el.querySelector("input[type=radio],input[type=checkbox]") || el);
          target.click();
          return {clicked: true, tag: target.tagName, want: want, wrapperText: (questionWrapper.innerText||"").trim().slice(0,150)};
        }
      }
      return {clicked: false, reason: "yes/no not found in wrapper", wrapperText: (questionWrapper.innerText||"").trim().slice(0,200)};
    }"""
    res = page.evaluate(JS, [question, answer])
    print(f"  [yesno] {question[:40]!r} answer={answer}: {res}")
    return bool(res.get("clicked"))


def fill_by_id(page, field_id: str, value: str, label: str = "") -> bool:
    """Preenche um input/textarea por ID usando native setter + eventos React."""
    JS = r"""(args) => {
      const [id, val] = args;
      const el = document.getElementById(id);
      if (!el) return {ok:false, reason:"not found"};
      el.scrollIntoView({block:"center"});
      el.focus();
      const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
      if (setter) setter.call(el, val); else el.value = val;
      el.dispatchEvent(new Event("input", {bubbles:true}));
      el.dispatchEvent(new Event("change", {bubbles:true}));
      el.dispatchEvent(new Event("blur", {bubbles:true}));
      return {ok:true, len: el.value.length};
    }"""
    r = page.evaluate(JS, [field_id, value])
    print(f"  [by_id] {label or field_id}: {r}")
    return bool(r.get("ok"))


def fill_text_by_wrapper(page, question: str, value: str) -> bool:
    """Preenche input sem id/name localizando pelo texto do wrapper mais próximo."""
    JS = r"""(args) => {
      const [q, val] = args;
      const ql = q.toLowerCase();
      const els = [...document.querySelectorAll("input,textarea")];
      for (const el of els) {
        // wrapper mais próximo: subir poucos níveis e pegar texto curto
        let best = "";
        let n = el.parentElement;
        let d = 0;
        while (n && d < 6) {
          const t = (n.innerText || "").trim();
          if (t.length > 8 && t.length < 350) best = t;
          n = n.parentElement; d++;
        }
        if (best.toLowerCase().includes(ql)) {
          el.scrollIntoView({block:"center"});
          el.focus();
          const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
          if (setter) setter.call(el, val); else el.value = val;
          el.dispatchEvent(new Event("input", {bubbles:true}));
          el.dispatchEvent(new Event("change", {bubbles:true}));
          el.dispatchEvent(new Event("blur", {bubbles:true}));
          return {ok:true, valueNow: el.value, wrapper: best.slice(0,80)};
        }
      }
      return {ok:false, reason:"not found"};
    }"""
    r = page.evaluate(JS, [question, value])
    print(f"  [by_wrapper] {question[:40]!r}: {r}")
    return bool(r.get("ok"))


def fill_combobox(page, question: str, value: str) -> bool:
    """Preenche um React Select combobox: clica, digita, seleciona opção que contém o valor."""
    # localiza o combobox pelo wrapper da pergunta
    JS_find = r"""(q) => {
      const ql = q.toLowerCase();
      const cbs = [...document.querySelectorAll('input[role="combobox"], input[aria-autocomplete="list"]')];
      for (const el of cbs) {
        let n = el.parentElement; let d = 0; let best = "";
        while (n && d < 6) { const t=(n.innerText||"").trim(); if(t.length>3&&t.length<200) best=t; n=n.parentElement; d++; }
        if (best.toLowerCase().includes(ql)) return {found:true, x: el.getBoundingClientRect().x, y: el.getBoundingClientRect().y};
      }
      return {found:false};
    }"""
    pos = page.evaluate(JS_find, question)
    if not pos.get("found"):
        print(f"  [combobox NOT FOUND] {question!r}")
        return False
    # clica no combobox pelo papel
    combo = page.locator(f'input[role="combobox"]').first
    combo.scroll_into_view_if_needed(timeout=5000)
    combo.click()
    page.wait_for_timeout(400)
    combo.fill("")
    # digita parte do valor (cidade) para filtrar opções
    type_val = value.split(",")[0]  # "São Paulo"
    combo.press_sequentially(type_val, delay=30)
    page.wait_for_timeout(1500)
    # seleciona a primeira opção que contém o valor completo
    try:
        opts = page.locator('[role="option"]:visible, [role="listbox"] [role="option"], li[role="option"], div[role="option"]')
        count = opts.count()
        print(f"  [combobox] options count={count}")
        chosen = False
        for i in range(count):
            txt = opts.nth(i).inner_text(timeout=2000).strip()
            if value.lower() in txt.lower() or type_val.lower() in txt.lower():
                opts.nth(i).click()
                chosen = True
                print(f"  [combobox OK] selected: {txt[:60]!r}")
                break
        if not chosen and count > 0:
            # fallback: primeira opção
            txt = opts.nth(0).inner_text(timeout=2000).strip()
            opts.nth(0).click()
            chosen = True
            print(f"  [combobox FALLBACK] selected first: {txt[:60]!r}")
        return chosen
    except Exception as e:
        print(f"  [combobox ERR] {e}")
        return False


def main():
    cands = [(it["name"], it.get("executable_path")) for it in CFG["browser_candidates"]]
    with sync_playwright() as pw:
        ctx = None
        for name, exe in cands:
            if exe and not Path(exe).exists():
                continue
            bp = ROOT / CFG["browser_profiles"].get(name, f"data/browser-profile-{name}")
            bp.mkdir(parents=True, exist_ok=True)
            kw = {"headless": True, "executable_path": exe} if exe else {"headless": True}
            try:
                ctx = pw.chromium.launch_persistent_context(str(bp), **kw)
                print(f"[browser] {name}")
                break
            except Exception as e:
                print(f"[browser fail] {name}: {e}")
        if ctx is None:
            sys.exit("Sem browser")

        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        print("[goto]", URL)
        page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_selector("input[type=email]", timeout=20000)
        page.wait_for_timeout(2000)

        # 1. Nome
        fill_text(page, "Your Full Name", PROFILE["full_name"])
        # 2. Email
        fill_text(page, "Your Email", PROFILE["email"], input_type="email")
        # 3. Resume upload (input file com id _systemfield_resume)
        resume_input = page.locator("input#_systemfield_resume").first
        resume_input.set_input_files(RESUME)
        page.wait_for_timeout(2500)
        print("  [OK upload] resume")
        # 4. CX ops 5+ yrs (Yes/No)
        check_yesno(page, "Have you worked for more than 5yrs in customer experience operations", CX_OPS_ANSWER)
        # 5. PT timezone (Yes/No)
        check_yesno(page, "Are you able to work hours that overlap with West Coast", PT_TIMEZONE_ANSWER)
        # 6. Location (combobox React Select — click + type + select option)
        fill_combobox(page, "Where will you be working from", PROFILE["location"])
        # 7. Earliest start date (text input, date picker — preenche texto)
        fill_text_by_wrapper(page, "earliest date that you will be able to start", START_DATE)
        # 8. Salary expectations (number)
        fill_text(page, "salary expectations", SALARY_USD, input_type="number")
        # 9. LinkedIn URL
        fill_text(page, "LinkedIn", PROFILE["linkedin"], input_type="url")
        # 10. Portfolio (opcional) - pular
        # 11. Três discursivas (textareas) — preencher POR ID (wrappers são idênticos)
        fill_by_id(page, "dc110f2d-3f05-42c4-8e68-3025b02d9692", A_AI_WORKFLOW, label="Q1 AI workflow")
        fill_by_id(page, "acaacd28-4220-4666-b0bd-8c3f4cfab630", A_DEPLOYMENT_WRONG, label="Q2 deployment wrong")
        fill_by_id(page, "af767617-e2a6-4cd5-9df7-00559de6230b", A_MULTI_ACCOUNT, label="Q3 multi-account")
        # 12. Consent checkbox "I agree"
        try:
            page.locator("input[type=checkbox][id*='data_consent_ack']").first.check(force=True)
            print("  [OK] consent checkbox")
        except Exception as e:
            print(f"  [WARN] consent checkbox: {e}")

        page.wait_for_timeout(1500)
        page.screenshot(path=str(SHOT_DIR / "pre-submit.png"), full_page=True)
        print(f"[screenshot] {SHOT_DIR / 'pre-submit.png'}")

        # Procurar e clicar no botão "Submit Application" (filtrar dos Yes/No/Upload)
        submit = page.get_by_role("button", name="Submit Application")
        print(f"[submit] count={submit.count()}")
        if submit.count() == 0:
            # fallback: button[type=submit] cujo texto contém "submit application"
            submit = page.locator("button[type=submit]").filter(has_text="Submit Application")
            print(f"[submit fallback] count={submit.count()}")
        if submit.count() == 0:
            page.screenshot(path=str(SHOT_DIR / "no-submit-found.png"), full_page=True)
            sys.exit("Botão Submit Application não encontrado")
        submit.first.click()
        print("[submit] clicked")
        # Esperar confirmação ou erro
        try:
            page.wait_for_timeout(4000)
        except Exception:
            pass
        page.screenshot(path=str(SHOT_DIR / "post-submit.png"), full_page=True)
        print(f"[screenshot] {SHOT_DIR / 'post-submit.png'}")

        body_lower = page.locator("body").inner_text(timeout=8000).lower()
        body_full = body_lower
        confirm_terms = ("thank you for applying", "application submitted", "application has been submitted",
                         "thanks for applying", "successfully", "we've received your application",
                         "received your application")
        confirmed = any(t in body_lower for t in confirm_terms)
        # Detectar mensagens de erro/limite
        limit_hit = "application limit" in body_lower or "already applied" in body_lower or "limit" in body_lower
        print(f"[RESULT] confirmed={confirmed} limit_hit={limit_hit} final_url={page.url}")
        print("[BODY FULL]:", body_full[:2500])
        # capturar erros de validação do DOM
        try:
            errs = page.evaluate(r"""() => [...document.querySelectorAll("[role=alert],[aria-invalid='true'],[class*='error'][class*='i18n'],[class*='ErrorText'],[class*='errorMessage']")].map(e => (e.innerText||e.textContent||"").trim().slice(0,150))""")
            print("[VALIDATION ERRORS]:", json.dumps(errs, ensure_ascii=False))
        except Exception as e:
            print("[errs probe fail]", e)
        ctx.close()


if __name__ == "__main__":
    main()
