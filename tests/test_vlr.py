"""Testes do parser do vlr.gg.

Sem rede: o HTML de exemplo e um recorte fiel de `/matches/results` e
`/matches`. O que se testa e o que decide a corretude - qual time e o A, quem
venceu, o placar - porque um erro ai cola o resultado no time errado e o
Bradley-Terry aprende invertido.
"""

from __future__ import annotations

from datetime import timezone

from collectors.vlr import _parse_pagina

_RESULTADO = """
<div class="wf-label mod-large"> Fri, September 5, 2026 </div>
<a href="/734314/nrg-vs-loud-vct-2026-americas-stage-2-lbf" class="wf-module-item match-item mod-color">
  <div class="match-item-time"> 3:00 PM </div>
  <div class="match-item-vs">
    <div class="match-item-vs-team ">
      <div class="match-item-vs-team-name"> <div class="text-of"> <span class="flag mod-us"></span> NRG </div> </div>
      <div class="match-item-vs-team-score sp-mask mod-dash"> 2 </div>
    </div>
    <div class="match-item-vs-team mod-winner">
      <div class="match-item-vs-team-name"> <i class="fa fa-caret-right"></i> <div class="text-of"> <span class="flag mod-br"></span> LOUD </div> </div>
      <div class="match-item-vs-team-score sp-mask mod-dash"> 3 </div>
    </div>
  </div>
  <div class="match-item-eta"> <div class="ml mod-completed"> <div class="ml-status">Completed</div> </div> </div>
  <div class="match-item-event text-of">
    <div class="match-item-event-series text-of"> Playoffs&ndash;Lower Final </div>
    VCT 2026: Americas Stage 2
  </div>
  <div class="match-item-icon"> <img src="//x.png"> </div>
</a>
"""

_AGENDA = """
<div class="wf-label mod-large"> Sun, September 7, 2026 </div>
<a href="/742481/nrf-vs-ge" class="wf-module-item match-item mod-color">
  <div class="match-item-time"> 5:00 AM </div>
  <div class="match-item-vs">
    <div class="match-item-vs-team ">
      <div class="match-item-vs-team-name"> <div class="text-of"> <span class="flag mod-kr"></span> Nongshim RedForce </div> </div>
      <div class="match-item-vs-team-score mod-upcoming"> &ndash; </div>
    </div>
    <div class="match-item-vs-team ">
      <div class="match-item-vs-team-name"> <div class="text-of"> <span class="flag mod-in"></span> Global Esports </div> </div>
      <div class="match-item-vs-team-score mod-upcoming"> &ndash; </div>
    </div>
  </div>
  <div class="match-item-eta"> <div class="ml"> <div class="ml-status">Upcoming</div> </div> </div>
  <div class="match-item-event text-of">
    <div class="match-item-event-series text-of"> Playoffs&ndash;Grand Final </div>
    VCT 2026: Pacific Stage 2
  </div>
  <div class="match-item-icon"> <img src="//x.png"> </div>
</a>
"""


def test_resultado_traz_placar_vencedor_e_formato():
    (c,) = _parse_pagina(_RESULTADO)

    assert c.id_externo == "vlr:734314"
    assert (c.equipe_a_nome, c.placar_a) == ("NRG", 2)
    assert (c.equipe_b_nome, c.placar_b) == ("LOUD", 3)
    # LOUD venceu - o lado A (NRG) NAO venceu.
    assert c.vitoria_a is False
    assert c.formato == "Bo5"  # maior placar 3 -> melhor de 5
    assert c.torneio == "VCT 2026: Americas Stage 2 — Playoffs–Lower Final"
    assert c.inicio_previsto.date().isoformat() == "2026-09-05"
    assert c.inicio_previsto.tzinfo == timezone.utc
    assert c.inicio_previsto.hour == 15  # 3:00 PM


def test_agenda_fica_sem_resultado():
    (c,) = _parse_pagina(_AGENDA)

    assert c.id_externo == "vlr:742481"
    assert c.equipe_a_nome == "Nongshim RedForce"
    assert c.equipe_b_nome == "Global Esports"
    assert c.vitoria_a is None
    assert c.placar_a is None and c.placar_b is None
    assert c.formato is None
    assert c.inicio_previsto.date().isoformat() == "2026-09-07"


def test_pagina_vazia_nao_quebra():
    assert _parse_pagina("<html><body>nada</body></html>") == []
