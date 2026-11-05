#!/usr/bin/env python3
"""Tester för bygg.py utan internet. Kör: python3 test_bygg.py"""

import io
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HAR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HAR)
import bygg  # noqa: E402


def rapport(orgnr="5591234567", fran="2025-01-01", till="2025-12-31", underskrift="2026-03-10",
            oms="8 400 000", oms_fg="7 000 000", byggnad="1 900", extra=""):
    """En liten påhittad årsredovisning i iXBRL med samma uppbyggnad som Bolagsverkets."""
    fg_fran = "2024-01-01"
    fg_till = "2024-12-31"
    return f"""<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"><body>
<ix:header><ix:resources>
<xbrli:context id="p0"><xbrli:entity><xbrli:identifier scheme="x">{orgnr}</xbrli:identifier></xbrli:entity>
<xbrli:period><xbrli:startDate>{fran}</xbrli:startDate><xbrli:endDate>{till}</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="p1"><xbrli:entity><xbrli:identifier scheme="x">{orgnr}</xbrli:identifier></xbrli:entity>
<xbrli:period><xbrli:startDate>{fg_fran}</xbrli:startDate><xbrli:endDate>{fg_till}</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="b0"><xbrli:entity><xbrli:identifier scheme="x">{orgnr}</xbrli:identifier></xbrli:entity>
<xbrli:period><xbrli:instant>{till}</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="b1"><xbrli:entity><xbrli:identifier scheme="x">{orgnr}</xbrli:identifier></xbrli:entity>
<xbrli:period><xbrli:instant>{fg_till}</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="b0_koncern"><xbrli:entity><xbrli:identifier scheme="x">{orgnr}</xbrli:identifier>
<xbrli:segment><xbrldi:explicitMember dimension="se-gen-base:Koncern">se-mem-base:KoncernMember</xbrldi:explicitMember></xbrli:segment>
</xbrli:entity><xbrli:period><xbrli:instant>{till}</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="b0_jp"><xbrli:entity><xbrli:identifier scheme="x">{orgnr}</xbrli:identifier>
<xbrli:segment><se-gen-base:RedovisningInformationJuridiskPersonSegment/></xbrli:segment>
</xbrli:entity><xbrli:period><xbrli:instant>{till}</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:unit id="SEK"><xbrli:measure>iso4217:SEK</xbrli:measure></xbrli:unit>
</ix:resources></ix:header>
<p>Org.nr <ix:nonNumeric name="se-cd-base:Organisationsnummer" contextRef="p0">{orgnr[:6]}-{orgnr[6:]}</ix:nonNumeric></p>
<ix:nonNumeric name="se-cd-base:RakenskapsarForstaDag" contextRef="p0">{fran}</ix:nonNumeric>
<ix:nonNumeric name="se-cd-base:RakenskapsarSistaDag" contextRef="p0">{till}</ix:nonNumeric>
<ix:nonNumeric name="se-gen-base:ForetagetsSate" contextRef="p0">Västerås</ix:nonNumeric>
<ix:nonNumeric name="se-gen-base:UndertecknandeArsredovisningDatum" contextRef="p0">{underskrift}</ix:nonNumeric>
<td><ix:nonFraction name="se-gen-base:Nettoomsattning" contextRef="p0" unitRef="SEK" scale="3" format="ixt:numspacecomma">8 400</ix:nonFraction></td>
<td><ix:nonFraction name="se-gen-base:Nettoomsattning" contextRef="p0" unitRef="SEK" scale="0" format="ixt:numspacecomma">{oms}</ix:nonFraction></td>
<td><ix:nonFraction name="se-gen-base:Nettoomsattning" contextRef="p1" unitRef="SEK" scale="0" format="ixt:numspacecomma">{oms_fg}</ix:nonFraction></td>
<td><ix:nonFraction name="se-gen-base:ResultatEfterFinansiellaPoster" contextRef="p0" unitRef="SEK" scale="0" sign="-" format="ixt:numspacecomma">120 000</ix:nonFraction></td>
<td><ix:nonFraction name="se-gen-base:ByggnaderMark" contextRef="b0" unitRef="SEK" scale="3" format="ixt:numspacecomma">{byggnad}</ix:nonFraction></td>
<td><ix:nonFraction name="se-gen-base:ByggnaderMark" contextRef="b1" unitRef="SEK" scale="3" format="ixt:numspacecomma">2 000</ix:nonFraction></td>
<td><ix:nonFraction name="se-gen-base:Tillgangar" contextRef="b0_koncern" unitRef="SEK" scale="0" format="ixt:numspacecomma">99 000 000</ix:nonFraction></td>
<td><ix:nonFraction name="se-gen-base:Tillgangar" contextRef="b0_jp" unitRef="SEK" scale="0" format="ixt:numspacecomma">6 000 000</ix:nonFraction></td>
<td><ix:nonFraction name="se-gen-base:EgetKapital" contextRef="b0" unitRef="SEK" scale="0" format="ixt:numspacecomma">1 500 000</ix:nonFraction></td>
<td><ix:nonFraction name="se-gen-base:VarulagerMm" contextRef="b0" unitRef="SEK" scale="0" format="ixt:fixed-zero">-</ix:nonFraction></td>
<td><ix:nonFraction name="se-gen-base:MedelantaletAnstallda" contextRef="p0" unitRef="antal" scale="0" format="ixt:numdotdecimal">7.5</ix:nonFraction></td>
{extra}
</body></html>"""


def veckofil(rapporter):
    """Bolagsverkets format: en zip per vecka med en zip per inlämning."""
    ut = io.BytesIO()
    with zipfile.ZipFile(ut, "w") as z:
        for i, (orgnr, html) in enumerate(rapporter):
            inre = io.BytesIO()
            with zipfile.ZipFile(inre, "w") as zi:
                zi.writestr("arsredovisning.xhtml", html)
            z.writestr("%s_%d.zip" % (orgnr, i), inre.getvalue())
    return ut.getvalue()


def main():
    steg = [0]

    def ok(text):
        steg[0] += 1
        print("OK %2d  %s" % (steg[0], text))

    t = bygg.tolka_tal
    assert t("1 234 567", "ixt:numspacecomma", 0, None) == 1234567
    assert t("29,8", "ixt:numcomma", -2, None) == 29.8 / 100
    assert t("1,234.5", "ixt:numcommadot", 0, None) == 1234.5
    assert t("1.234,5", "ixt:numdotcomma", 0, None) == 1234.5
    assert t("–", "ixt:numspacecomma", 0, None) == 0
    assert t("12", "", 3, "-") == -12000
    assert t("", "ixt:numspacecomma", 0, None) is None
    ok("talformat tolkas rätt")

    r = bygg.las_rapport(rapport())
    assert r["orgnr"] == "5591234567" and r["till"] == "2025-12-31" and r["fran"] == "2025-01-01"
    assert r["nettoomsattning"] == "8400000" and r["nettoomsattning_fg"] == "7000000"
    assert r["resultat_efter_fin"] == "-120000"
    assert r["byggnader_mark"] == "1900000", r["byggnader_mark"]
    assert r["tillgangar"] == "6000000", "koncernens värde får inte tas"
    assert r["soliditet"] == "25.0" and r["varulager"] == "0" and r["anstallda"] == "7.5"
    assert r["sate"] == "Västerås" and r["undertecknad"] == "2026-03-10" and r["maskiner"] == ""
    ok("rätt år, förra årets omsättning, minsta skala, koncernvärden bort, soliditet räknas ut")

    assert bygg.las_rapport("<html>ingen årsredovisning</html>") is None
    ok("annat än årsredovisningar ignoreras")

    tmp = tempfile.mkdtemp(prefix="nyckeltal-test-")
    v1 = os.path.join(tmp, "v1.zip")
    open(v1, "wb").write(veckofil([
        ("5591234567", rapport(till="2024-12-31", fran="2024-01-01", oms="5 000 000")),
        ("5590000001", rapport(orgnr="5590000001")),
    ]))
    v2 = os.path.join(tmp, "v2.zip")
    open(v2, "wb").write(veckofil([
        ("5591234567", rapport()),
        ("5590000001", rapport(orgnr="5590000001", underskrift="2026-05-01", byggnad="3 000")),
    ]))
    bolag = {}
    bygg.las_veckofil(v1, bolag)
    bygg.las_veckofil(v2, bolag)
    rad = dict(zip(bygg.RUBRIK, bolag["5591234567"][2].split("\t")))
    assert rad["till"] == "2025-12-31" and rad["nettoomsattning"] == "8400000"
    rad = dict(zip(bygg.RUBRIK, bolag["5590000001"][2].split("\t")))
    assert rad["byggnader_mark"] == "3000000"
    ok("senaste räkenskapsåret och rättade årsredovisningar går före")

    # Hela bygget mot en låtsas-Bolagsverket med två sidor i listan.
    filer = {"arsredovisningar/2024/52_1.zip": open(v1, "rb").read(),
             "arsredovisningar/2026/10_1.zip": open(v1, "rb").read(),
             "arsredovisningar/2026/11_1.zip": open(v2, "rb").read()}
    hamtade = []

    class Latsas(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.startswith("/bulk?"):
                sida2 = "marker=arsredovisningar%2F2026%2F10_1.zip" in self.path
                nycklar = ["arsredovisningar/2026/11_1.zip"] if sida2 else \
                    ["arsredovisningar/2024/52_1.zip", "arsredovisningar/2026/10_1.zip"]
                xml = "<ListBucketResult><IsTruncated>%s</IsTruncated>%s</ListBucketResult>" % (
                    "false" if sida2 else "true",
                    "".join("<Contents><Key>%s</Key><ETag>&#34;e-%s&#34;</ETag><Size>1</Size></Contents>"
                            % (k, k[-8:]) for k in nycklar))
                data = xml.encode()
            else:
                key = self.path[len("/bulk/"):]
                hamtade.append(key)
                data = filer[key]
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Latsas)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    miljo = dict(os.environ, BOLAGSVERKET_BAS="http://127.0.0.1:%d/bulk" % server.server_port)

    def kor(*args):
        p = subprocess.run([sys.executable, "-I", os.path.join(HAR, "bygg.py")] + list(args),
                           capture_output=True, text=True, env=miljo, timeout=120)
        assert p.returncode == 0, p.stdout + p.stderr
        return p.stdout

    ut1 = os.path.join(tmp, "ut1")
    utskrift = kor("--ut", ut1, "--fran-ar", "2025")
    assert hamtade == ["arsredovisningar/2026/10_1.zip", "arsredovisningar/2026/11_1.zip"], hamtade
    assert "Klar: 2 bolag" in utskrift and open(os.path.join(ut1, "status.txt")).read() == "klar\n"
    ok("listan läses över flera sidor och gamla år hoppas över")

    ut2 = os.path.join(tmp, "ut2")
    kor("--forra", ut1, "--ut", ut2)
    assert len(hamtade) == 2, "redan lästa veckofiler ska inte hämtas igen"
    with zipfile.ZipFile(os.path.join(ut2, "nyckeltal.zip")) as z:
        rader = z.read("nyckeltal.txt").decode().splitlines()
    assert rader[0].split("\t") == bygg.RUBRIK and len(rader) == 3
    ok("nästa bygge fortsätter där förra slutade")

    ut3 = os.path.join(tmp, "ut3")
    kor("--ut", ut3, "--minuter", "0")
    assert open(os.path.join(ut3, "status.txt")).read() == "ofullstandig\n"
    ok("när tiden är slut sparas det som hunnits och bygget markeras ofullständigt")

    server.shutdown()
    shutil.rmtree(tmp)
    print("\nAlla %d tester gick igenom." % steg[0])


if __name__ == "__main__":
    main()
