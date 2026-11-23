"""Uma composição HyperFrames (HTML + timeline GSAP) por cena do roteiro.

Cada peça entra sincronizada com uma palavra falada (`em`), achada nos tempos do Whisper.
Peças de mapa (contorno, pin, seta...) são projetadas de lon/lat para pixel com a mesma Vista do fundo.
"""
import html
import json
import os

from .legendas import acha, esc
from .mapas import Vista, aneis, caixa, caminho, geo

W, H = 1920, 1080
CORES = {'am': '#FFD23F', 'vm': '#E8392B', 'az': '#38BDF8', 'vd': '#2BC46A', 'br': '#FFFFFF', 'lj': '#FF8A1F'}
# slot -> (left, top, centralizado)
SLOTS = {'esq': (80, 190, False), 'esq2': (80, 560, False), 'dir': (1200, 190, False), 'dir2': (1200, 560, False),
         'topo': (960, 120, True), 'centro': (960, 330, True), 'baixo': (960, 640, True)}
PADRAO = {'chip': 'topo', 'cartao': 'esq', 'doc': 'esq', 'carimbo': 'centro', 'numero': 'dir', 'lista': 'esq',
          'polaroid': 'dir', 'compara': 'centro'}
# tipo de peça -> (efeito sonoro, volume)
SFX = {'chip': ('pop', .42), 'pin': ('pop', .42), 'rotulo': ('pop', .3), 'cartao': ('whoosh-short', .38), 'doc': ('whoosh-short', .38),
       'lista': ('whoosh-short', .32), 'polaroid': ('click', .5), 'carimbo': ('impact-bass-1', .55), 'numero': ('pop', .48),
       'compara': ('whoosh-short', .38), 'contorno': ('click', .32), 'poligono': ('click', .32), 'linha': ('whoosh-short', .28),
       'seta': ('whoosh-short', .3), 'camera': ('whoosh', .32), 'anel': ('pop', .3), 'corte': ('whoosh-short', .3)}
PECAS_TELA = {'chip', 'cartao', 'doc', 'carimbo', 'numero', 'lista', 'risca', 'polaroid', 'compara', 'corte', 'som', 'sai'}
PECAS_MAPA = {'contorno', 'poligono', 'linha', 'seta', 'pin', 'anel', 'rotulo', 'camera'}
TIPOS_FX = PECAS_TELA | PECAS_MAPA
FUNDOS = {'mapa', 'foto', 'video', 'papel'}


class Cena:
    def __init__(self, cid, c, words, dur, vistas, video, creditos=None):
        self.id, self.c, self.words, self.dur, self.video = cid, c, words, dur, video
        self.creditos = creditos or {}
        self.html, self.js, self.sons, self.cam_html = [], [], [], []
        self.svg, self.slots, self.k = [], {}, 0
        f = c.get('fundo', {'tipo': 'papel'})
        self.vista = None
        if f.get('tipo') == 'mapa':
            v = vistas[f['vista']]
            self.vista = Vista(f['vista'], tuple(v['centro']), v['zoom'], v.get('camada', 'bm'))
            self.vista.fundo(os.path.join(video, 'assets', 'mapas', f['vista'] + '.jpg'))

    def t(self, fx, chave='em'):
        em = fx.get(chave, '^')
        if em == '^':
            return 0.0
        if isinstance(em, (int, float)):
            return float(em)
        return round(max(0.0, acha(self.words, em, fx.get('n', 0)) + fx.get('desl', -0.06)), 3)

    def novo(self):
        self.k += 1
        return f'{self.id}-f{self.k}'

    def som(self, tipo, t):
        if tipo in SFX:
            self.sons.append((t, *SFX[tipo]))

    def ocupa(self, slot, fid, t, fica=False):
        """Peça nova num slot ocupado tira a anterior (a menos que a anterior tenha `fica`)."""
        ant = self.slots.get(slot)
        if ant and not ant[1]:
            self.js.append(f'Kit.E.sai(tl, "#{ant[0]}", {max(0.0, t - 0.14):.3f});')
        self.slots[slot] = (fid, fica)

    # -- peças na tela
    def peca(self, fx, interno, entrada):
        fid = fx.get('id') and f'{self.id}-{fx["id"]}' or self.novo()
        slot = fx.get('pos', PADRAO.get(fx['tipo'], 'esq'))
        left, top, centro = SLOTS[slot] if isinstance(slot, str) else (*slot, False)
        if isinstance(fx.get('xy'), list):
            left, top = fx['xy']
        t = self.t(fx)
        self.ocupa(slot if isinstance(slot, str) else tuple(slot), fid, t, fx.get('fica', False))
        self.html.append(f'<div id="{fid}" class="ov{" centro" if centro else ""}" style="left:{left}px;top:{top}px">{interno}</div>')
        self.js.append(entrada.format(s=f'"#{fid}"', t=f'{t:.3f}'))
        if fx.get('ate'):
            self.js.append(f'Kit.E.sai(tl, "#{fid}", {self.t(fx, "ate"):.3f});')
        self.som(fx['tipo'], t)
        return fid, t

    # -- peças no mapa
    def xy(self, fx):
        if 'lnglat' in fx:
            return self.vista.proj(*fx['lnglat'])
        return caixa(self.vista, aneis(geo(fx['geo'])))[1]

    def fx(self, fx):
        tp = fx['tipo']
        if tp in PECAS_MAPA and self.vista is None and tp != 'camera':
            raise SystemExit(f'{self.id}: peça de mapa "{tp}" numa cena sem fundo de mapa')
        cor = CORES.get(fx.get('cor', 'am'), fx.get('cor', '#FFD23F'))
        if tp in ('chip', 'cartao', 'doc', 'carimbo', 'numero', 'lista', 'polaroid', 'compara'):
            self._peca_tela(tp, fx)
        elif tp == 'risca':
            alvo = f'#{self.id}-{fx["lista"]}-i{fx["item"]}'
            t = self.t(fx)
            self.js.append(f'Kit.risca(tl, "{alvo}", {t:.3f});')
            self.sons.append((t, 'click', 0.45))
        elif tp in ('contorno', 'poligono', 'linha', 'seta'):
            self._traco(tp, fx, cor)
        elif tp == 'pin':
            fid = self.novo()
            x, y = self.xy(fx)
            t = self.t(fx)
            self.svg.append(f'<g id="{fid}" opacity="0"><g transform="translate({x},{y})"><path d="M0 0 C-6 -14 -20 -22 -20 -36 A20 20 0 1 1 20 -36 '
                            f'C20 -22 6 -14 0 0 Z" fill="{cor}" stroke="#0B0F18" stroke-width="4" /><circle cx="0" cy="-36" r="7" fill="#0B0F18" /></g></g>')
            self.js.append(f'Kit.E.pin(tl, "#{fid}", {t:.3f});')
            if fx.get('rotulo'):
                dx, dy = fx.get('rot_desl', [0, -72])
                self.rotulo(fx['rotulo'], x + dx, y + dy, t + 0.15, fx.get('rot_classe', ''))
            self.som('pin', t)
        elif tp == 'anel':
            fid = self.novo()
            x, y = self.xy(fx)
            t = self.t(fx)
            self.svg.append(f'<circle id="{fid}a" cx="{x}" cy="{y}" r="14" fill="none" stroke="{cor}" stroke-width="6" opacity="0" />'
                            f'<circle id="{fid}b" cx="{x}" cy="{y}" r="14" fill="none" stroke="{cor}" stroke-width="6" opacity="0" />')
            self.js.append(f'Kit.anel(tl, document.getElementById("{fid}a"), {t:.3f}); Kit.anel(tl, document.getElementById("{fid}b"), {t + 0.45:.3f});')
            self.som('anel', t)
        elif tp == 'rotulo':
            x, y = self.xy(fx)
            dx, dy = fx.get('rot_desl', [0, 0])
            self.rotulo(fx['texto'], x + dx, y + dy, self.t(fx), fx.get('classe', 'grande'))
        elif tp == 'camera':
            x, y = self.xy(fx) if ('lnglat' in fx or 'geo' in fx) else (W / 2, H / 2)
            t = self.t(fx)
            self.js.append(f'Kit.camera(tl, "#{self.id}-cam", {t:.3f}, {x}, {y}, {fx.get("zoom", 1.6)}, {fx.get("dur", 1.3)});')
            self.som('camera', t)
        elif tp == 'corte':
            self._corte(fx)
        elif tp == 'som':
            self.sons.append((self.t(fx), fx['som'], fx.get('vol', 0.5)))
        elif tp == 'sai':
            t = self.t(fx)
            for a in fx['alvo'] if isinstance(fx['alvo'], list) else [fx['alvo']]:
                self.js.append(f'Kit.E.sai(tl, "#{self.id}-{a}", {t:.3f});')
        else:
            raise SystemExit(f'fx desconhecido: {tp}')

    def _peca_tela(self, tp, fx):
        if tp == 'chip':
            self.peca(fx, f'<div class="chip {fx.get("estilo", "")}">{esc(fx["texto"])}</div>', 'Kit.E.chip(tl, {s}, {t});')
        elif tp == 'cartao':
            small = f'<small>{esc(fx["small"])}</small>' if fx.get('small') else ''
            self.peca(fx, f'<div class="cartao">{small}{esc(fx["texto"])}</div>', 'Kit.E.cartao(tl, {s}, {t});')
        elif tp == 'doc':
            self.peca(fx, f'<div class="doc">“{esc(fx["texto"])}”<span class="de">{esc(fx.get("de", ""))}</span></div>', 'Kit.E.doc(tl, {s}, {t});')
        elif tp == 'carimbo':
            fs = min(88, int(1250 / (len(fx['texto']) * 0.78)))
            self.peca(fx, f'<div class="carimbo {fx.get("estilo", "")}" style="font-size:{fs}px">{esc(fx["texto"])}</div>',
                      'Kit.E.carimbo(tl, {s}, {t}, ' + str(fx.get('rot', -6)) + ');')
        elif tp == 'numero':
            txt = f'{fx.get("pre", "")}{fx["ate"]:{"" if fx.get("ano") else ","}.{fx.get("casas", 0)}f}{fx.get("suf", "")}'.replace(',', '.')
            fs = min(150, int(660 / (len(txt) * 0.74)))
            rot = f'<small>{esc(fx["rotulo"])}</small>' if fx.get('rotulo') else ''
            fid, t = self.peca(fx, f'<div class="numero" style="font-size:{fs}px"><span>0</span>{rot}</div>', 'Kit.E.numero(tl, {s}, {t});')
            self.js.append(f'Kit.contador(tl, document.querySelector("#{fid} .numero span"), {fx.get("de", 0)}, {fx["ate"]}, {t + 0.05:.3f}, '
                           f'{fx.get("dur", 1.3)}, {json.dumps(fx.get("pre", ""))}, {json.dumps(fx.get("suf", ""))}, {fx.get("casas", 0)}, '
                           f'{"false" if fx.get("ano") else "true"});')
            self.sons.append((t + fx.get('dur', 1.3), 'sparkle', 0.3))
        elif tp == 'lista':
            fid = fx.get('id') and f'{self.id}-{fx["id"]}' or f'{self.id}-f{self.k + 1}'
            itens = ''.join(f'<div class="item" id="{fid}-i{k}">{esc(x)}<div class="risco"></div></div>' for k, x in enumerate(fx['itens']))
            fid, t = self.peca(fx, f'<div class="lista">{itens}</div>', 'Kit.lista(tl, {s}, {t});')
            self.js.append(f'tl.set("#{fid} .risco", {{ scaleX: 0 }}, 0);')
        elif tp == 'polaroid':
            src = f'assets/fotos/{fx["img"]}'
            self.peca(fx, f'<div class="polaroid"><img src="{src}" alt="{html.escape(fx.get("legenda", ""))}" /><span>{esc(fx.get("legenda", ""))}</span></div>',
                      'Kit.E.polaroid(tl, {s}, {t});')
        elif tp == 'compara':
            a, b = fx['antes'], fx['depois']
            self.peca(fx, f'<div class="compara"><div class="antes"><small>{esc(a[0])}</small><strong>{esc(a[1])}</strong></div>'
                          f'<div class="depois"><small>{esc(b[0])}</small><strong>{esc(b[1])}</strong></div></div>', 'Kit.E.cartao(tl, {s}, {t});')

    def _traco(self, tp, fx, cor):
        fid = fx.get('id') and f'{self.id}-{fx["id"]}' or self.novo()
        t = self.t(fx)
        anel = None
        if tp == 'contorno':
            refs = fx['geo'] if isinstance(fx['geo'], list) else [fx['geo']]
            anel = [a for r in refs for a in aneis(geo(r))]
            d = caminho(self.vista, anel)
        elif tp == 'poligono':
            anel = [fx['coords']]
            d = caminho(self.vista, anel)
        elif tp == 'linha':
            anel = [fx['coords']]
            d = caminho(self.vista, anel, fecha=False, tol=0.6)
        else:  # seta curva de A para B
            (x0, y0), (x1, y1) = self.vista.proj(*fx['de']), self.vista.proj(*fx['para'])
            mx, my = (x0 + x1) / 2 - (y1 - y0) * 0.25, (y0 + y1) / 2 + (x1 - x0) * 0.25
            d = f'M{x0} {y0} Q{mx:.1f} {my:.1f} {x1} {y1}'
        fecha = tp in ('contorno', 'poligono')
        fill = (cor + '40') if fecha and fx.get('preenche', True) else 'none'
        larg = fx.get('larg', 5 if fecha else 6)
        tr = ' stroke-dasharray="14 12"' if fx.get('tracejado') else ''
        mk = f' marker-end="url(#{self.id}-seta)"' if tp == 'seta' else ''
        self.svg.append(f'<path id="{fid}" d="{d}" fill="{fill}" stroke="{cor}" stroke-width="{larg}" stroke-linejoin="round" '
                        f'stroke-linecap="round" vector-effect="non-scaling-stroke" opacity="0"{tr}{mk} />')
        dur = fx.get('dur', 0.9 if tp != 'seta' else 0.6)
        if fx.get('tracejado'):
            self.js.append(f'tl.fromTo("#{fid}", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.3, immediateRender: false }}, {t:.3f});')
        else:
            self.js.append(f'Kit.tracar(tl, document.getElementById("{fid}"), {t:.3f}, {dur});')
        if fill != 'none':
            self.js.append(f'Kit.preenche(tl, document.getElementById("{fid}"), {t + dur * 0.7:.3f});')
        if fx.get('pisca'):
            self.js.append(f'tl.fromTo("#{fid}", {{ strokeWidth: {larg} }}, {{ strokeWidth: {larg * 2.4}, duration: 0.18, yoyo: true, repeat: 3, '
                           f'immediateRender: false }}, {t + dur:.3f});')
        if fx.get('rotulo') and anel:
            cx, cy = caixa(self.vista, anel)[1]
            dx, dy = fx.get('rot_desl', [0, 0])
            self.rotulo(fx['rotulo'], cx + dx, cy + dy, t + dur * 0.6, fx.get('rot_classe', 'grande'))
        if fx.get('ate'):
            self.js.append(f'Kit.E.sai(tl, "#{fid}", {self.t(fx, "ate"):.3f});')
        self.som(tp, t)

    def _corte(self, fx):
        """Corte rápido para b-roll (foto ou vídeo do Commons) com crédito na tela."""
        fid = self.novo()
        t = self.t(fx)
        dur = round(min(fx.get('dur', 2.4), max(0.6, self.dur - t - 0.05)), 3)
        src = f'assets/broll/{fx["midia"]}'
        janela = fx.get('estilo') == 'janela'
        if src.endswith('.mp4'):
            media = f'<video id="{fid}-v" class="clip" src="{src}" muted playsinline data-start="{t:.3f}" data-duration="{dur}"></video>'
        else:
            media = f'<img id="{fid}-v" src="{src}" alt="{html.escape(fx.get("legenda", ""))}" />'
        leg = f'<div class="leg">{esc(fx["legenda"])}</div>' if fx.get('legenda') else ''
        cred = self.creditos.get(fx['midia'].rsplit('.', 1)[0], '')
        cred_html = f'<div class="cred" data-layout-ignore>{html.escape(cred.split(" - Wikimedia")[0][:110])}</div>' if cred else ''
        lado = ' dir' if fx.get('lado') == 'dir' else ''
        self.html.append(f'<div id="{fid}" class="corte{" janela" if janela else ""}{lado}">{media}{leg}{cred_html}</div>')
        if janela:
            self.js.append(f'tl.fromTo("#{fid}", {{ opacity: 0, scale: 1.25, rotation: 6 }}, {{ opacity: 1, scale: 1, rotation: -2, duration: 0.28, '
                           f'ease: "power3.out", immediateRender: false }}, {t:.3f});')
        else:
            self.js.append(f'tl.fromTo("#{fid}", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.08, immediateRender: false }}, {t:.3f});')
        a, b = (1.14, 1.0) if fx.get('kb', 'out') == 'out' else (1.0, 1.12)
        self.js.append(f'tl.fromTo("#{fid}-v", {{ scale: {a} }}, {{ scale: {b}, duration: {dur}, ease: "none", immediateRender: false }}, {t:.3f});')
        if fx.get('legenda'):
            self.js.append(f'tl.fromTo("#{fid} .leg", {{ opacity: 0, x: -30 }}, {{ opacity: 1, x: 0, duration: 0.2, immediateRender: false }}, {t + 0.1:.3f});')
        self.js.append(f'tl.to("#{fid}", {{ opacity: 0, duration: 0.1 }}, {t + dur - 0.1:.3f});')
        self.som('corte', t)

    def rotulo(self, texto, x, y, t, classe=''):
        fid = self.novo()
        self.cam_html.append(f'<div id="{fid}" class="rotulo {classe}" style="left:{x:.0f}px;top:{y:.0f}px"><span>{esc(texto)}</span></div>')
        self.js.append(f'Kit.E.rotulo(tl, "#{fid}", {t:.3f});')
        self.som('rotulo', t)

    def _fundo(self, f):
        """HTML do fundo e texto de crédito da fonte."""
        cid = self.id
        if f['tipo'] == 'mapa':
            fundo = f'<img class="fundo" src="assets/mapas/{f["vista"]}.jpg" alt="mapa" />'
            if f.get('ufs', True):
                d = ' '.join(caminho(self.vista, aneis(ft), tol=1.6) for ft in geo('br')['features'])
                self.svg.insert(0, f'<path d="{d}" fill="none" stroke="#FFFFFF" stroke-opacity="0.38" stroke-width="1.6" vector-effect="non-scaling-stroke" />')
            usa_ibge = f.get('ufs', True) or 'geo' in json.dumps(self.c.get('fx', []))
            credito = self.vista.credito() + (' • Malhas: IBGE' if usa_ibge else '')
            if f.get('empurra', True) and not any(x['tipo'] == 'camera' for x in self.c.get('fx', [])):  # câmera nunca parada
                self.js.insert(0, f'tl.fromTo("#{cid}-cam", {{ scale: 1, x: 0, y: 0, transformOrigin: "0 0" }}, '
                                  f'{{ scale: 1.035, x: -34, y: -19, duration: {self.dur:.2f}, ease: "none" }}, 0);')
            return fundo, credito
        if f['tipo'] == 'video':
            fundo = (f'<video id="{cid}-vid" class="clip fundo" src="assets/videos/{f["src"]}" muted playsinline data-start="0" '
                     f'data-duration="{f.get("dur", self.dur):.3f}" style="position:absolute;left:0;top:0;width:1920px;height:1080px"></video>')
            if f.get('fim'):  # quadro final segura depois do vídeo
                fundo = (f'<img class="fundo" src="assets/videos/{f["fim"]}" alt="" style="position:absolute;left:0;top:0;width:1920px;'
                         f'height:1080px" />' + fundo)
            return fundo, f.get('fonte', '')
        if f['tipo'] == 'foto':
            cls = ' contem' if f.get('ajuste') == 'contem' else ''
            fundo = f'<div class="foto{cls}" id="{cid}-foto"><img src="assets/fotos/{f["img"]}" alt="{html.escape(f.get("fonte", ""))}" /></div>'
            a, b = (1.0, 1.09) if f.get('kb', 'in') == 'in' else (1.09, 1.0)
            self.js.insert(0, f'tl.fromTo("#{cid}-foto", {{ scale: {a} }}, {{ scale: {b}, duration: {self.dur:.2f}, ease: "none" }}, 0);')
            return fundo, f.get('fonte', '')
        return '', ''

    def monta(self, lead):
        c, cid = self.c, self.id
        f = c.get('fundo', {'tipo': 'papel'})
        fundo, credito = self._fundo(f)
        for fx in c.get('fx', []):
            self.fx(fx)
        cap = ''
        if c.get('capitulo'):
            k = c['capitulo']
            cap = (f'<div id="{cid}-cap" class="capitulo"><div class="n"><span>CAPÍTULO {k["n"]}</span></div><h1>{esc(k["titulo"])}</h1>'
                   f'<p>{esc(k.get("pergunta", ""))}</p></div>')
            self.js.append(f'tl.fromTo("#{cid}-cap", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.2, immediateRender: false }}, 0);')
            self.js.append(f'tl.fromTo("#{cid}-cap h1", {{ scale: 1.15 }}, {{ scale: 1, duration: 0.5, ease: "power3.out", immediateRender: false }}, 0.05);')
            self.js.append(f'tl.to("#{cid}-cap", {{ opacity: 0, duration: 0.3 }}, {lead + 0.15:.3f});')
            self.sons += [(0.02, 'whoosh', 0.45), (0.35, 'impact-bass-2', 0.4)]
        svg = f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
        if f['tipo'] == 'foto':
            cam = fundo + f'<div class="cam" id="{cid}-cam">{svg}{"".join(self.svg)}</svg>{"".join(self.cam_html)}</div>'
        elif f['tipo'] == 'papel':
            cam = f'<div class="papel"></div><div class="cam" id="{cid}-cam"></div>'
        else:
            cam = (f'<div class="cam" id="{cid}-cam">{fundo}{svg}'
                   f'<defs><marker id="{cid}-seta" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">'
                   f'<path d="M0 0 L10 5 L0 10 Z" fill="#FFD23F" /></marker></defs>{"".join(self.svg)}</svg>{"".join(self.cam_html)}</div>')
        cred = f'<div class="credito" data-layout-ignore>{html.escape(credito)}</div>' if credito else ''
        js = '\n      '.join(self.js)
        return f'''<template>
  <style>#root {{ position: absolute; inset: 0; overflow: hidden; background: #05070d; }}</style>
  <div id="root" data-composition-id="{cid}" data-width="{W}" data-height="{H}">
    {cam}
    <div class="vinheta"></div>
    {"".join(self.html)}
    {cred}
    {cap}
  </div>
  <script>
    (function () {{
      const tl = gsap.timeline({{ paused: true }});
      {js}
      tl.set({{}}, {{}}, {self.dur:.3f});
      window.__timelines["{cid}"] = tl;
    }})();
  </script>
</template>
'''
