#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mp3_to_m4b.py – spojí MP3 kapitoly audioknihy do jednoho souboru .m4b
s kapitolami, obálkou a údaji o knize, aby se kniha v aplikaci Knihy
(Apple Books) zobrazila jako audiokniha.

Použití (v Terminálu):

    python3 mp3_to_m4b.py "/cesta/ke/složce s mp3"

Cestu ke složce nemusíte psát: stačí napsat  python3 mp3_to_m4b.py
a pak do okna Terminálu přetáhnout složku myší a stisknout Enter.

Volitelné parametry:
    --nazev "Název knihy"
    --autor "Autor knihy"
    --cte "Kdo knihu čte"
    --obalka obrazek.jpg        vlastní obálka (jinak se hledá ve složce nebo v MP3)
    --nazvy-kapitol nazvy.txt   vlastní názvy kapitol, jeden na řádek, ve stejném
                                pořadí jako soubory
    --bitrate 64k               kvalita zvuku (64k stačí na mluvené slovo)
    --vystup kniha.m4b          kam uložit výsledek (jinak do složky s MP3)
    --knihy                     po dokončení rovnou přidat do aplikace Knihy (Mac)

Soubory se řadí podle názvu stejně jako ve Finderu (1, 2, … 10, 11),
každý soubor je jedna kapitola. Prochází se i podsložky (např. CD1, CD2).

Potřebuje jen Python 3 a ffmpeg. Pokud ffmpeg v počítači není, skript si
sám doinstaluje balíček imageio-ffmpeg, který ffmpeg obsahuje.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata

AUDIO_PRIPONY = {'.mp3', '.m4a', '.m4b', '.aac', '.flac', '.wav', '.ogg',
                 '.opus', '.wma', '.aif', '.aiff'}
OBRAZEK_PRIPONY = {'.jpg', '.jpeg', '.png'}
OBALKA_NAZVY = ('cover', 'folder', 'front', 'obalka', 'obálka', 'obal')
VZORKOVANI = 44100


# ---------------------------------------------------------------- ffmpeg ----

def najdi_ffmpeg():
    """Vrátí cestu k ffmpeg; když chybí, doinstaluje imageio-ffmpeg."""
    exe = shutil.which('ffmpeg')
    if exe:
        return exe
    try:
        import imageio_ffmpeg
    except ImportError:
        print('ffmpeg v počítači není, instaluji balíček imageio-ffmpeg (jen poprvé)…')
        prikaz = [sys.executable, '-m', 'pip', 'install', '--user', '--quiet',
                  'imageio-ffmpeg']
        if subprocess.call(prikaz) != 0 and \
                subprocess.call(prikaz + ['--break-system-packages']) != 0:
            sys.exit('Nepodařilo se nainstalovat ffmpeg. Nainstalujte ho ručně '
                     '(např. „brew install ffmpeg“) a spusťte skript znovu.')
        import importlib
        import site
        site.addsitedir(site.getusersitepackages())
        importlib.invalidate_caches()
        import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def vyber_kodek(ffmpeg):
    """Na Macu je lepší Apple kodér aac_at, pokud ho ffmpeg umí."""
    vystup = subprocess.run([ffmpeg, '-hide_banner', '-encoders'],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return 'aac_at' if b' aac_at ' in vystup.stdout else 'aac'


def precti_hlavicku(ffmpeg, soubor):
    """Přečte z ffmpeg tagy, délku, počet kanálů a zda má soubor obrázek."""
    p = subprocess.run([ffmpeg, '-hide_banner', '-nostdin', '-i', soubor],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    text = p.stderr.decode('utf-8', 'replace')
    info = {'tagy': {}, 'delka': 0.0, 'kanaly': 0, 'obrazek': False}
    v_metadatech = False
    for radek in text.splitlines():
        if radek == '  Metadata:':
            v_metadatech = True
            continue
        if v_metadatech:
            m = re.match(r'^    (\S[^:]*?)\s*: ?(.*)$', radek)
            if m:
                info['tagy'].setdefault(m.group(1).lower(), m.group(2).strip())
                continue
            if not radek.startswith('     '):
                v_metadatech = False
        m = re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)', radek)
        if m:
            info['delka'] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        m = re.search(r'Stream #\d+:\d+.*?: Audio: .*?\d+ Hz, ([^,]+)', radek)
        if m and not info['kanaly']:
            info['kanaly'] = 1 if m.group(1).strip() == 'mono' else 2
        if 'Video:' in radek and 'attached pic' in radek:
            info['obrazek'] = True
    return info


# ------------------------------------------------------------- pomocníci ----

def nfc(text):
    return unicodedata.normalize('NFC', text or '').strip()


def razeni(text):
    """Přirozené řazení: 2 < 10, stejně jako ve Finderu."""
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', nfc(text).lower())]


def najdi_soubory(slozka, vystup):
    soubory = []
    for koren, adresare, nazvy in os.walk(slozka):
        adresare[:] = [d for d in adresare if not d.startswith('.')]
        for nazev in nazvy:
            cesta = os.path.join(koren, nazev)
            if (not nazev.startswith('.')
                    and os.path.splitext(nazev)[1].lower() in AUDIO_PRIPONY
                    and os.path.abspath(cesta) != os.path.abspath(vystup)):
                soubory.append(cesta)
    # Hotová .m4b z dřívějšího spuštění nechceme brát jako kapitolu.
    if any(not s.lower().endswith('.m4b') for s in soubory):
        soubory = [s for s in soubory if not s.lower().endswith('.m4b')]
    soubory.sort(key=lambda c: razeni(os.path.relpath(c, slozka)))
    return soubory


def najdi_obalku(slozka):
    obrazky = []
    for nazev in os.listdir(slozka):
        if not nazev.startswith('.') and os.path.splitext(nazev)[1].lower() in OBRAZEK_PRIPONY:
            obrazky.append(os.path.join(slozka, nazev))
    for obr in obrazky:
        if os.path.splitext(os.path.basename(obr))[0].lower() in OBALKA_NAZVY:
            return obr
    return max(obrazky, key=os.path.getsize) if obrazky else None


def ocisti_nazev(text, album):
    """'01_AHA Rodicovstvi - Predmluva' -> 'Predmluva'."""
    puvodni = nfc(text)
    t = re.sub(r'^(?:track|stopa|cd|disk)?\s*\d{1,3}\s*[-_.):\]]*\s*', '', puvodni,
               flags=re.IGNORECASE)
    album = nfc(album)
    if album and t.lower().startswith(album.lower()):
        zbytek = t[len(album):]
        m = re.match(r'^\s*[-–—_:.,|]+\s*', zbytek)
        if m and zbytek[m.end():].strip():
            t = zbytek[m.end():]
    return t.strip()


def ocisluj_opakovani(nazvy):
    """Stejné názvy jdoucí po sobě dostanou (1/3), (2/3), (3/3)."""
    vysledek = list(nazvy)
    i = 0
    while i < len(nazvy):
        j = i
        while j + 1 < len(nazvy) and nazvy[j + 1] == nazvy[i]:
            j += 1
        pocet = j - i + 1
        if pocet > 1:
            for k in range(i, j + 1):
                vysledek[k] = '%s (%d/%d)' % (nazvy[i], k - i + 1, pocet)
        i = j + 1
    return vysledek


def esc(text):
    """Escapování pro soubor FFMETADATA."""
    return re.sub(r'([=;#\\\n])', r'\\\1', text)


def cas(sekundy):
    sekundy = int(round(sekundy))
    return '%d:%02d:%02d' % (sekundy // 3600, sekundy % 3600 // 60, sekundy % 60)


def bezpecny_nazev(text):
    return re.sub(r'[/:\\]', '-', text).strip() or 'Audiokniha'


def rozdel(delky, pocet):
    """Rozdělí soubory (po sobě jdoucí) na části s podobnou délkou."""
    delky = [d or 1.0 for d in delky]
    celkem = sum(delky)
    skupiny = [[]]
    soucet = 0.0
    for i, d in enumerate(delky):
        if skupiny[-1] and len(skupiny) < pocet and soucet >= celkem * len(skupiny) / pocet:
            skupiny.append([])
        skupiny[-1].append(i)
        soucet += d
    return skupiny


def dekoduj(ffmpeg, soubor, kanaly, cil):
    """Dekóduje soubor do PCM a zapíše ho do cil (stdin kodéru). Vrací počet vzorků."""
    dekoder = subprocess.Popen(
        [ffmpeg, '-hide_banner', '-nostdin', '-nostats', '-loglevel', 'error',
         '-i', soubor, '-map', '0:a:0', '-vn', '-sn',
         '-f', 's16le', '-acodec', 'pcm_s16le',
         '-ar', str(VZORKOVANI), '-ac', str(kanaly), 'pipe:1'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    chyby = []
    vlakno = threading.Thread(target=lambda: chyby.append(dekoder.stderr.read()))
    vlakno.start()
    bajtu_na_vzorek = 2 * kanaly
    bajtu = 0
    zbytek = b''
    try:
        while True:
            blok = dekoder.stdout.read(1 << 20)
            if not blok:
                break
            blok = zbytek + blok
            cele = len(blok) - len(blok) % bajtu_na_vzorek
            zbytek = blok[cele:]
            cil.write(blok[:cele])
            bajtu += cele
    finally:
        dekoder.wait()
        vlakno.join()
    if bajtu == 0:
        raise RuntimeError('Soubor se nepodařilo přečíst: %s\n%s' % (
            soubor, b''.join(chyby).decode('utf-8', 'replace')))
    return bajtu // bajtu_na_vzorek


def koduj_cast(ffmpeg, kodek, bitrate, kanaly, soubory, cil, delky, hotovo):
    """Zakóduje skupinu souborů do jednoho AAC souboru; délky zapíše do delky."""
    log = cil + '.log'
    with open(log, 'wb') as f_log:
        koder = subprocess.Popen(
            [ffmpeg, '-hide_banner', '-nostats', '-loglevel', 'error', '-y',
             '-f', 's16le', '-ar', str(VZORKOVANI), '-ac', str(kanaly), '-i', 'pipe:0',
             '-c:a', kodek, '-b:a', bitrate, cil],
            stdin=subprocess.PIPE, stderr=f_log)
        try:
            for idx, soubor in soubory:
                delky[idx] = dekoduj(ffmpeg, soubor, kanaly, koder.stdin)
                hotovo(idx)
            koder.stdin.close()
        except BrokenPipeError:
            pass
        except BaseException:
            koder.kill()
            raise
        finally:
            koder.wait()
    if koder.returncode != 0:
        with open(log, encoding='utf-8', errors='replace') as f:
            raise RuntimeError('Kódování selhalo:\n' + f.read())


def cesta_z_terminalu(text):
    """Cesta přetažená do Terminálu může mít uvozovky nebo '\\ ' místo mezer."""
    text = text.strip()
    if len(text) > 1 and text[0] == text[-1] and text[0] in '\'"':
        return text[1:-1]
    if os.name == 'nt':                 # ve Windows je '\' oddělovač složek
        return text
    return re.sub(r'\\(.)', r'\1', text)


# ------------------------------------------------------------------ hlavní ---

def main():
    ap = argparse.ArgumentParser(description='Spojí MP3 kapitoly do audioknihy .m4b pro Apple Books.')
    ap.add_argument('slozka', nargs='?', help='složka s MP3 soubory')
    ap.add_argument('--nazev', help='název knihy')
    ap.add_argument('--autor', help='autor knihy')
    ap.add_argument('--cte', help='kdo knihu čte (interpret)')
    ap.add_argument('--obalka', help='obrázek obálky (jpg/png)')
    ap.add_argument('--nazvy-kapitol', help='textový soubor s názvy kapitol, jeden na řádek')
    ap.add_argument('--bitrate', default='64k', help='kvalita zvuku, výchozí 64k')
    ap.add_argument('--vystup', help='cesta k výslednému souboru .m4b')
    ap.add_argument('--knihy', action='store_true', help='po dokončení přidat do aplikace Knihy')
    args = ap.parse_args()

    slozka = args.slozka
    if not slozka:
        slozka = cesta_z_terminalu(input('Přetáhněte sem složku s MP3 a stiskněte Enter: '))
    slozka = os.path.abspath(os.path.expanduser(slozka))
    if not os.path.isdir(slozka):
        sys.exit('Složka neexistuje: %s' % slozka)

    ffmpeg = najdi_ffmpeg()

    # Výstup a seznam souborů (výstup se nesmí načíst jako vstup).
    docasny_vystup = args.vystup or os.path.join(slozka, 'audiokniha.m4b')
    soubory = najdi_soubory(slozka, docasny_vystup)
    if not soubory:
        sys.exit('Ve složce nejsou žádné zvukové soubory.')

    print('Načítám %d souborů…' % len(soubory))
    hlavicky = [precti_hlavicku(ffmpeg, s) for s in soubory]
    tagy = hlavicky[0]['tagy']

    # Údaje o knize: parametry > tagy v MP3 > název složky.
    album = tagy.get('album', '')
    nazev = nfc(args.nazev or album or os.path.basename(slozka))
    autor_tag = tagy.get('author') or tagy.get('writer')
    interpret = tagy.get('album_artist') or tagy.get('artist') or ''
    autor = nfc(args.autor or autor_tag or interpret or tagy.get('composer', ''))
    cte = nfc(args.cte or (interpret if autor_tag and interpret != autor_tag else ''))
    rok = ''
    for klic in ('date', 'tdrc', 'tyer', 'year', 'tdat'):
        m = re.search(r'\b(\d{4})\b', tagy.get(klic, ''))
        if m:
            rok = m.group(1)
            break

    vystup = os.path.abspath(os.path.expanduser(
        args.vystup or os.path.join(slozka, bezpecny_nazev(nazev) + '.m4b')))
    soubory_hlavicky = [(s, h) for s, h in zip(soubory, hlavicky)
                        if os.path.abspath(s) != vystup]
    soubory = [s for s, _ in soubory_hlavicky]
    hlavicky = [h for _, h in soubory_hlavicky]

    # Názvy kapitol.
    if args.nazvy_kapitol:
        with open(os.path.expanduser(args.nazvy_kapitol), encoding='utf-8') as f:
            kapitoly = [nfc(r) for r in f.read().splitlines() if r.strip()]
        if len(kapitoly) != len(soubory):
            sys.exit('V souboru s názvy kapitol je %d řádků, ale souborů je %d.'
                     % (len(kapitoly), len(soubory)))
    else:
        kapitoly = []
        for i, (s, h) in enumerate(zip(soubory, hlavicky), 1):
            surovy = h['tagy'].get('title') or os.path.splitext(os.path.basename(s))[0]
            kapitoly.append(ocisti_nazev(surovy, album) or 'Kapitola %d' % i)
        kapitoly = ocisluj_opakovani(kapitoly)

    kanaly = 2 if any(h['kanaly'] != 1 for h in hlavicky) else 1
    kodek = vyber_kodek(ffmpeg)
    celkem_odhad = sum(h['delka'] for h in hlavicky) or 1.0

    print()
    print('Název:     %s' % nazev)
    print('Autor:     %s' % (autor or '–'))
    if cte:
        print('Čte:       %s' % cte)
    print('Kapitol:   %d (přibližně %s)' % (len(soubory), cas(celkem_odhad)))
    print('Výstup:    %s' % vystup)
    print()

    with tempfile.TemporaryDirectory(prefix='mp3_to_m4b_') as tmp:
        # --- obálka ---------------------------------------------------------
        zdroj_obalky = args.obalka and os.path.expanduser(args.obalka)
        if not zdroj_obalky:
            zdroj_obalky = najdi_obalku(slozka)
        if not zdroj_obalky:
            for s, h in zip(soubory, hlavicky):
                if h['obrazek']:
                    zdroj_obalky = s
                    break
        obalka = None
        if zdroj_obalky:
            obalka = os.path.join(tmp, 'obalka.jpg')
            r = subprocess.run([ffmpeg, '-hide_banner', '-nostdin', '-loglevel', 'error', '-y',
                                '-i', zdroj_obalky, '-map', '0:v:0', '-frames:v', '1',
                                '-vf', "scale='min(1400,iw)':-2", '-c:v', 'mjpeg', '-pix_fmt', 'yuvj420p',
                                '-q:v', '3', obalka],
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if r.returncode != 0 or not os.path.exists(obalka):
                print('Obálku se nepodařilo načíst, pokračuji bez ní.')
                obalka = None

        # --- 1) dekódování a kódování, souběžně ve více částech -----------------
        # Každá část (souvislý úsek kapitol) se kóduje na vlastním jádře.
        skupiny = rozdel([h['delka'] for h in hlavicky],
                         max(1, min(os.cpu_count() or 1, 8, len(soubory))))
        casti = [os.path.join(tmp, 'cast%02d.m4a' % k) for k in range(len(skupiny))]
        delky = [0] * len(soubory)        # délka každé kapitoly ve vzorcích
        start = time.time()
        zamek = threading.Lock()
        stav = {'pocet': 0, 'sekund': 0.0}

        def hotovo(idx):
            with zamek:
                stav['pocet'] += 1
                stav['sekund'] += hlavicky[idx]['delka']
                print('[%3d/%d] %3d %%  %s' % (stav['pocet'], len(soubory),
                                              min(100, int(100 * stav['sekund'] / celkem_odhad)),
                                              kapitoly[idx]))
                sys.stdout.flush()

        chyby = []

        def prace(skupina, cil):
            try:
                koduj_cast(ffmpeg, kodek, args.bitrate, kanaly,
                           [(i, soubory[i]) for i in skupina], cil, delky, hotovo)
            except Exception as e:      # chybu oznámíme z hlavního vlákna
                chyby.append(e)

        vlakna = [threading.Thread(target=prace, args=(sk, cil), daemon=True)
                  for sk, cil in zip(skupiny, casti)]
        for v in vlakna:
            v.start()
        for v in vlakna:
            while v.is_alive():
                v.join(0.5)
        if chyby:
            sys.exit(str(chyby[0]))

        # Začátky kapitol. Každá část začíná na celém AAC rámci (1024 vzorků)
        # a kodér na jejím začátku přidá krátkou úvodní prodlevu.
        prodleva = 2112 if kodek == 'aac_at' else 1024
        zacatky = []
        zacatek_casti = 0
        for sk in skupiny:
            pozice = zacatek_casti + prodleva
            for i in sk:
                zacatky.append(pozice)
                pozice += delky[i]
            vzorku_casti = sum(delky[i] for i in sk)
            zacatek_casti += -(-(vzorku_casti + prodleva) // 1024) * 1024
        zacatky[0] = 0
        vzorku = zacatek_casti

        seznam = os.path.join(tmp, 'casti.txt')
        with open(seznam, 'w', encoding='utf-8') as f:
            for cil in casti:
                f.write("file '%s'\n" % cil.replace("'", "'\\''"))

        # --- 2) kapitoly a údaje o knize -------------------------------------
        meta = os.path.join(tmp, 'kapitoly.txt')
        with open(meta, 'w', encoding='utf-8') as f:
            f.write(';FFMETADATA1\n')
            udaje = [('title', nazev), ('album', nazev), ('artist', autor),
                     ('album_artist', autor), ('composer', cte), ('genre', 'Audiokniha'),
                     ('date', rok), ('copyright', tagy.get('copyright', '')),
                     ('comment', 'Čte: %s' % cte if cte else ''), ('media_type', '2')]
            for klic, hodnota in udaje:
                if hodnota:
                    f.write('%s=%s\n' % (klic, esc(hodnota)))
            konce = zacatky[1:] + [vzorku]
            for zac, kon, kap in zip(zacatky, konce, kapitoly):
                f.write('\n[CHAPTER]\nTIMEBASE=1/1000\n')
                f.write('START=%d\nEND=%d\n' % (round(zac * 1000 / VZORKOVANI),
                                               round(kon * 1000 / VZORKOVANI)))
                f.write('title=%s\n' % esc(kap))

        # --- 3) složení výsledného .m4b --------------------------------------
        print('Ukládám audioknihu…')
        hotovy = os.path.join(tmp, 'kniha.m4b')

        def sloz(s_obalkou):
            prikaz = [ffmpeg, '-hide_banner', '-nostdin', '-loglevel', 'error', '-y',
                      '-f', 'concat', '-safe', '0', '-i', seznam,
                      '-f', 'ffmetadata', '-i', meta]
            if s_obalkou:
                prikaz += ['-i', obalka]
            prikaz += ['-map', '0:a', '-map_metadata', '1', '-map_chapters', '1']
            if s_obalkou:
                prikaz += ['-map', '2:v', '-c:v', 'copy', '-disposition:v:0', 'attached_pic']
            prikaz += ['-c:a', 'copy', '-movflags', '+faststart', '-f', 'ipod', hotovy]
            return subprocess.run(prikaz, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        r = sloz(bool(obalka))
        if r.returncode != 0 and obalka:
            print('Obálku se nepodařilo vložit, ukládám bez ní.')
            r = sloz(False)
        if r.returncode != 0:
            sys.exit('Uložení selhalo:\n' + r.stderr.decode('utf-8', 'replace'))
        os.makedirs(os.path.dirname(vystup), exist_ok=True)
        shutil.move(hotovy, vystup)

    trvani = vzorku / VZORKOVANI
    print()
    print('Hotovo za %s.' % cas(time.time() - start))
    print('Audiokniha: %s' % vystup)
    print('Délka %s, %d kapitol, %.0f MB.' % (cas(trvani), len(kapitoly),
                                             os.path.getsize(vystup) / 1e6))

    if sys.platform == 'darwin':
        pridat = args.knihy
        if not pridat and sys.stdin.isatty():
            odpoved = input('\nPřidat knihu do aplikace Knihy? [A/n] ').strip().lower()
            pridat = odpoved in ('', 'a', 'ano', 'y', 'yes')
        if pridat:
            subprocess.call(['open', '-a', 'Books', vystup])
            print('Přidáno. Do iPhonu ji dostanete přes Finder → iPhone → Audioknihy → Synchronizovat.')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit('\nPřerušeno.')
