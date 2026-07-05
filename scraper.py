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

def main():
    items = load_seed()
    # ---- เพิ่มตัวดึงสดของแต่ละแหล่งตรงนี้ (ตอนนี้ทำศิริราชเป็นตัวอย่างจริง) ----
    enrich_siriraj(items)
    # TODO: เพิ่ม enrich_rajavithi(), enrich_camphub(), ฯลฯ ตามต้องการ

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
