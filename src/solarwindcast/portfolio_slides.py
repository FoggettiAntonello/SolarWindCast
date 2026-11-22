"""Render twelve offline HTML slides from verified aggregate evidence, without inference."""

from base64 import b64encode
from html import escape
from importlib.resources import files


def regional_map() -> str:
    """Embed the attributed administrative map, explicitly distinct from electricity zones."""
    return files('solarwindcast').joinpath('assets/italy_regions.svg').read_text(encoding='utf-8')


def energy_background_uri() -> str:
    """Embed the generated decorative background without remote image dependencies."""
    data = files('solarwindcast').joinpath('assets/energy_background.png').read_bytes()
    return 'data:image/png;base64,' + b64encode(data).decode('ascii')


def sources_visual() -> str:
    """Illustrate source roles with original pictograms, without implying weather was used."""
    return '''<svg class="sources-visual" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 400" role="img" aria-label="ENTSO-E: dati energetici usati. Open-Meteo: adattatore predisposto, meteo escluso dai risultati.">
<title>Due fonti, due ruoli distinti</title>
<rect x="8" y="8" width="624" height="190" rx="16" fill="#e6efea"/>
<g fill="none" stroke="#27675c" stroke-width="3"><path d="M65 72 L107 45 L144 88 L102 128 L65 72 M107 45 L102 128 M65 72 L144 88"/>
<circle cx="65" cy="72" r="8" fill="#e6efea"/><circle cx="107" cy="45" r="8" fill="#e6efea"/><circle cx="144" cy="88" r="8" fill="#e6efea"/><circle cx="102" cy="128" r="8" fill="#e6efea"/></g>
<g font-family="system-ui"><text x="185" y="52" font-size="13" letter-spacing="2" fill="#467264">FONTE DEI DATI UTILIZZATI</text>
<text x="185" y="94" font-size="34" font-weight="750" fill="#173e36">ENTSO-E</text>
<text x="185" y="124" font-size="18" fill="#41685f">Transparency Platform</text>
<text x="185" y="158" font-size="18" fill="#173e36">Produzione rinnovabile e carico elettrico</text>
<rect x="8" y="218" width="624" height="174" rx="16" fill="#f1eadc"/>
<circle cx="88" cy="274" r="26" fill="#e7b458"/>
<g stroke="#d49c3d" stroke-width="3"><path d="M88 235v-11 M88 313v10 M49 274H38 M127 274h11 M60 246l-8-8 M116 246l8-8"/></g>
<path d="M69 304c-20-2-22-30-2-35 6-26 44-26 52-3 27-2 34 38 8 38Z" fill="#fffaf0" stroke="#76958c" stroke-width="2"/>
<text x="185" y="259" font-size="13" letter-spacing="2" fill="#836c43">INTEGRAZIONE PREDISPOSTA</text>
<text x="185" y="302" font-size="30" font-weight="700" fill="#173e36">Open-Meteo</text>
<text x="185" y="340" font-size="18" fill="#665f4e">Meteo escluso dagli esperimenti mostrati</text>
<text x="185" y="366" font-size="16" fill="#665f4e">Archivi delle previsioni e leakage da verificare</text></g></svg>
<div class="source-links"><a href="https://transparency.entsoe.eu/">ENTSO-E ↗</a><a href="https://open-meteo.com/">Open-Meteo ↗</a></div>'''


def number(value: float) -> str:
    """Format a numeric label using Italian separators."""
    return f'{value:,.2f}'.translate(str.maketrans(',.', '.,'))


def bars(rows: list[tuple[str, float, str]], title: str, unit: str,
         nominal: list[float] | None = None) -> str:
    """Draw zero-based SVG bars with exact labels and optional per-row nominal markers."""
    maximum = max([v for _, v, _ in rows] + (nominal or [0])) * 1.12 or 1
    height = 65 + 79 * len(rows)
    pieces = [f'<svg class="chart" role="img" aria-label="{escape(title)}" '
              f'viewBox="0 0 640 {height}" xmlns="http://www.w3.org/2000/svg">',
              f'<title>{escape(title)}</title><text x="2" y="22" class="chart-title">{escape(title)}</text>']
    for i, (label, value, color) in enumerate(rows):
        y = 60 + i * 79
        width = value / maximum * 475
        pieces += [f'<text x="2" y="{y}">{escape(label)}</text>',
                   f'<rect data-value="{value:.17g}" data-nominal="{nominal[i] if nominal else ""}" '
                   f'x="0" y="{y+10}" width="{width:.3f}" height="22" rx="3" fill="{color}"/>',
                   f'<text x="500" y="{y+28}" class="value">{number(value)}</text>']
        if nominal:
            x = nominal[i] / maximum * 475
            pieces.append(f'<path d="M{x:.3f},{y+6} v30" stroke="#172e3a" stroke-dasharray="4 3" stroke-width="2"/>')
    pieces.append(f'<text x="2" y="{height-3}" class="unit">{escape(unit)} · origine delle barre: zero</text></svg>')
    return ''.join(pieces)


def data_table(rows: list[tuple[str, str]], caption: str) -> str:
    """Render a compact evidence table beside explanatory text."""
    return '<table><caption>'+escape(caption)+'</caption><tbody>'+''.join(
        '<tr><th scope="row">'+escape(k)+'</th><td>'+escape(v)+'</td></tr>' for k, v in rows
    )+'</tbody></table>'


def best(models: dict, timestral: bool) -> dict:
    """Return the descriptive minimum MAE within a declared family, never a promotion."""
    return min((v for k, v in models.items() if k.startswith('timestral') == timestral),
               key=lambda v: v['mae'])


def render_slides(bundle: dict, config: dict) -> str:
    """Compose twelve text-and-evidence slides, keeping complete results in a linked appendix."""
    studies = {s['id']: s for s in bundle['studies']}
    monthly = studies['monthly_original']['targets']
    hourly = studies['hourly_extension']['targets']
    calibrated = studies['hourly_calibration']['targets']
    final = studies['monthly_final']['targets']['wind']
    raw_name = 'timestral_5M'
    cal_name = raw_name+'__additive_calibrated'
    ref = final['timestral_28M_known_calendar__ctx24']
    candidate = final['timestral_28M_known_calendar__ctx12__calibrated']
    wind, solar = calibrated['wind'], calibrated['solar']
    hourly_exclusions = len(studies['hourly_extension'].get('exclusions', []))
    calibration_study = studies['hourly_calibration']
    solar_history_exclusions = calibration_study.get('excluded_for_history', {}).get('solar', 0)
    original_exclusions = len(calibration_study.get('original_exclusions', {}).get('solar', []))
    teal, gray, amber = '#087e8b', '#718692', '#bc682c'
    slides = []

    def add(title: str, text: str, visual: str, source: str) -> None:
        """Append one slide with adjacent prose, one evidence figure and a source note."""
        index = len(slides)+1
        chapters = ('Il problema', 'Le fonti', 'Il metodo', 'Previsione mensile',
                    'Il tentativo', 'Previsione oraria', 'L’incertezza', 'La calibrazione',
                    'Il risultato', 'Il compromesso', 'La verifica', 'Il contributo')
        slides.append(f'<section class="slide" id="slide{index}" aria-labelledby="title{index}">'
                      f'<div class="copy"><p class="step">{index:02d} / {chapters[index-1]}</p>'
                      f'<h1 id="title{index}">{title}</h1>{text}</div>'
                      f'<figure>{visual}<figcaption>{source}</figcaption></figure></section>')

    add('Prevedere le rinnovabili, misurando anche gli errori.',
        '<p>Abbiamo costruito una pipeline per prevedere solare ed eolico della zona di mercato Sud Italia.</p>'
        '<p>La domanda principale è l’energia del prossimo mese. Abbiamo poi esplorato le prossime 24 ore, '
        'confrontando Timestral con metodi semplici.</p><p class="takeaway">Risultato: un vantaggio orario '
        'puntuale osservato, senza superiorità complessiva dimostrata.</p>',
        regional_map(),
        'La Puglia è il focus geografico; i risultati riguardano la zona di mercato Sud. '
        'Calabria: estensione distinta. Confini amministrativi: '
        '<a href="https://github.com/openpolis/geojson-italy">Openpolis</a>, '
        '<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>; geometrie semplificate.')

    add('Prima del modello, dati coerenti.',
        '<p>Abbiamo acquisito e controllato dati ENTSO-E, uniformando gli intervalli in UTC '
        'e conservando originali, provenienza e valori mancanti.</p>'
        '<p>La zona Sud comprende la Puglia ma non coincide con essa. Sud + Calabria è '
        'un’estensione separata, non la geografia delle prestazioni principali.</p>',
        sources_visual(),
        'Storico principale: novembre 2021 – ottobre 2026, con copertura verificata per componente. '
        'I mancanti restano NaN. La disponibilità del meteo non equivale al suo uso nel backtest.')

    add('Una valutazione che rispetta il tempo.',
        '<p>Ogni previsione usa soltanto il contesto disponibile al momento dell’emissione. '
        'Modello e baseline sono valutati sulle stesse finestre.</p>'
        '<p>Il calendario è conoscibile in anticipo. I ritardi di pubblicazione e i buchi '
        'dei dati vengono gestiti esplicitamente.</p><p class="takeaway">Il backtest è retrospettivo: '
        'dati revisionati e periodi già esaminati limitano la forza delle conclusioni.</p>',
        data_table([('Contesto mensile', str(config['monthly_protocol']['context_months'])+' mesi'),
                    ('Emissione mensile', str(config['monthly_protocol']['issue_lead_hours'])+' ore prima del mese UTC'),
                    ('Contesto orario', str(config['hourly_pilot']['context_hours'])+' ore'),
                    ('Ritardo dati orario assunto', str(config['hourly_pilot']['assumed_delay_hours'])+' ore')],
                   'Impostazioni congelate nella configurazione'),
        'Il ritardo orario è un’ipotesi; non ricostruisce le pubblicazioni storiche effettive.')

    monthly_charts = ''.join(bars([(label+' · baseline', best(monthly[t], False)['mae'], gray),
                                   (label+' · Timestral', best(monthly[t], True)['mae'], teal)],
                                  label+' · MAE mensile', 'MWh · più basso è meglio')
                             for t, label in [('solar', 'Solare'), ('wind', 'Eolico')])
    add('Sul mese, i risultati sono misti.',
        '<p>Le baseline ripetono il passato o usano gli errori storici. Sono il riferimento '
        'che un modello più complesso deve superare.</p><p>Nel test mensile il migliore Timestral '
        'osservato perde sul solare e migliora sull’eolico rispetto alla migliore baseline del campione.</p>'
        '<p class="takeaway">Questa graduatoria è descrittiva: scegliere il migliore dopo il test '
        'non equivale a validarlo prima.</p>', monthly_charts,
        f'Novembre 2024 – ottobre 2026: {best(monthly["solar"], True)["cases"]} mesi solari e '
        f'{best(monthly["wind"], True)["cases"]} eolici valutabili. Scale separate. Tutti i metodi nell’approfondimento.')

    add('Il tentativo mensile successivo non ha funzionato.',
        '<p>Abbiamo provato un contesto eolico più corto con 28M, calendario e una calibrazione '
        'definita in precedenza.</p><p>Il candidato peggiora sia l’errore centrale sia la pinball '
        'rispetto al riferimento a contesto più lungo.</p><p class="takeaway">Criteri non superati: '
        'abbiamo fermato questa iterazione, senza promuovere il candidato.</p>',
        bars([('MAE · riferimento', 100, gray),
              ('MAE · candidato', 100*candidate['mae']/ref['mae'], amber),
              ('Pinball · riferimento', 100, gray),
              ('Pinball · candidato', 100*candidate['pinball']/ref['pinball'], amber)],
             'Ultimo confronto eolico mensile', 'Indice: riferimento = 100 · più basso è meglio'),
        f'{candidate["origins"]} mesi comuni. Riferimento 28M/calendario/24 mesi; candidato 12 mesi calibrato. '
        'Vecchio test già esaminato: confronto esplorativo.')

    hourly_charts = ''.join(bars([(label+' · baseline', best(hourly[t], False)['mae'], gray),
                                  (label+' · 5M', hourly[t][raw_name]['mae'], teal)],
                                 label+' · MAE sulle 24 ore', 'MW · più basso è meglio')
                            for t, label in [('solar', 'Solare'), ('wind', 'Eolico')])
    add('Sulle 24 ore emerge un segnale utile.',
        '<p>Dopo un pilota, abbiamo esteso la prova a giornate prestabilite. Timestral 5M '
        'usa solo la serie del target, senza meteo o riaddestramento.</p><p>Il MAE migliora '
        'rispetto alla migliore baseline osservata: '
        + ' e '.join(f'{number(next(h["change_pct"] for h in bundle["highlights"] if h["target"]==t and h["metric"]=="mae"))}% '
                     + label for t, label in [('solar', 'solare'), ('wind', 'eolico')])
        + '.</p><p class="takeaway">È un vantaggio del punto previsto nel campione, non una '
        'dimostrazione di maggiore affidabilità degli intervalli.</p>', hourly_charts,
        f'Giorni 1/8/22, novembre 2024 – ottobre 2026: solare {hourly["solar"][raw_name]["origins"]} giornate/'
        f'{hourly["solar"][raw_name]["cases"]} ore; eolico {hourly["wind"][raw_name]["origins"]}/'
        f'{hourly["wind"][raw_name]["cases"]}. Esclusioni per contesto incompleto: {hourly_exclusions}; scale separate.')

    add('L’errore medio non basta: le bande sono strette.',
        '<p>Un intervallo nominale all’80% dovrebbe contenere circa l’80% dei valori osservati '
        'su un campione adeguato. Qui gli intervalli grezzi coprono molto meno, soprattutto nell’eolico.</p>'
        '<p>Per questo abbiamo misurato anche pinball, coperture e ampiezze.</p>'
        '<p class="takeaway">Un MAE migliore può convivere con un’incertezza poco affidabile.</p>',
        bars([(label+f' · nominale {int(level*100)}%', 100*hourly[t][raw_name][f'coverage_{level}'], teal)
              for t, label in [('solar', 'Solare'), ('wind', 'Eolico')] for level in (.8, .9)],
             'Copertura osservata del 5M grezzo', '% · tratteggio = livello nominale', [80, 90, 80, 90]),
        'Stesso campione della slide precedente. Ore correlate: la copertura osservata non è una garanzia futura.')

    add('Calibrare l’incertezza senza cambiare la mediana.',
        '<p>Abbiamo allargato i quantili laterali usando soltanto errori di giornate '
        'già interamente disponibili al cutoff.</p><p>La correzione è non negativa, preserva '
        'l’annidamento delle bande e lascia invariata la previsione centrale.</p>'
        '<p class="takeaway">È una calibrazione delle previsioni, non un fine tuning dei pesi.</p>',
        data_table([('Storico del calibratore', str(config['hourly_calibration']['lookback_days'])+' giorni'),
                    ('Minimo di giornate valide', str(config['hourly_calibration']['minimum_complete_origins'])),
                    ('Mediana e MAE', 'Invariati sui medesimi casi'),
                    ('Nuove inferenze o training', 'Nessuno: replay delle previsioni esistenti')],
                   'Regole del replay controllato'),
        'Il replay ha un sottoinsieme valutabile diverso: non attribuire il cambio di campione a un miglioramento.')

    add('Eolico: la copertura si avvicina al nominale.',
        '<p>Sulle giornate con storico sufficiente, le bande calibrate contengono più spesso '
        'la produzione osservata.</p><p>La mediana resta identica. La pinball migliora rispetto '
        'allo stesso 5M grezzo, ma il confronto con la baseline resta necessario.</p>',
        bars([(f'{int(level*100)}% · '+label, 100*wind[name][f'coverage_{level}'], color)
              for level in (.8, .9) for label, name, color in
              [('prima', raw_name, gray), ('calibrato', cal_name, teal)]],
             'Copertura eolica prima / dopo', '% · tratteggio = livello nominale', [80, 80, 90, 90]),
        f'Stessi {wind[cal_name]["origins"]} giorni, {wind[cal_name]["cases"]} ore, maggio 2025 – ottobre 2026. '
        'Prima/dopo indica soltanto la calibrazione.')

    base = wind['hour_of_day_distribution']
    add('Il miglioramento ha un costo: bande più ampie.',
        f'<p>La pinball eolica passa da {number(wind[raw_name]["pinball"])} a '
        f'{number(wind[cal_name]["pinball"])} MW, sullo stesso campione.</p>'
        '<p>Rispetto alla baseline probabilistica, però, la pinball calibrata rimane peggiore '
        'e la banda al 90% più ampia.</p><p class="takeaway">I criteri complessivi non sono '
        'superati. Una copertura corretta, da sola, non rende migliore una previsione.</p>',
        bars([('Pinball · baseline', 100, gray), ('Pinball · calibrato', 100*wind[cal_name]['pinball']/base['pinball'], amber),
              ('Ampiezza 90 · baseline', 100, gray),
              ('Ampiezza 90 · calibrato', 100*wind[cal_name]['width_0.9']/base['width_0.9'], amber)],
             'Calibrato contro baseline probabilistica', 'Indice: baseline = 100 · ampiezza da leggere con copertura'),
        f'Stessi {wind[cal_name]["origins"]} giorni. Baseline: distribuzione della stessa ora del giorno. '
        'I due indicatori hanno unità originali MW ma scale distinte, qui normalizzate.')

    add('Solare: il beneficio della calibrazione è limitato.',
        f'<p>La pinball scende da {number(solar[raw_name]["pinball"])} a '
        f'{number(solar[cal_name]["pinball"])} MW: una riduzione piccola.</p>'
        '<p>Le coperture migliorano, ma non basta per superare i criteri o la baseline '
        'probabilistica. Il vantaggio non è uniforme tra target e campioni.</p>'
        '<p class="takeaway">Riportiamo anche questo risultato: la stessa correzione non '
        'porta lo stesso beneficio su tutte le serie.</p>',
        bars([(f'{int(level*100)}% · '+label, 100*solar[name][f'coverage_{level}'], color)
              for level in (.8, .9) for label, name, color in
              [('prima', raw_name, gray), ('calibrato', cal_name, teal)]],
             'Copertura solare prima / dopo', '% · tratteggio = livello nominale', [80, 80, 90, 90]),
        f'{solar[cal_name]["origins"]} giornate/{solar[cal_name]["cases"]} ore valutabili. '
        f'{solar_history_exclusions} origini solari senza storico sufficiente e {original_exclusions} '
        'esclusioni originarie; mediana e MAE invariati.')

    add('Una pipeline verificabile, con limiti espliciti.',
        '<p>Il contributo è un percorso riproducibile: dati controllati, backtest comune, '
        'baseline, metriche probabilistiche e calibrazione causale.</p>'
        '<p>Mancano una verifica prospettica indipendente e un beneficio economico misurato. '
        'Il motivo del vantaggio orario non è stato isolato con esperimenti causali.</p>'
        '<p><a href="details.html#complete">Confronti completi e casi sfavorevoli →</a></p>'
        '<p><a href="metrics.json">Metriche JSON</a> · <a href="../../README.md">Codice e setup</a></p>',
        data_table([('Configurazione e cutoff', 'Espliciti e condivisi tra i confronti'),
                    ('Provenienza', 'Originali e hash conservati'),
                    ('Collaudo', 'Ambiente isolato, CLI e test documentati'),
                    ('Conclusione', 'Segnale orario promettente; nessuna promozione generale')],
                   'Che cosa può verificare chi legge'),
        'Dati revisionati, finestre già esaminate e ore correlate. I benchmark di Mistral non sono risultati locali.')

    assert len(slides) == 12
    page = '''<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SolarWindCast · Il progetto in 12 slide</title><style>
:root{--ink:#193541;--teal:#087e8b;--paper:#f4f7f7}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:19px/1.55 system-ui,sans-serif}main,header,nav{max-width:1280px;margin:auto;padding-left:42px;padding-right:42px}header{display:flex;justify-content:space-between;align-items:center;min-height:64px;font-size:15px;border-bottom:1px solid #d5e1e2}a{color:#006b78}header a{text-decoration:none}.slide{display:grid;grid-template-columns:minmax(0,.93fr) minmax(0,1.07fr);gap:54px;align-items:center;min-height:calc(100svh - 135px);padding:28px 0}.js .slide{display:none}.js .slide.active{display:grid}h1{font-size:clamp(30px,3.2vw,47px);line-height:1.14;letter-spacing:-.03em;margin:12px 0 24px}.step{font-size:13px;font-weight:700;letter-spacing:.13em;color:#53737c}.copy p{margin:14px 0}.takeaway{border-left:4px solid var(--teal);padding-left:16px;font-weight:600;font-size:18px}figure{margin:0;min-width:0}figcaption{font-size:13px;color:#526b75;margin-top:16px;line-height:1.45}.chart{display:block;width:100%;max-height:330px;margin:0 0 12px}.chart text{font:17px system-ui;fill:#193541}.chart .chart-title{font-weight:700;font-size:19px}.chart .value{font-weight:700}.chart .unit{font-size:13px;fill:#526b75}table{border-collapse:collapse;width:100%;font-size:18px}caption{text-align:left;font-size:21px;font-weight:700;margin-bottom:18px}th,td{text-align:left;padding:17px 12px;border-bottom:1px solid #cadbdd;vertical-align:top}th{width:43%;font-weight:600}td{color:#31535e}nav{min-height:70px;display:flex;align-items:center;gap:16px;justify-content:space-between;font-size:15px;border-top:1px solid #d5e1e2}.controls{display:flex;align-items:center;gap:14px}button{font:inherit;cursor:pointer;padding:9px 16px;background:#fff;border:1px solid #a9c0c5;border-radius:5px;color:var(--ink)}button:disabled{opacity:.45;cursor:default}button:focus-visible,a:focus-visible{outline:3px solid #bc682c;outline-offset:4px}
body{background:radial-gradient(ellipse at 92% 5%,#dce9df 0,transparent 48%),radial-gradient(ellipse at 4% 95%,#ece0ca 0,transparent 48%),#f6f3eb;background-attachment:fixed}header,nav{border-color:#c7d7cb}header strong{display:flex;align-items:center;gap:10px;letter-spacing:-.02em}header strong::before{content:"";display:inline-block;width:25px;height:25px;border-radius:50%;background:conic-gradient(from 20deg,#d3a555 0deg 110deg,#39786b 110deg 240deg,#a1c3ad 240deg 360deg);box-shadow:inset 0 0 0 5px #f4f1e7}h1{color:#173f36}.step{color:#477b69;text-transform:uppercase}.step::before{content:"";display:inline-block;width:25px;height:2px;background:#bf914b;vertical-align:middle;margin-right:12px}.takeaway{border-color:#b9914d;color:#244f42}figure{padding:24px;background:#fffdf6e8;border:1px solid #d8e1d5;border-radius:18px;box-shadow:0 14px 35px #254e3821}figcaption{color:#5a7061}table th,table td{border-color:#dce4d8}caption{color:#214d40}.geography,.sources-visual{width:100%;height:auto;display:block}.source-links{display:flex;gap:24px;font-size:13px;margin-top:10px}.source-links a{color:#3f7160}button{border-color:#9bb7a5;background:#fffdf6}#next{background:#285c4e;color:#fffdf2;border-color:#285c4e}.chart text{fill:#244b3e}.chart .unit{fill:#627464}
@media(max-width:800px){main,header,nav{padding-left:20px;padding-right:20px}.slide{grid-template-columns:1fr;gap:20px;padding:20px 0;min-height:0}h1{font-size:33px}body{font-size:17px}.chart{max-height:none}.takeaway{font-size:17px}table{font-size:16px}th,td{padding:14px 7px}header{gap:15px;font-size:13px}nav{flex-wrap:wrap;padding-top:15px;padding-bottom:15px}.chart text{font-size:18px}.chart .unit{font-size:14px}figure{padding:16px}.source-links{font-size:14px}}
@media(min-width:801px) and (max-height:740px){body{font-size:17px}header{min-height:56px}nav{min-height:64px}.slide{min-height:calc(100svh - 124px);padding:18px 0;gap:40px}h1{font-size:32px;margin-bottom:18px}.takeaway{font-size:16px}table{font-size:16px}th,td{padding-top:12px;padding-bottom:12px}}
body{background-image:url("ENERGY_BACKGROUND_DATA_URI");background-size:cover;background-position:center;background-attachment:fixed}figure{background:#fffdf6e6;box-shadow:0 12px 30px #254e3815}
@media print{@page{size:A4 landscape;margin:12mm}header,nav{display:none}body{font-size:15px;print-color-adjust:exact;-webkit-print-color-adjust:exact}main{padding:0;max-width:none}.js .slide,.slide{display:grid;min-height:175mm;break-after:page;page-break-after:always;padding:0;gap:25px}.slide:last-child{break-after:auto;page-break-after:auto}h1{font-size:30px}.takeaway{font-size:15px}table{font-size:15px}.chart{max-height:64mm}figcaption{font-size:10px}figure{box-shadow:none;padding:16px}}
</style></head><body><header><strong>SolarWindCast</strong><span class="header-links"><a href="details.html#complete">Confronti completi</a> · <a href="PresentazioneSolarWindCast.pptx" download>PowerPoint ↓</a></span></header><main>''' + ''.join(slides) + '''</main>
<nav aria-label="Navigazione slide"><span>Valutazione retrospettiva · dati reali</span><div class="controls"><button id="previous" aria-label="Slide precedente">←</button><span id="counter" aria-live="polite">1 / 12</span><button id="next" aria-label="Slide successiva">→</button></div></nav>
<script>const slides=[...document.querySelectorAll('.slide')];let current=0;
function show(n){current=Math.max(0,Math.min(slides.length-1,n));slides.forEach((s,i)=>{s.classList.toggle('active',i===current);s.setAttribute('aria-hidden',i===current?'false':'true')});document.querySelector('#counter').textContent=(current+1)+' / '+slides.length;document.querySelector('#previous').disabled=current===0;document.querySelector('#next').disabled=current===slides.length-1;history.replaceState(null,'','#slide'+(current+1));window.scrollTo(0,0)}
document.querySelector('#previous').onclick=()=>show(current-1);document.querySelector('#next').onclick=()=>show(current+1);
document.addEventListener('keydown',e=>{if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();show(current+(e.key==='ArrowRight'?1:-1))}if(e.key==='Home'){e.preventDefault();show(0)}if(e.key==='End'){e.preventDefault();show(slides.length-1)}});
document.documentElement.classList.add('js');const initial=Number(location.hash.replace('#slide',''))-1;show(Number.isInteger(initial)&&initial>=0?initial:0);
window.addEventListener('beforeprint',()=>slides.forEach(s=>s.removeAttribute('aria-hidden')));window.addEventListener('afterprint',()=>show(current));
</script></body></html>'''
    return page.replace('ENERGY_BACKGROUND_DATA_URI', energy_background_uri())
