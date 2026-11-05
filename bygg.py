#!/usr/bin/env python3
"""bygg.py – nyckeltal ur de årsredovisningar som lämnats in digitalt till Bolagsverket.

Läser Bolagsverkets öppna bulkfiler (en zip per vecka med en årsredovisning i iXBRL per bolag)
och skriver nyckeltal.zip: en rad per bolag med det senaste räkenskapsåret. Utöver resultat och
balans tas tillgångar som visar vad bolaget äger (fastighet, maskiner, inventarier och fordon),
lager, kundfordringar, skulder till kreditinstitut och förra årets omsättning.

Inga personnamn tas med. Bara Pythons standardbibliotek.

  python3 bygg.py --forra forra --ut ut            bygger vidare på förra körningen
  python3 bygg.py --ut ut --lokal vecka.zip        läser en nedladdad veckofil (för prov)

--forra    mapp med förra körningens nyckeltal.zip och behandlade.txt
--ut       mapp där de nya filerna skrivs
--fran-ar  första inlämningsår som läses (standard 2025)
--minuter  hur länge bygget får hålla på innan det sparar och slutar (standard 320)
--max      högst så många veckofiler (för prov)
"""

import argparse
import datetime as dt
import io
import os
import re
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

BAS = os.environ.get("BOLAGSVERKET_BAS",
                     "https://vardefulla-datamangder.bolagsverket.se/arsredovisningar-bulkfiler")
PREFIX = "arsredovisningar/"

# (kolumn, element i den svenska taxonomin, typ). "period" gäller räkenskapsåret, "balans" dess
# sista dag och "forra" räkenskapsåret innan.
KOLUMNER = [
    ("nettoomsattning", "Nettoomsattning", "period"),
    ("nettoomsattning_fg", "Nettoomsattning", "forra"),
    ("rorelseresultat", "Rorelseresultat", "period"),
    ("resultat_efter_fin", "ResultatEfterFinansiellaPoster", "period"),
    ("arets_resultat", "AretsResultat", "period"),
    ("tillgangar", "Tillgangar", "balans"),
    ("eget_kapital", "EgetKapital", "balans"),
    ("soliditet", "Soliditet", "balans"),
    ("kassa_bank", "KassaBank", "balans"),
    ("kortfristiga_skulder", "KortfristigaSkulder", "balans"),
    ("langfristiga_skulder", "LangfristigaSkulder", "balans"),
    ("kreditinstitut_lang", "OvrigaLangfristigaSkulderKreditinstitut", "balans"),
    ("kreditinstitut_kort", "OvrigaKortfristigaSkulderKreditinstitut", "balans"),
    ("materiella", "MateriellaAnlaggningstillgangar", "balans"),
    ("byggnader_mark", "ByggnaderMark", "balans"),
    ("maskiner", "MaskinerAndraTekniskaAnlaggningar", "balans"),
    ("inventarier", "InventarierVerktygInstallationer", "balans"),
    ("varulager", "VarulagerMm", "balans"),
    ("kundfordringar", "Kundfordringar", "balans"),
    ("anstallda", "MedelantaletAnstallda", "period"),
    ("anstallda_fg", "MedelantaletAnstallda", "forra"),
    ("personalkostnader", "Personalkostnader", "period"),
]
RUBRIK = ["orgnr", "fran", "till", "undertecknad", "sate", "valuta"] + [k[0] for k in KOLUMNER]
PER_TAGG = {}
for _namn, _tagg, _typ in KOLUMNER:
    PER_TAGG.setdefault(_tagg, []).append((_namn, _typ))

FLAGGOR = re.S | re.I
CONTEXT_RE = re.compile(r"<(?:[\w-]+:)?context\b([^>]*)>(.*?)</(?:[\w-]+:)?context>", FLAGGOR)
UNIT_RE = re.compile(r"<(?:[\w-]+:)?unit\b([^>]*)>(.*?)</(?:[\w-]+:)?unit>", FLAGGOR)
TAL_RE = re.compile(r"<ix:nonFraction\b([^>]*?)(/>|>(.*?)</ix:nonFraction>)", FLAGGOR)
TEXT_RE = re.compile(r"<ix:nonNumeric\b([^>]*?)(/>|>(.*?)</ix:nonNumeric>)", FLAGGOR)
DATUM_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
TILLATNA_DIMENSIONER = re.compile(
    r"<[\w-]+:RedovisningInformation(JuridiskPerson|Generell)Segment\s*/>", re.I)


def attribut(text, namn):
    m = re.search(r"\s" + namn + r"\s*=\s*\"([^\"]*)\"", text, re.I)
    return m.group(1) if m else None


def ren_text(s):
    s = re.sub(r"<[^>]*>", "", s or "")
    for a, b in (("&nbsp;", " "), ("&#160;", " "), ("\xa0", " "), ("&amp;", "&"), ("&lt;", "<"),
                 ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'"), ("&apos;", "'")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def tolka_tal(text, format_, scale, sign):
    """Talet i ett ix:nonFraction, i kronor (eller antal/procent som bråk)."""
    t = ren_text(text)
    f = (format_ or "").lower()
    if "zero" in f or "dash" in f or t in ("-", "–", "—"):
        return 0.0
    komma = bool(re.search(r"comma(-?decimal)?$", f)) or "commadecimal" in f or "comma-decimal" in f
    if komma:
        s = re.sub(r"[^\d,]", "", t).replace(",", ".", 1).replace(",", "")
    else:
        s = re.sub(r"[^\d.]", "", t)
        if s.count(".") > 1:
            s = s.replace(".", "")
    if not re.search(r"\d", s):
        return None
    try:
        v = float(s) * 10 ** int(scale or 0)
    except ValueError:
        return None
    return -v if sign == "-" else v


def las_kontexter(html):
    ut = {}
    for m in CONTEXT_RE.finditer(html):
        cid = attribut(m.group(1), "id")
        k = m.group(2)
        start = re.search(r"<(?:[\w-]+:)?startDate\b[^>]*>\s*(\d{4}-\d{2}-\d{2})", k, re.I)
        slut = re.search(r"<(?:[\w-]+:)?(?:endDate|instant)\b[^>]*>\s*(\d{4}-\d{2}-\d{2})", k, re.I)
        dim = False
        for d in re.finditer(r"<(?:[\w-]+:)?(segment|scenario)\b[^>]*>(.*?)</(?:[\w-]+:)?\1>", k, FLAGGOR):
            rest = TILLATNA_DIMENSIONER.sub("", d.group(2))
            if re.search(r"<[A-Za-z]", rest):
                dim = True
        ut[cid] = (start.group(1) if start else None, slut.group(1) if slut else None, dim)
    return ut


def las_texter(html):
    ut = {}
    for m in TEXT_RE.finditer(html):
        namn = (attribut(m.group(1), "name") or "").split(":")[-1]
        ut.setdefault(namn, []).append(ren_text(m.group(3) or ""))
    return ut


def dagen_fore(datum):
    return (dt.date.fromisoformat(datum) - dt.timedelta(days=1)).isoformat()


def las_rapport(html, filnamn=""):
    """En rad (dict) med nyckeltalen ur en årsredovisning, eller None."""
    txt = las_texter(html)

    def forsta(namn):
        return next((v for v in txt.get(namn, []) if v), "")

    orgnr = re.sub(r"\D", "", forsta("Organisationsnummer"))
    if not re.fullmatch(r"\d{10}", orgnr):
        m = re.search(r"(\d{10})_", str(filnamn))
        orgnr = m.group(1) if m else ""
    till = (DATUM_RE.search(forsta("RakenskapsarSistaDag")) or [None])[0]
    if not orgnr or not till:
        return None
    fran = (DATUM_RE.search(forsta("RakenskapsarForstaDag")) or [""])[0]
    datum = []
    for namn, varden in txt.items():
        if namn.startswith("Undertecknande") and "Datum" in namn:
            datum += [d for v in varden for d in DATUM_RE.findall(v)]
    undertecknad = max(datum) if datum else ""
    forra_slut = dagen_fore(fran) if fran else None

    ktx = las_kontexter(html)
    enheter = {}
    for m in UNIT_RE.finditer(html):
        v = re.search(r"iso4217:([A-Z]{3})", m.group(2))
        if v:
            enheter[attribut(m.group(1), "id")] = v.group(1)

    def passar(cid, typ):
        k = ktx.get(cid)
        if not k or k[2]:
            return False
        start, slut, _ = k
        if typ == "balans":
            return slut == till
        if typ == "period":
            return slut == till and bool(start) and (not fran or start == fran)
        return forra_slut is not None and slut == forra_slut and bool(start)

    basta = {}  # kolumn -> (skala, värde)
    valuta = ""
    for m in TAL_RE.finditer(html):
        if m.group(3) is None:
            continue
        a = m.group(1)
        tagg = (attribut(a, "name") or "").split(":")[-1]
        if tagg not in PER_TAGG:
            continue
        cid = attribut(a, "contextRef")
        for kol, typ in PER_TAGG[tagg]:
            if not passar(cid, typ):
                continue
            skala = int(attribut(a, "scale") or 0)
            if kol in basta and basta[kol][0] <= skala:
                continue
            v = tolka_tal(m.group(3), attribut(a, "format"), skala, attribut(a, "sign"))
            if v is None:
                continue
            basta[kol] = (skala, v)
            if not valuta and enheter.get(attribut(a, "unitRef")):
                valuta = enheter[attribut(a, "unitRef")]

    if not basta:
        return None
    rad = {"orgnr": orgnr, "fran": fran, "till": till, "undertecknad": undertecknad,
           "sate": forsta("ForetagetsSate")[:80], "valuta": "" if valuta in ("", "SEK") else valuta}
    for kol, _tagg, _typ in KOLUMNER:
        if kol not in basta:
            rad[kol] = ""
            continue
        v = basta[kol][1]
        if kol == "soliditet":
            rad[kol] = "%.1f" % (v * 100 if abs(v) <= 1.5 else v)
        elif kol.startswith("anstallda"):
            rad[kol] = ("%.1f" % v).rstrip("0").rstrip(".")
        else:
            rad[kol] = str(int(round(v)))
    if not rad["soliditet"] and rad["eget_kapital"] and rad["tillgangar"] not in ("", "0"):
        rad["soliditet"] = "%.1f" % (100 * float(rad["eget_kapital"]) / float(rad["tillgangar"]))
    return rad


def rad_text(rad):
    return "\t".join(re.sub(r"[\t\r\n]+", " ", str(rad.get(k, ""))) for k in RUBRIK)


def ar_nyare(ny, gammal):
    """ny och gammal är (till, undertecknad). Senare år går före, sedan senast undertecknad."""
    if gammal is None:
        return True
    if ny[0] != gammal[0]:
        return ny[0] > gammal[0]
    return (ny[1] or "") >= (gammal[1] or "")


def las_inlamning(zf_eller_filer, namn):
    """Raderna ur en inlämning (en zip med xhtml, eller en xhtml direkt)."""
    rader = []
    for fnamn, hamta in zf_eller_filer:
        if re.search(r"\.x?html?$", fnamn, re.I):
            rad = las_rapport(hamta().decode("utf-8", "replace"), namn)
            if rad:
                rader.append(rad)
    return rader


def las_veckofil(sokvag, bolag):
    antal = fel = 0
    with zipfile.ZipFile(sokvag) as z:
        for info in z.infolist():
            try:
                if info.filename.lower().endswith(".zip"):
                    with zipfile.ZipFile(io.BytesIO(z.read(info))) as inre:
                        filer = [(i.filename, (lambda i=i: inre.read(i))) for i in inre.infolist()]
                        rader = las_inlamning(filer, info.filename)
                else:
                    rader = las_inlamning([(info.filename, lambda: z.read(info))], info.filename)
                for rad in rader:
                    antal += 1
                    gammal = bolag.get(rad["orgnr"])
                    if ar_nyare((rad["till"], rad["undertecknad"]), gammal[:2] if gammal else None):
                        bolag[rad["orgnr"]] = (rad["till"], rad["undertecknad"], rad_text(rad))
            except Exception as e:  # en trasig inlämning ska inte stoppa bygget
                fel += 1
                if fel <= 3:
                    print("  %s: %s" % (info.filename, e), file=sys.stderr)
    return antal, fel


def hamta(url, mal=None, forsok=4):
    for i in range(1, forsok + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "kreditpartner-nyckeltal"})
            with urllib.request.urlopen(req, timeout=600) as svar:
                if mal is None:
                    return svar.read()
                with open(mal, "wb") as f:
                    while True:
                        bit = svar.read(1 << 20)
                        if not bit:
                            break
                        f.write(bit)
                return mal
        except Exception as e:
            if i >= forsok:
                raise RuntimeError("%s: %s" % (url, e))
            time.sleep(30 * i)


def lista_veckofiler():
    ut, markor = [], ""
    while True:
        url = BAS + "?prefix=" + urllib.parse.quote(PREFIX, safe="") + "&marker=" + urllib.parse.quote(markor, safe="")
        xml = hamta(url).decode("utf-8")
        poster = re.findall(r"<Contents>(.*?)</Contents>", xml, re.S)
        for p in poster:
            def falt(t):
                m = re.search(r"<%s>([^<]*)</%s>" % (t, t), p)
                return m.group(1) if m else ""
            ut.append((falt("Key"), falt("ETag").replace("&#34;", "").replace('"', "")))
        if "<IsTruncated>true</IsTruncated>" not in xml or not poster or ut[-1][0] == markor:
            break
        markor = ut[-1][0]
    return sorted(set(v for v in ut if v[0].endswith(".zip")))


def las_forra(mapp, bolag, behandlade):
    zp = os.path.join(mapp, "nyckeltal.zip")
    if os.path.exists(zp):
        with zipfile.ZipFile(zp) as z:
            with z.open("nyckeltal.txt") as f:
                rubrik = None
                for rad in io.TextIOWrapper(f, encoding="utf-8"):
                    rad = rad.rstrip("\n")
                    if rubrik is None:
                        rubrik = rad.split("\t")
                        continue
                    falt = dict(zip(rubrik, rad.split("\t")))
                    if falt.get("orgnr"):
                        bolag[falt["orgnr"]] = (falt.get("till", ""), falt.get("undertecknad", ""),
                                                rad_text(falt))
        print("Förra filen: %d bolag" % len(bolag))
    bp = os.path.join(mapp, "behandlade.txt")
    if os.path.exists(bp):
        for rad in open(bp, encoding="utf-8"):
            if "\t" in rad:
                k, e = rad.rstrip("\n").split("\t", 1)
                behandlade[k] = e
        print("Behandlade veckofiler: %d" % len(behandlade))


def skriv_ut(mapp, bolag, behandlade, klar, kvar):
    os.makedirs(mapp, exist_ok=True)
    with zipfile.ZipFile(os.path.join(mapp, "nyckeltal.zip"), "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        with z.open("nyckeltal.txt", "w") as f:
            f.write(("\t".join(RUBRIK) + "\n").encode("utf-8"))
            for orgnr in sorted(bolag):
                f.write((bolag[orgnr][2] + "\n").encode("utf-8"))
    with open(os.path.join(mapp, "behandlade.txt"), "w", encoding="utf-8") as f:
        for k in sorted(behandlade):
            f.write("%s\t%s\n" % (k, behandlade[k]))
    with open(os.path.join(mapp, "status.txt"), "w") as f:
        f.write("klar\n" if klar else "ofullstandig\n")
    senaste = max(behandlade) if behandlade else "ingen"
    with open(os.path.join(mapp, "notering.md"), "w", encoding="utf-8") as f:
        f.write("Byggd %s. %d bolag.\n\nSenast inlästa veckofil: %s.\n" % (
            dt.date.today().isoformat(), len(bolag), senaste.replace(PREFIX, "")))
        if not klar:
            f.write("\nOfullständig: %d veckofiler återstår och läses vid nästa körning.\n" % kvar)
        f.write("\nKälla: Bolagsverket, digitalt inlämnade årsredovisningar (värdefulla datamängder).\n")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--forra")
    p.add_argument("--ut", default="ut")
    p.add_argument("--fran-ar", type=int, default=2025)
    p.add_argument("--minuter", type=float, default=320)
    p.add_argument("--max", type=int, default=10 ** 9)
    p.add_argument("--lokal", action="append", default=[])
    a = p.parse_args()
    slut = time.time() + a.minuter * 60

    bolag, behandlade = {}, {}
    if a.forra:
        las_forra(a.forra, bolag, behandlade)

    klar, kvar = True, 0
    if a.lokal:
        for fil in a.lokal:
            antal, fel = las_veckofil(fil, bolag)
            print("%s: %d årsredovisningar, %d fel" % (fil, antal, fel))
    else:
        alla = lista_veckofiler()
        att_lasa = []
        for key, etag in alla:
            m = re.search(r"/(\d{4})/", key)
            if m and int(m.group(1)) >= a.fran_ar and behandlade.get(key) != etag:
                att_lasa.append((key, etag))
        print("Veckofiler hos Bolagsverket: %d, att läsa: %d" % (len(alla), len(att_lasa)))
        lasta = 0
        with tempfile.TemporaryDirectory() as tmp:
            for key, etag in att_lasa[: a.max]:
                if time.time() >= slut:
                    print("Tiden är slut. Resten tas vid nästa körning.")
                    break
                fil = os.path.join(tmp, "vecka.zip")
                try:
                    hamta(BAS + "/" + key, fil)
                except RuntimeError as e:
                    print(e)
                    if not lasta:
                        raise
                    print("Resten tas vid nästa körning.")
                    break
                antal, fel = las_veckofil(fil, bolag)
                behandlade[key] = etag
                lasta += 1
                print("%s: %d årsredovisningar, %d fel, %d bolag" % (key, antal, fel, len(bolag)))
        kvar = len(att_lasa) - lasta
        klar = kvar == 0

    skriv_ut(a.ut, bolag, behandlade, klar, kvar)
    print("%s: %d bolag" % ("Klar" if klar else "Ofullständig", len(bolag)))


if __name__ == "__main__":
    main()
