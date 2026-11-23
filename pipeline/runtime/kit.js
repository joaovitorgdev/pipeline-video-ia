// Runtime das cenas do kit (16:9). Tempos locais vêm das palavras do Whisper (assets/timing.js).
(function () {
  const norm = (w) => w.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]/g, "");
  function cena(nome) {
    const [ini, dur] = window.TIMING.cenas[nome];
    const words = window.TIMING.words
      .filter((w) => w.start >= ini - 0.01 && w.start < ini + dur)
      .map((w) => ({ n: norm(w.text), start: +(w.start - ini).toFixed(3), end: +(w.end - ini).toFixed(3) }));
    // início local da n-ésima ocorrência da frase (uma ou mais palavras)
    function acha(frase, n) {
      const alvo = frase.split(/\s+/).map(norm).filter(Boolean);
      let k = 0;
      for (let i = 0; i + alvo.length <= words.length; i++) {
        if (alvo.every((a, j) => words[i + j].n === a)) { if (k++ === n) return i; }
      }
      throw new Error(`"${frase}" não está na cena ${nome}`);
    }
    return {
      dur,
      at: (frase, n = 0) => words[acha(frase, n)].start,
      fim: (frase, n = 0) => { const alvo = frase.split(/\s+/).filter(Boolean).length; return words[acha(frase, n) + alvo - 1].end; },
    };
  }
  const E = {
    chip(tl, s, t) { tl.fromTo(s, { opacity: 0, y: 22, scale: 0.9 }, { opacity: 1, y: 0, scale: 1, duration: 0.22, ease: "back.out(2.2)", immediateRender: false }, t); },
    cartao(tl, s, t) { tl.fromTo(s, { opacity: 0, scale: 0.65, rotation: -3 }, { opacity: 1, scale: 1, rotation: 0, duration: 0.28, ease: "back.out(2)", immediateRender: false }, t); },
    doc(tl, s, t) { tl.fromTo(s, { opacity: 0, y: 60, rotation: -4 }, { opacity: 1, y: 0, rotation: -1.2, duration: 0.35, ease: "power3.out", immediateRender: false }, t); },
    polaroid(tl, s, t) { tl.fromTo(s, { opacity: 0, scale: 1.35, rotation: 9 }, { opacity: 1, scale: 1, rotation: -3, duration: 0.3, ease: "power3.out", immediateRender: false }, t); },
    carimbo(tl, s, t, rot = -6) {
      tl.fromTo(s, { opacity: 0, scale: 2.2, rotation: rot - 6 }, { opacity: 1, scale: 1, rotation: rot, duration: 0.16, ease: "power4.in", immediateRender: false }, t);
      tl.fromTo(s, { x: 0 }, { x: 9, duration: 0.04, yoyo: true, repeat: 3, ease: "none", immediateRender: false }, t + 0.16);
    },
    numero(tl, s, t) { tl.fromTo(s, { opacity: 0, scale: 0.7 }, { opacity: 1, scale: 1, duration: 0.22, ease: "back.out(2.5)", immediateRender: false }, t); },
    rotulo(tl, s, t) { tl.fromTo(s, { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.2, ease: "power2.out", immediateRender: false }, t); },
    pin(tl, s, t) { tl.fromTo(s, { opacity: 0, y: -60, scale: 0.6 }, { opacity: 1, y: 0, scale: 1, duration: 0.32, ease: "bounce.out", immediateRender: false }, t); },
    sai(tl, s, t, d = 0.18) { tl.to(s, { opacity: 0, duration: d, ease: "power2.in" }, t); },
  };
  function lista(tl, s, t, passo = 0.14) {
    const itens = document.querySelectorAll(s + " .item");
    tl.fromTo(s, { opacity: 0 }, { opacity: 1, duration: 0.15, immediateRender: false }, t);
    itens.forEach((el, k) => tl.fromTo(el, { opacity: 0, x: -60 }, { opacity: 1, x: 0, duration: 0.22, ease: "power3.out", immediateRender: false }, t + 0.08 + k * passo));
  }
  function risca(tl, s, t) {
    tl.fromTo(s + " .risco", { scaleX: 0 }, { scaleX: 1, duration: 0.25, ease: "power2.out", immediateRender: false }, t);
    tl.to(s, { opacity: 0.45, duration: 0.2 }, t + 0.2);
  }
  function tracar(tl, el, t, d = 0.9, ease = "power1.inOut") {
    const L = (el.getTotalLength && el.getTotalLength()) || 3000;
    tl.set(el, { strokeDasharray: L, strokeDashoffset: L }, 0);
    tl.set(el, { opacity: 1 }, t);
    tl.to(el, { strokeDashoffset: 0, duration: d, ease }, t);
  }
  function preenche(tl, el, t, d = 0.4) { tl.set(el, { fillOpacity: 0 }, 0); tl.fromTo(el, { fillOpacity: 0 }, { fillOpacity: 1, duration: d, immediateRender: false }, t); }
  function contador(tl, el, de, ate, t, d = 1.3, pre = "", suf = "", casas = 0, agrupa = true) {
    const o = { v: de };
    const fmt = (v) => pre + v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas, useGrouping: agrupa }) + suf;
    el.textContent = fmt(de);
    tl.to(o, { v: ate, duration: d, ease: "power2.out", onUpdate: () => { el.textContent = fmt(casas ? o.v : Math.round(o.v)); } }, t);
  }
  // câmera: leva o ponto (px, py) da tela para o centro com escala s
  function camera(tl, cam, t, px, py, s, d = 1.2) {
    tl.set(cam, { transformOrigin: "0 0" }, 0);
    tl.to(cam, { x: 960 - px * s, y: 540 - py * s, scale: s, duration: d, ease: "power2.inOut" }, t);
  }
  function anel(tl, el, t, r0 = 14, r1 = 90) {
    tl.fromTo(el, { attr: { r: r0 }, opacity: 1 }, { attr: { r: r1 }, opacity: 0, duration: 0.85, ease: "power2.out", immediateRender: false }, t);
  }
  window.Kit = { cena, E, lista, risca, tracar, preenche, contador, camera, anel, norm };
})();
