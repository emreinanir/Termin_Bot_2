import re
import time
import random
import locale
import smtplib
from datetime import datetime, date, timedelta
from email.message import EmailMessage
from email.utils import formatdate
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ===================== K O N F I G =====================

TARGET_URL   = "https://termine-reservieren.de/termine/buergeramt.mainz/"
UNIT_TEXT    = "Abteilung Ausländerangelegenheiten"

# Hedef hizmet metni birden fazla varyant olabilir
CONCERN_TEXTS = [
    "Aufenthaltserlaubnis zum Studium/Sprachkurs",
    "Aufenthaltserlaubnis zum Studium / Sprachkurs",
    "Studium/Sprachkurs",
    "Sprachschule / Studium",
    "Studium / Sprachschule",
    "Sprachkurs",
]

WINDOW_DAYS  = 180
STATE_FILE   = ".state_studium.txt"
INTERVAL_MIN = 15  # dakika

# E-posta ayarları (kendi değerlerinle değiştir)
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "YourGmail@gmail.com"   # <- değiştir
SMTP_PASS = "GmailAppPassword"     # <- değiştir (Google App Password)
MAIL_TO   = "YourGmail@gmail.com"   # <- değiştir (Target Gmail)

# Form verileri (ANREDE YOK!)
FORM = {
    "vorname": "Erik",
    "nachname": "Imanov",
    "email": "erikimanov@gmail.com",
    "telefon": "015259572012",
    "geburt": ("01", "07", "1995"),  # (TAG, Monat, Jahr)
}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

try:
    locale.setlocale(locale.LC_TIME, "de_DE.UTF-8")
except locale.Error:
    pass

# ===================== Y A R D I M C I =====================

def log(msg: str):
    print(f"[{formatdate(localtime=True)}] {msg}", flush=True)

def send_mail(subject, body):
    msg = EmailMessage()
    msg["From"] = SMTP_USER
    msg["To"] = MAIL_TO
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        log("Mail gönderildi.")
    except Exception as e:
        log(f"[MAIL ERROR] {e}")

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = f.read().strip()
            if not data:
                return None, None
            if "|" in data:
                date_str, time_str = data.split("|", 1)
            else:
                date_str, time_str = data, ""
            return datetime.strptime(date_str, "%Y-%m-%d").date(), time_str
    except Exception:
        return None, None

def save_state(d, t):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            f.write(f"{d.strftime('%Y-%m-%d')}|{t or ''}")
    except Exception:
        pass

def close_dialogs(page):
    for label in ["Schliessen","Schließen","OK","Akzeptieren","Verstanden"]:
        try:
            btn = page.get_by_role("button", name=label)
            if btn.count() and btn.first.is_visible():
                btn.first.click()
        except Exception:
            pass

def click_by_text(page, text):
    for role in ["button", "link"]:
        try:
            el = page.get_by_role(role, name=text)
            if el.count() and el.first.is_visible():
                el.first.click()
                return True
        except Exception:
            pass
    try:
        el = page.get_by_text(text, exact=True)
        if el.count() and el.first.is_visible():
            el.first.click()
            return True
    except Exception:
        pass
    return False

def click_plus_in_same_row(frame, label_text: str) -> bool:
    """
    label_text geçen satırı görünür alana getir ve o satırdaki '+' butonunu tıkla.
    Farklı HTML yapıları için birkaç sağlam yol dener (iframe içinde de çalışır).
    """
    try:
        label = frame.locator("xpath=//*[normalize-space(.)=" + repr(label_text) + "]").first
        if not label or not label.count():
            return False

        label.scroll_into_view_if_needed()
        frame.wait_for_timeout(300)

        container = None
        for xp in [
            "xpath=ancestor::li[1]",
            "xpath=ancestor::tr[1]",
            "xpath=ancestor::div[1]"
        ]:
            cand = label.locator(xp)
            if cand.count():
                container = cand.first
                break
        if container is None:
            container = label

        # '+' benzeri butonları sırayla dene
        for selector in [
            "xpath=.//button[normalize-space(text())='+']",
            "xpath=.//button[.//svg] | .//*[@role='button'][.//svg]",
            "xpath=.//button"
        ]:
            plus = container.locator(selector)
            if plus.count():
                plus.first.scroll_into_view_if_needed()
                frame.wait_for_timeout(150)
                plus.first.click(timeout=3000, force=True)
                return True

        # Etiketten sonra gelen ilk '+' (kardeş düğüm)
        forward_plus = label.locator("xpath=following::button[normalize-space(text())='+'][1]")
        if forward_plus.count():
            forward_plus.first.scroll_into_view_if_needed()
            frame.wait_for_timeout(150)
            forward_plus.first.click(timeout=3000, force=True)
            return True

        return False

    except Exception as e:
        log(f"[ERROR] click_plus_in_same_row: {e}")
        return False

def find_frame_with_text(page, text_regex):
    # Sayfadaki tüm frame’lerde ara; bulunamazsa ana sayfayı döndür
    for fr in page.frames:
        try:
            if fr.locator(f"xpath=//*[contains(normalize-space(.), {repr(text_regex.pattern)})]").count():
                return fr
        except Exception:
            pass
    return page

def click_plus_for_any_label(page):
    # listedeki etiketlerden ilk bulunanın satırındaki '+' tıkla (iframe dahil)
    for label in CONCERN_TEXTS:
        frame = find_frame_with_text(page, re.compile(re.escape(label), re.I))
        # metni görünür yapmaya çalış
        try:
            node = frame.locator(f"xpath=//*[contains(normalize-space(.), {repr(label)})]").first
            if node.count():
                node.scroll_into_view_if_needed()
                frame.wait_for_timeout(250)
        except Exception:
            pass
        if click_plus_in_same_row(frame, label):
            return True
    return False

def proceed_weiter(page):
    for nm in ["Weiter", "Fortfahren", "weiter", "WEITER"]:
        try:
            btn = page.get_by_role("button", name=nm)
            if btn.count() and btn.first.is_visible():
                btn.first.click()
                return True
        except Exception:
            pass
    try:
        link = page.get_by_role("link", name=re.compile(r"Weiter", re.I))
        if link.count() and link.first.is_visible():
            link.first.click()
            return True
    except Exception:
        pass
    return False

def fill_form(page):
    # --- SADECE METİN ALANLARI ve GEBURTSDATUM (ANREDE YOK) ---

    def fill(label, val):
        try:
            inp = page.get_by_label(re.compile(label, re.I))
            if inp.count() and inp.first.is_visible():
                inp.first.fill(val)
                return True
        except Exception:
            pass
        return False

    fill("Vorname", FORM["vorname"])
    fill("Nachname", FORM["nachname"])
    fill(r"E[-\s]?Mail\s*\*", FORM["email"])
    fill(r"E[-\s]?Mail.*Wiederholung", FORM["email"])
    fill("Telefonnummer", FORM["telefon"])

    # Geburtsdatum tek kutuysa onu, değilse TAG/Monat/Jahr kutularını doldur
    try:
        single = page.get_by_label(re.compile(r"Geburtsdatum", re.I))
        if single.count() and single.first.is_visible():
            single.first.fill(".".join(FORM["geburt"]))
        else:
            tg = page.get_by_label(re.compile(r"TAG", re.I))
            mo = page.get_by_label(re.compile(r"Monat", re.I))
            yr = page.get_by_label(re.compile(r"Jahr", re.I))
            if tg.count(): tg.first.fill(FORM["geburt"][0])
            if mo.count(): mo.first.fill(FORM["geburt"][1])
            if yr.count(): yr.first.fill(FORM["geburt"][2])
    except Exception:
        pass

    # --- RIZA KUTUSU: görünür alana getir, olmazsa JS ile tıkla ---
    try:
        cb = page.locator('input[name="agreementChecked"], input.required[name="agreementChecked"]')
        if cb.count():
            cb.first.scroll_into_view_if_needed()
            page.wait_for_timeout(120)
            try:
                cb.first.check(force=True)
            except Exception:
                # JS ile tıklama fallback (overlay/visibility sorunlarında)
                page.evaluate("""(sel)=>{
                    const el=document.querySelector(sel);
                    if(el){
                        el.scrollIntoView({block:'center'});
                        el.click();
                        el.dispatchEvent(new Event('input',{bubbles:true}));
                        el.dispatchEvent(new Event('change',{bubbles:true}));
                    }
                }""", 'input[name="agreementChecked"]')
        else:
            txt = page.get_by_text(re.compile(r"Ich willige ein.*verarbeitet werden", re.I | re.S))
            if txt.count():
                container = txt.first.locator("xpath=ancestor::label|ancestor::div")
                c2 = container.locator('input[type="checkbox"]')
                if c2.count():
                    c2.first.scroll_into_view_if_needed()
                    page.wait_for_timeout(120)
                    c2.first.check(force=True)
    except Exception as e:
        log(f"[WARN] Rıza kutusu işaretlenemedi: {e}")

def find_next_termin(page):
    # Örn: "Nächster Termin ab 15.10.2025, 09:30 Uhr"
    try:
        text = page.inner_text("body")
    except Exception:
        return None, None
    m = re.search(r"Nächster\s+Termin\s+ab\s+(\d{1,2}\.\d{1,2}\.\d{4})(?:,\s*(\d{1,2}:\d{2})\s*Uhr)?",
                  text, re.I | re.S)
    if not m:
        return None, None
    try:
        d_str, t_str = m.group(1), (m.group(2) or "")
        d_obj = datetime.strptime(d_str, "%d.%m.%Y").date()
        return d_obj, t_str
    except Exception:
        return None, None

# ===================== A N A   A K I Ş =====================

def check_once():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=False, slow_mo=800)
        context = browser.new_context(user_agent=UA)
        page = context.new_page()
        page.set_default_timeout(15000)

        # 1) Açılış
        page.goto(TARGET_URL, wait_until="domcontentloaded")
        close_dialogs(page)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(300)

        # 2) Abteilung Ausländerangelegenheiten
        if not click_by_text(page, UNIT_TEXT):
            context.close(); browser.close()
            raise AssertionError(f"Birim bulunamadı: {UNIT_TEXT}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(300)

        # 3) Row -> '+'
        if not click_plus_for_any_label(page):
            log("[ERR] '+' tıklanamadı (etiket varyantları veya iframe).")
            context.close(); browser.close()
            return None, None
        log("[OK] '+' başarıyla tıklandı.")
        page.wait_for_timeout(500)

        # 4) Weiter
        if not proceed_weiter(page):
            context.close(); browser.close()
            raise AssertionError("Weiter/Fortfahren butonu bulunamadı.")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(400)

        # 5) 'OK' (varsa)
        try:
            okbtn = page.get_by_role("button", name=re.compile(r"OK", re.I))
            if okbtn.count() and okbtn.first.is_visible():
                okbtn.first.click()
        except Exception:
            pass
        page.wait_for_timeout(200)

        # 6) Form doldur (ANREDE OLMADAN)
        fill_form(page)
        page.wait_for_timeout(200)

        # 7) Weiter (sonuç sayfasına)
        if not proceed_weiter(page):
            log("[WARN] İleri (Weiter) butonu görülemedi.")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(700)

        # 8) Randevu metnini yakala
        d, t = find_next_termin(page)

        context.close(); browser.close()
        return d, t

def main_loop():
    while True:
        try:
            found_d, found_t = check_once()
            last_d, last_t = load_state()
            today = date.today()
            window_end = today + timedelta(days=WINDOW_DAYS)

            in_window = (found_d is not None) and (today <= found_d <= window_end)
            changed = (found_d is not None) and (
                (last_d is None) or (found_d < last_d) or (found_d == last_d and (found_t or "") != (last_t or ""))
            )

            log(f"Sonuç: {found_d}, {found_t or ''} | önceki: {last_d}, {last_t or ''} | pencere_içi={in_window} değişti={changed}")

            if in_window and changed:
                subject = "[Mainz] Studium/Sprachkurs — Nächster Termin"
                when_txt = found_d.strftime("%d.%m.%Y") + (f", {found_t} Uhr" if found_t else "")
                body = (
                    f"Nächster Termin ab: {when_txt}\n\n"
                    f"{TARGET_URL}\n"
                    f"Pencere: bugün → {WINDOW_DAYS} gün\n"
                    f"Kaynak: Abteilung Ausländerangelegenheiten > Aufenthaltserlaubnis zum Studium/Sprachkurs"
                )
                send_mail(subject, body)
                save_state(found_d, found_t or "")

        except AssertionError as e:
            log(f"[ERROR] {e}")
        except PWTimeout:
            log("[WARN] Zaman aşımı, sonraki döngüde tekrar denenecek.")
        except Exception as e:
            log(f"[ERROR] {e}")

        # 15 dk + ufak jitter
        base = INTERVAL_MIN * 60
        jitter = random.randint(-120, 120)
        time.sleep(max(60, base + jitter))

if __name__ == "__main__":
    main_loop()