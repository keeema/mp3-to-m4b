# mp3-to-m4b

Spojí MP3 kapitoly audioknihy do jednoho souboru **.m4b** s kapitolami, obálkou a údaji o knize. Kniha se pak v aplikaci **Knihy (Apple Books)** zobrazí jako audiokniha: se seznamem kapitol a s tím, že si pamatuje, kde jste skončili.

> *English: Joins a folder of MP3 chapter files into a single chaptered M4B audiobook (with cover art and metadata) for Apple Books. Each file becomes a chapter. The command-line interface is in Czech.*

## Co umí

- Každý soubor je jedna kapitola. Řadí se podle názvu jako ve Finderu (2 < 10) a prochází i podsložky (CD1, CD2…).
- Názvy kapitol bere z tagů nebo z názvů souborů. Odstraní z nich čísla stop i název knihy na začátku a opakující se názvy očísluje (1/8, 2/8…).
- Název knihy, autora a interpreta převezme z tagů MP3. Dají se přepsat parametry.
- Obálku najde ve složce (`cover.jpg`, `folder.jpg`…) nebo v MP3, případně použije vaši.
- Soubor označí jako audioknihu (media kind *Audiobook*).
- Kóduje souběžně na všech jádrech procesoru. Deset hodin zvuku trvá zhruba minutu.
- Vstupní formáty: MP3, M4A, M4B, AAC, FLAC, WAV, OGG, Opus, WMA, AIFF.

## Požadavky

- **Python 3.8+**. Na Macu stačí v Terminálu napsat `python3` a systém případně nabídne instalaci.
- **ffmpeg**. Pokud ho nemáte (`brew install ffmpeg`), skript si sám doinstaluje balíček [imageio-ffmpeg](https://pypi.org/project/imageio-ffmpeg/), který ffmpeg obsahuje.

Funguje na macOS a Linuxu. Na Windows by měl fungovat taky, ale není tam otestovaný.

## Použití

```sh
python3 mp3_to_m4b.py "/cesta/ke/složce s mp3"
```

Nebo spusťte jen `python3 mp3_to_m4b.py`, přetáhněte složku do okna Terminálu a stiskněte Enter.

Výsledný soubor `Název knihy.m4b` se uloží do složky s MP3. Na Macu se skript na konci zeptá, jestli knihu rovnou přidat do aplikace Knihy.

### Parametry

| Parametr | Význam |
|---|---|
| `--nazev "…"` | název knihy (jinak z tagu *album* nebo podle názvu složky) |
| `--autor "…"` | autor knihy |
| `--cte "…"` | kdo knihu čte (interpret) |
| `--obalka obrazek.jpg` | vlastní obálka |
| `--nazvy-kapitol nazvy.txt` | vlastní názvy kapitol, jeden na řádek, ve stejném pořadí jako soubory |
| `--bitrate 64k` | kvalita zvuku. Výchozích 64k na mluvené slovo stačí. |
| `--vystup kniha.m4b` | kam výsledek uložit |
| `--knihy` | po dokončení přidat do aplikace Knihy bez ptaní (macOS) |

Příklad:

```sh
python3 mp3_to_m4b.py ~/Downloads/Kniha --nazev "Název knihy" --autor "Jméno Autora" --cte "Jméno Interpreta"
```

## Jak dostat knihu do iPhonu

Audioknihy, které do Knih importujete sami, se **nesynchronizují přes iCloud**. To platí jen pro e-knihy a PDF. Použijte synchronizaci přes Finder:

1. Připojte iPhone k Macu kabelem a ve Finderu klikněte vlevo na iPhone.
2. Na záložce **Audioknihy** zapněte synchronizaci a klikněte na **Synchronizovat**.

Tip: když na záložce **Obecné** zaškrtnete *„Zobrazovat tento iPhone, je-li připojen k Wi-Fi“*, příště se synchronizace obejde bez kabelu.

## Jak to funguje

1. Každý soubor se dekóduje do PCM. Podle počtu vzorků se spočítá přesná délka kapitoly, takže kapitoly sedí na milisekundy.
2. Zvuk se zakóduje do AAC, na Macu Apple kodérem `aac_at`, pokud ho ffmpeg umí. Kóduje se v několika částech souběžně.
3. Části se spojí do kontejneru MP4 (`.m4b`) spolu s kapitolami, obálkou a metadaty.

## Upozornění

Skript pracuje jen se soubory **bez DRM** a žádnou ochranu neobchází. Používejte ho na nahrávky, které legálně vlastníte. Do repozitáře nenahrávejte zvukové soubory ani obálky knih.

## Licence

[MIT](LICENSE)
