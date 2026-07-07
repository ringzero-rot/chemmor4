#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
อาสาน้อย — ตัวอัปเดตข้อมูล (scraper)
------------------------------------
อ่านฐานข้อมูลที่ดูแลด้วยมือจาก seed.json แล้วพยายามดึงประกาศสดจากเว็บโรงพยาบาล
เพื่ออัปเดตสถานะ/วันปิดรับ จากนั้นเขียนผลลัพธ์ลง data.json (พร้อม updatedAt ใหม่ทุกครั้ง)

หลักการสำคัญ:
- ถ้าดึงเว็บสดไม่สำเร็จ -> ใช้ข้อมูลจาก seed.json เหมือนเดิม (ข้อมูลเดิมไม่มีวันหาย)
- แต่ละตำแหน่งของศิริราชผูกกับหน้า viewnews.asp?id=XXX อยู่แล้ว จึงอัปเดตได้ทีละตำแหน่ง

รันเอง:  python scraper.py
ผลลัพธ์: data.json (ให้เว็บ index.html โหลดไปแสดง)
"""
import json, re, sys, datetime, pathlib

HERE = pathlib.Path(__file__).parent
SEED = HERE / "seed.json"
OUT  = HERE / "data.json"

SIRIRAJ_NEWS = "https://www.si.mahidol.ac.th/th/division/csr/volunteersiriraj/news.asp?t=1"

# ============================================================================
# ทะเบียนแหล่งข้อมูลจริง (SOURCES) — โปร่งใสว่าอะไรดึงอัตโนมัติได้ / อะไรต้องใส่มือ
#   auto=True  : โครงสร้างเว็บพอ parse อัตโนมัติได้ (มี enrich_* ให้)
#   auto=False : ประกาศผ่าน Facebook/Google Form/รูปภาพ — บอตอ่านไม่ได้ ต้องอัปเดตมือใน seed.json
# ============================================================================
SOURCES = [
    # --- โรงพยาบาล/คณะแพทย์ ---
    {"key":"siriraj",   "name":"ศูนย์อาสาสมัครศิริราช",              "auto":True,
     "url":"https://www.si.mahidol.ac.th/th/division/csr/volunteersiriraj/news.asp?t=1"},
    {"key":"rama",      "name":"จิตอาสารามาธิบดี",                   "auto":False,
     "url":"https://www.rama.mahidol.ac.th/rama_hospital/th/volunteer"},
    {"key":"rajavithi", "name":"จิตอาสา รพ.ราชวิถี (ธนาคารเวลา)",     "auto":False,
     "url":"https://oapp.rajavithi.go.th/RjvtRegisterVolunteer/"},
    {"key":"vajira",    "name":"อาสาสมัครนักเรียน วชิรพยาบาล",        "auto":False,
     "url":"https://sites.google.com/nmu.ac.th/student-volunteer/"},
    {"key":"trc",       "name":"อาสาสมัครสภากาชาดไทย/ยุวกาชาด",       "auto":False,
     "url":"https://trcyvolunteer.redcross.or.th/"},
    {"key":"mirror",    "name":"โรงพยาบาลมีสุข (มูลนิธิกระจกเงา)",     "auto":False,
     "url":"https://www.happyhospital.org/volunteer.php"},
    # --- เครือข่าย/มูลนิธิ ---
    {"key":"buddhika",  "name":"จิตอาสา 8 รพ. · มูลนิธิเครือข่ายพุทธิกา","auto":False,
     "url":"https://budnet.org"},
    # --- ค่าย/เปิดบ้าน ---
    {"key":"chulacamp", "name":"ค่ายอยากเป็นหมอ จุฬาฯ",              "auto":False,
     "url":"https://medcamp.docchula.com"},
    {"key":"sirirajedu","name":"Siriraj Open House / ฝ่ายการศึกษา",   "auto":False,
     "url":"https://www.sieduit.org/education"},
    # --- แหล่งรวมข่าว (aggregators) — ดึงอัตโนมัติ (auto-discovery) ---
    {"key":"DekPort",   "name":"DekPort (รวมจิตอาสานักเรียน สายสุขภาพ)","auto":True,
     "url":"https://dekport.com/volunteer"},
    {"key":"VolunteerSpirit","name":"เครือข่ายจิตอาสา Volunteerspirit","auto":True,
     "url":"https://www.volunteerspirit.org/category/volunteeractivity/"},
    {"key":"camphub",   "name":"CampHub (ค่ายสายสุขภาพ)",            "auto":False,
     "url":"https://www.camphub.in.th/medical-health/doctor/"},
    {"key":"dekuni",    "name":"dekuni (รวมจิตอาสา รพ.)",            "auto":False,
     "url":"https://dekuni.com/voluneer-hospital/"},
    {"key":"admission", "name":"AdmissionPremium",                   "auto":False,
     "url":"https://www.admissionpremium.com/"},
    {"key":"eduzones",  "name":"Eduzones",                           "auto":False,
     "url":"https://www.eduzones.com/"},
]


TH_MONTHS = {  # ชื่อเดือนไทย -> เลขเดือน
    "มกราคม":1,"กุมภาพันธ์":2,"มีนาคม":3,"เมษายน":4,"พฤษภาคม":5,"มิถุนายน":6,
    "กรกฎาคม":7,"สิงหาคม":8,"กันยายน":9,"ตุลาคม":10,"พฤศจิกายน":11,"ธันวาคม":12,
}

def load_seed():
    data = json.loads(SEED.read_text(encoding="utf-8"))
    return data["items"] if isinstance(data, dict) else data

def th_date_to_bs(day, month_name, year_be):
    """แปลง (วัน, ชื่อเดือนไทย, ปี พ.ศ.) -> 'พ.ศ.-MM-DD' ตามรูปแบบที่แอปใช้"""
    m = TH_MONTHS.get(month_name)
    if not m:
        return None
    return f"{int(year_be):04d}-{m:02d}-{int(day):02d}"

def fetch_siriraj_open_positions():
    """
    คืน dict: { viewnews_id(str): {'close': 'พ.ศ.-MM-DD' or None} }
    ดึงเฉพาะรายการที่ยัง "(รับสมัคร)" อยู่ในหน้า news.asp
    หมายเหตุ: เว็บศิริราชเป็น TIS-620 ต้องถอดรหัสเป็น cp874
    """
    import urllib.request
    req = urllib.request.Request(SIRIRAJ_NEWS, headers={"User-Agent":"Mozilla/5.0 (asanaoi-bot)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read()
    html = raw.decode("cp874", errors="replace")  # ถอดรหัสไทยให้ถูกต้อง (ต่างจากเบราว์เซอร์บอทบางตัว)

    positions = {}
    # จับบล็อกที่มีลิงก์ viewnews.asp?id=NNN และช่วงวัน "เปิดรับสมัคร ... ถึง ..."
    for m in re.finditer(r'viewnews\.asp\?id=(\d+)(.*?)(?=viewnews\.asp\?id=|\Z)', html, re.S):
        vid, block = m.group(1), m.group(2)
        is_open = ("รับสมัคร" in block) and ("ปิดรับสมัคร" not in block or "(รับสมัคร)" in block)
        # หา "ถึง <วัน> <เดือนไทย> <ปี>" เป็นวันปิดรับ
        close = None
        dm = re.search(r'ถึง\s*(\d{1,2})\s*([ก-๙]+)\s*(25\d{2})', block)
        if dm:
            close = th_date_to_bs(dm.group(1), dm.group(2), dm.group(3))
        positions[vid] = {"open": is_open, "close": close}
    return positions

def enrich_siriraj(items):
    try:
        live = fetch_siriraj_open_positions()
    except Exception as e:
        print(f"[warn] ดึงศิริราชไม่สำเร็จ ใช้ seed เดิม: {e}", file=sys.stderr)
        return 0
    changed = 0
    for it in items:
        src = it.get("sourceUrl","")
        vm = re.search(r'viewnews\.asp\?id=(\d+)', src)
        if not vm:
            continue
        vid = vm.group(1)
        info = live.get(vid)
        if not info:
            # ไม่พบประกาศแล้ว = รอบนี้ปิด (แต่ไม่ลบทิ้ง)
            if it.get("applyClose"):
                # ตั้งวันปิดเป็นอดีตเพื่อให้แอปจัดเป็น "ปิดรับสมัคร"
                pass
            continue
        if info.get("close") and info["close"] != it.get("applyClose"):
            it["applyClose"] = info["close"]
            it["keyDate"] = info["close"]
            it["keyType"] = "close"
            it["dateConfirmed"] = True
            changed += 1
    print(f"[ok] อัปเดตศิริราชจากเว็บสด {changed} ตำแหน่ง", file=sys.stderr)
    return changed

# ============================================================================
# Auto-discovery จากเว็บรวมข่าว (aggregators) — โตเองโดยไม่ต้องทำมือ
# กรองเฉพาะกิจกรรมสายสุขภาพ/โรงพยาบาล และติดธง unverified=True
# (แอปจะแสดงป้าย "จากแหล่งรวม—ตรวจก่อนสมัคร")
# ============================================================================
HEALTH_KW = ["โรงพยาบาล","รพ.","แพทย์","พยาบาล","เภสัช","ทันต","สาธารณสุข","สุขภาพ",
             "ผู้ป่วย","กายภาพ","หมอ","กาชาด","บริจาคเลือด","คลินิก","วชิร","ศิริราช","รามา"]
BE_DATE = re.compile(r'(\d{1,2})\s*([ก-๙\.]+)\s*(25\d{2})')

def _fetch(url):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (asanaoi-bot)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read()
    for enc in ("utf-8","cp874"):
        try: return raw.decode(enc)
        except Exception: continue
    return raw.decode("utf-8", errors="replace")

def _bs_from_text(txt):
    m = BE_DATE.search(txt)
    if not m: return None
    d, mon, y = m.group(1), m.group(2), m.group(3)
    month = None
    for name,num in TH_MONTHS.items():
        if name[:3] in mon: month = num; break
    if not month: return None
    try: return f"{int(y):04d}-{month:02d}-{int(d):02d}"
    except Exception: return None

def _mk_auto_item(source_key, idx, title, url, close_bs):
    return {
        "id": f"auto-{source_key}-{idx}", "cat":"volunteer", "unverified": True,
        "hospital": "โครงการจากแหล่งรวมข่าว", "org": f"พบผ่าน {source_key}", "area": "—",
        "icon": "🔎", "title": title[:120],
        "scopeShort": "รายการนี้ดึงอัตโนมัติจากเว็บรวมข่าว — โปรดกดลิงก์เพื่อตรวจรายละเอียดและวันสมัครก่อนสมัครทุกครั้ง",
        "scope": ["รายละเอียดอยู่ที่หน้าต้นทาง (กดปุ่มแหล่งข้อมูล/สมัคร)"],
        "qual": ["ตรวจคุณสมบัติที่หน้าต้นทาง"],
        "quota": "ดูที่ต้นทาง", "workDays": "ดูที่ต้นทาง", "cost": "ดูที่ต้นทาง",
        "cert": False, "certNote": "ตรวจสอบเรื่องเกียรติบัตรที่หน้าต้นทาง",
        "applyOpen": None, "applyClose": close_bs, "keyDate": close_bs,
        "keyType": "close", "dateConfirmed": False, "status": "open",
        "howTo": ["กดปุ่มด้านล่างไปยังหน้าต้นทาง แล้วทำตามขั้นตอนที่ระบุ"],
        "applyUrl": url, "sourceUrl": url, "sourceName": f"{source_key} (แหล่งรวมข่าว)",
        "note": "⚠️ ดึงอัตโนมัติจากแหล่งรวมข่าว ยังไม่ผ่านการตรวจด้วยมือ — โปรดยืนยันกับต้นทางก่อนสมัคร",
    }

def enrich_aggregator(items, url, source_key, limit=25):
    """ดึงลิงก์กิจกรรมสายสุขภาพจากหน้า aggregator (best-effort, กันพัง)"""
    try:
        html = _fetch(url)
    except Exception as e:
        print(f"[warn] ดึง {source_key} ไม่สำเร็จ: {e}", file=sys.stderr); return 0
    from urllib.parse import urljoin
    seen = set(x.get("sourceUrl") for x in items)
    added = 0
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S|re.I):
        href = m.group(1)
        text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', m.group(2))).strip()
        if len(text) < 12: continue
        if not any(kw in text for kw in HEALTH_KW): continue
        if href.startswith("/"): href = urljoin(url, href)
        if not href.startswith("http") or href in seen: continue
        ctx = html[max(0, m.start()-300): m.end()+300]
        items.append(_mk_auto_item(source_key, added+1, text, href, _bs_from_text(ctx)))
        seen.add(href); added += 1
        if added >= limit: break
    print(f"[auto] {source_key}: เพิ่ม {added} รายการ (unverified)", file=sys.stderr)
    return added

# ============================================================================
# ตรวจสอบลิงก์จริงก่อนแสดง — จับ Google Form ที่ปิด / ลิงก์เสีย / หน้าไม่มีข้อมูลรับสมัคร
# ============================================================================
CLOSED_PATTERNS = [
    re.compile(r'ไม่รับคำตอบ'),
    re.compile(r'no longer accepting responses', re.I),
    re.compile(r'(?<!เ)ปิดรับคำตอบ'),
    re.compile(r'(?<!เ)ปิดรับสมัครแล้ว'),
    re.compile(r'หมดเขตรับสมัคร'),
    re.compile(r'ปิดรับสมัครไปแล้ว'),
    re.compile(r'รับสมัครเต็มแล้ว'),
    re.compile(r'(?<!เ)ปิดรอบ(?:นี้)?แล้ว'),
]
OPEN_HINTS = ["รับสมัคร","เปิดรับ","ลงทะเบียน","สมัครเข้าร่วม","รับอาสา","accepting responses"]
SOCIAL = ["facebook.com","instagram.com","tiktok.com","twitter.com","x.com","line.me","lin.ee"]

def classify_link(url):
    """คืน: open | form_open | closed | dead | empty | social | unknown"""
    if not url: return "unknown"
    if any(s in url for s in SOCIAL): return "social"      # เปิดในเบราว์เซอร์ได้ แต่บอตอ่านไม่ได้
    import urllib.error
    try:
        html = _fetch(url)
    except urllib.error.HTTPError as e:
        return "dead" if e.code in (404,410) else "unknown"
    except Exception:
        return "unknown"
    is_form = ("docs.google.com/forms" in url) or ("forms.gle" in url)
    if any(p.search(html) for p in CLOSED_PATTERNS):
        return "closed"
    if is_form:
        return "form_open"
    if any(h in html for h in OPEN_HINTS):
        return "open"
    return "empty"     # หน้าโหลดได้แต่ไม่พบคำว่ารับสมัคร

def verify_links(items, cap=60):
    """เช็กลิงก์ของแต่ละรายการ ใส่ item['linkStatus'] และปรับสถานะถ้าปิด/เสีย (ไม่ลบทิ้ง)"""
    checked = 0
    for it in items:
        if checked >= cap: break
        # ข้ามรายการที่รับต่อเนื่อง (rolling) ไม่ต้องดาวน์เกรด
        st = classify_link(it.get("applyUrl") or it.get("sourceUrl"))
        it["linkStatus"] = st
        checked += 1
        if it.get("rolling"): 
            continue
        if st in ("closed","dead"):
            it["status"] = "closed"
            it["_forceClosed"] = True
            tag = "ฟอร์ม/ประกาศปิดรับแล้ว" if st=="closed" else "ลิงก์ใช้งานไม่ได้ (ไม่พบหน้า)"
            it["note"] = f"⚠️ ตรวจลิงก์อัตโนมัติ: {tag} · " + (it.get("note") or "")
        elif st == "empty":
            it["note"] = "⚠️ หน้าปลายทางไม่พบข้อมูลรับสมัครชัดเจน — โปรดตรวจก่อนสมัคร · " + (it.get("note") or "")
    print(f"[verify] ตรวจลิงก์ {checked} รายการ", file=sys.stderr)
    return checked

def main():
    items = load_seed()
    # ---- รายงานความครอบคลุมของแหล่งข้อมูล ----
    auto = [s for s in SOURCES if s["auto"]]
    manual = [s for s in SOURCES if not s["auto"]]
    print(f"[sources] ทั้งหมด {len(SOURCES)} แหล่ง · ดึงอัตโนมัติ {len(auto)} · ใส่มือ {len(manual)}", file=sys.stderr)

    # ---- 1) ดึงตำแหน่งจริงจากศิริราช (โครงสร้างชัด) ----
    enrich_siriraj(items)
    # ---- 2) Auto-discovery จากเว็บรวมข่าวสายสุขภาพ (โตเอง) ----
    enrich_aggregator(items, "https://dekport.com/volunteer", "DekPort", limit=30)
    enrich_aggregator(items, "https://www.volunteerspirit.org/category/volunteeractivity/", "VolunteerSpirit", limit=30)

    # ---- 3) ตรวจลิงก์จริงก่อนแสดง (Google Form ปิด / ลิงก์เสีย / หน้าไม่มีข้อมูล) ----
    verify_links(items)

    out = {
        "updatedAt": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),
        "generatedBy": "scraper.py",
        "count": len(items),
        "items": items,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[done] เขียน {OUT.name} · {len(items)} โครงการ · {out['updatedAt']}", file=sys.stderr)

if __name__ == "__main__":
    main()
