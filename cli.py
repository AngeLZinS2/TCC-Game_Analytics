"""Ponto de entrada de linha de comando.

    python cli.py init-db
    python cli.py collect steam
    python cli.py collect steam --apps 570,730 --no-load
    python cli.py collect opendota --limite 100
    python cli.py collect opendota --from-raw     # reprocessa sem chamar a API
    python cli.py stats
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict

from config import BASE_DIR, get_settings
from logging_config import configurar_logging

FONTES = (
    "steam",
    "opendota",
    "liquipedia",
    "liquipedia-times",
    "liquipedia-bracket",
    "valve-standings",
    "itad",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gaming-analytics")
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("init-db", help="aplica as migrations (alembic upgrade head)")

    coletar = sub.add_parser("collect", help="executa um coletor")
    coletar.add_argument("fonte", choices=FONTES)
    coletar.add_argument(
        "--no-load", action="store_true", help="coleta e normaliza, mas nao grava no banco"
    )
    coletar.add_argument(
        "--from-raw",
        action="store_true",
        help="reprocessa os payloads ja gravados em disco, sem chamar a API",
    )

    steam = coletar.add_argument_group("steam")
    steam.add_argument(
        "--apps", help="lista de app_ids separados por virgula (sobrepoe a semente)"
    )
    steam.add_argument(
        "--steamspy-top",
        type=int,
        metavar="N",
        help="usa os N jogos mais jogados nas ultimas 2 semanas (SteamSpy)",
    )
    steam.add_argument(
        "--all-apps",
        action="store_true",
        help=(
            "descobre todos os apps da Steam via ISteamApps/GetAppList. "
            "Combine com --min-players para filtrar e --limit-apps para limitar. "
            "Sem filtros, sao ~200k apps (pode levar semanas)."
        ),
    )
    steam.add_argument(
        "--min-players",
        type=int,
        default=0,
        metavar="N",
        help=(
            "com --all-apps: descarta apps com menos de N jogadores nas "
            "ultimas 2 semanas segundo o SteamSpy (0 = sem filtro)"
        ),
    )
    steam.add_argument(
        "--limit-apps",
        type=int,
        default=0,
        metavar="N",
        help="limita o total de apps a coletar (0 = sem limite; util para testes)",
    )

    liquipedia = coletar.add_argument_group(
        "liquipedia / liquipedia-times / liquipedia-bracket"
    )
    liquipedia.add_argument(
        "--wiki",
        default="dota2",
        help="codigo da wiki da Liquipedia (ver collectors/seeds/liquipedia_wikis.json)",
    )
    liquipedia.add_argument(
        "--todas-wikis",
        action="store_true",
        help="percorre TODAS as wikis do registro que suportam esta fonte",
    )

    equipes = coletar.add_argument_group("liquipedia-times")
    equipes.add_argument(
        "--limite-equipes",
        type=int,
        metavar="N",
        help="le so as N primeiras equipes da categoria (util para testar)",
    )

    bracket = coletar.add_argument_group("liquipedia-bracket")
    bracket.add_argument(
        "--torneio",
        action="append",
        metavar="PAGINA",
        help=(
            "titulo de uma pagina de torneio a coletar (repita para varios). "
            "Sem isso, le os torneios distintos ja vistos em agenda_partida "
            "para esta wiki."
        ),
    )

    valve = coletar.add_argument_group("valve-standings")
    valve.add_argument(
        "--todos",
        action="store_true",
        help=(
            "coleta todos os snapshots mensais do ranking desde 2024 "
            "(backfill; sem isso pega so o mais recente)"
        ),
    )

    itad = coletar.add_argument_group("itad")
    itad.add_argument(
        "--limite-jogos",
        type=int,
        metavar="N",
        help="consulta preco so dos N primeiros jogos pagos (util para testar)",
    )
    itad.add_argument(
        "--forcar-lookup",
        action="store_true",
        help="refaz o lookup do ITAD mesmo para jogos que ja tem itad_id",
    )

    opendota = coletar.add_argument_group("opendota")
    opendota.add_argument(
        "--limite",
        type=int,
        default=100,
        metavar="N",
        help="quantas partidas profissionais coletar (padrao: 100)",
    )
    opendota.add_argument(
        "--recoletar",
        action="store_true",
        help="nao pula partidas ja presentes em dim_partida",
    )

    sub.add_parser("stats", help="contagem de linhas por tabela")
    sub.add_parser(
        "seed-jogos", help="sincroniza dim_jogo com o registro de wikis da Liquipedia"
    )

    sentimento = sub.add_parser(
        "train-sentimento",
        help="treina os classificadores de sentimento sobre o texto das avaliacoes",
    )
    sentimento.add_argument(
        "--idioma",
        default=None,
        help="idioma das avaliacoes (padrao: o mais coletado)",
    )

    confronto = sub.add_parser(
        "train-confronto",
        help="ajusta a forca das equipes (Bradley-Terry) para prever confrontos",
    )
    confronto.add_argument("--jogo", default="dota2", help="codigo em dim_jogo")
    return parser


def _cmd_init_db() -> int:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "db" / "migrations"))
    command.upgrade(cfg, "head")
    print("Migrations aplicadas (head).")
    return 0


def _construir_coletor(args: argparse.Namespace, storage):
    """Instancia o coletor da fonte pedida, com os argumentos que sao dela."""
    settings = get_settings()

    if args.fonte == "steam":
        from collectors.steam_collector import SteamCollector

        app_ids = None
        if args.apps:
            app_ids = [int(parte) for parte in args.apps.split(",") if parte.strip()]
        coletor = SteamCollector(
            raw_storage=storage, app_ids=app_ids, settings=settings
        )
        # Prioridade: --apps > --steamspy-top > --all-apps > semente
        if args.steamspy_top:
            coletor.app_ids = coletor.apps_mais_jogados(args.steamspy_top)
        elif args.all_apps:
            coletor.app_ids = coletor.todos_os_apps(
                minimo_jogadores=args.min_players,
                limite=args.limit_apps,
            )
        elif args.limit_apps and not args.apps:
            # --limit-apps sem --all-apps: trunca a semente/resultado anterior
            coletor.app_ids = coletor.app_ids[: args.limit_apps]
        return coletor

    if args.fonte == "liquipedia":
        from collectors.liquipedia_collector import LiquipediaCollector

        return LiquipediaCollector(
            raw_storage=storage, settings=settings, wiki=args.wiki
        )

    if args.fonte == "liquipedia-times":
        from collectors.liquipedia_wiki_collector import LiquipediaWikiCollector

        return LiquipediaWikiCollector(
            raw_storage=storage,
            settings=settings,
            wiki=args.wiki,
            limite_equipes=args.limite_equipes,
        )

    if args.fonte == "liquipedia-bracket":
        from collectors.liquipedia_bracket_collector import LiquipediaBracketCollector

        return LiquipediaBracketCollector(
            raw_storage=storage,
            settings=settings,
            wiki=args.wiki,
            torneios=args.torneio,
        )

    if args.fonte == "valve-standings":
        from collectors.valve_standings_collector import ValveStandingsCollector

        return ValveStandingsCollector(
            raw_storage=storage,
            settings=settings,
            todos=args.todos,
        )

    if args.fonte == "itad":
        from collectors.itad_collector import ItadCollector

        return ItadCollector(
            raw_storage=storage,
            settings=settings,
            limite=args.limite_jogos,
            forcar_lookup=args.forcar_lookup,
        )

    from collectors.opendota_collector import OpenDotaCollector

    return OpenDotaCollector(
        raw_storage=storage,
        limite=args.limite,
        settings=settings,
        pular_existentes=not args.recoletar,
    )


def _carregador(fonte: str):
    if fonte == "steam":
        from etl.load_steam import carregar

        return carregar
    if fonte == "liquipedia":
        from etl.load_liquipedia import carregar

        return carregar
    if fonte == "liquipedia-times":
        from etl.load_liquipedia_wiki import carregar

        return carregar
    if fonte == "liquipedia-bracket":
        from etl.load_liquipedia import carregar

        return carregar
    if fonte == "valve-standings":
        from etl.load_valve_standings import carregar

        return carregar
    if fonte == "itad":
        from etl.load_itad import carregar

        return carregar
    from etl.load_dota import carregar

    return carregar


def _cmd_collect(args: argparse.Namespace) -> int:
    from etl.raw_storage import RawStorage

    settings = get_settings()
    storage = RawStorage(settings.raw_data_path, registrar_no_banco=not args.no_load)
    coletor = _construir_coletor(args, storage)

    try:
        if args.from_raw:
            registros = storage.ler_ultima_coleta(coletor.fonte)
            print(f"Reprocessando {len(registros)} payloads do disco...")
            resultado = coletor.parse(registros)
            if args.fonte == "valve-standings":
                # `parse` devolve uma lista de snapshots (um por mes), e o
                # proprio coletor sabe carregar a lista. `resultado.total` nao
                # existe aqui - o "normalizado" e a soma das linhas.
                carregados = 0 if args.no_load else coletor.load(resultado)
                normalizados = sum(r.total for r in resultado)
                print(f"itens normalizados={normalizados} carregados={carregados}")
                return 0
            if args.no_load:
                carregados = 0
            elif args.fonte.startswith("liquipedia"):
                # As tres fontes da Liquipedia carregam por wiki
                # (`jogo=args.wiki`). Sem isso, `_carregador` cai no padrao
                # `jogo="dota2"` do proprio `carregar()` - e um
                # `--from-raw --wiki counterstrike` reprocessaria os dados
                # certos, mas gravaria tudo como se fosse Dota 2.
                carregados = _carregador(args.fonte)(resultado, jogo=args.wiki)
            else:
                carregados = _carregador(args.fonte)(resultado)
            print(f"itens normalizados={resultado.total} carregados={carregados}")
            return 0

        execucao = coletor.run(carregar=not args.no_load)
    finally:
        coletor.close()

    for chave, valor in asdict(execucao).items():
        print(f"{chave:24} {valor}")
    return 0 if execucao.sucesso else 1


def _cmd_stats() -> int:
    from sqlalchemy import func, select

    from db.models import (
        DimJogador,
        DimJogoSteam,
        DimPartida,
        DimPersonagem,
        DimTempo,
        FatoPartidaJogador,
        FatoSnapshotJogoSteam,
        RawData,
    )
    from db.session import session_scope

    grupos = {
        "transversal": (RawData,),
        "catalogo/mercado (steam)": (DimJogoSteam, FatoSnapshotJogoSteam),
        "partidas (esports)": (
            DimTempo,
            DimJogador,
            DimPersonagem,
            DimPartida,
            FatoPartidaJogador,
        ),
    }

    with session_scope() as sessao:
        for titulo, modelos in grupos.items():
            print(f"\n{titulo}")
            for modelo in modelos:
                total = sessao.scalar(select(func.count()).select_from(modelo))
                print(f"  {modelo.__tablename__:32} {total}")
    return 0


def _cmd_seed_jogos() -> int:
    from etl.load_jogos import sincronizar
    from etl.wikis import registro

    criados = sincronizar()
    print(f"{len(registro())} wikis no registro; {criados} jogos criados agora")
    return 0


def _cmd_train_sentimento(args) -> int:
    from ml.sentimento import treinar

    relatorio = treinar(idioma=args.idioma)
    conjunto = relatorio["conjunto"]

    print(
        f"{conjunto['avaliacoes']} avaliacoes em {relatorio['idioma']} "
        f"({conjunto['treino']} treino / {conjunto['teste']} teste, de "
        f"{conjunto['total_no_banco']} no banco em todos os idiomas)"
    )
    print(
        f"descartadas por texto curto (<{conjunto['minimo_caracteres']} chars): "
        f"{conjunto['descartadas_curtas']}"
    )
    print(f"taxa base (recomendadas): {conjunto['taxa_base']:.1%}" + chr(10))

    print(f"{'modelo':<34} {'acur':>7} {'balanc':>8} {'roc_auc':>9} {'f1_neg':>8}")
    for modelo in relatorio["modelos"]:
        marca = " *" if modelo["chave"] == relatorio["modelo_ativo"] else "  "
        print(
            f"{modelo['nome']:<34}{marca}{modelo['acuracia']:>5.1%} "
            f"{modelo['acuracia_balanceada']:>7.1%} {modelo['roc_auc']:>9.4f} "
            f"{modelo['f1_negativa']:>8.3f}"
        )

    print(
        chr(10) + f"* modelo servido pela API: {relatorio['modelo_ativo']} (maior ROC-AUC)"
    )
    return 0


def _cmd_train_confronto(args) -> int:
    from ml.confronto import ajustar_e_salvar, ranking

    relatorio = ajustar_e_salvar(jogo=args.jogo)
    validacao = relatorio["validacao"]

    print(
        f"{relatorio['confrontos']} confrontos entre {relatorio['equipes']} equipes "
        f"(C={relatorio['regularizacao_C']}, escolhido por CV no treino)"
    )
    print(
        f"vantagem do lado A: {relatorio['vantagem_lado_a']:+.4f} log-odds = "
        f"{relatorio['probabilidade_lado_a_entre_iguais']:.1%} entre times de forca igual"
    )

    if validacao["suficiente"]:
        print(
            chr(10) + f"validacao walk-forward em {validacao['avaliadas']} partidas:"
        )
        print(
            f"  acuracia {validacao['acuracia']:.1%} +/- {validacao['margem_erro']:.1%}"
            f"  (taxa base {validacao['taxa_base']:.1%})"
        )
        print(
            f"  ROC-AUC {validacao['roc_auc']:.4f} | Brier {validacao['brier']:.4f}"
        )
        if validacao["acuracia"] <= validacao["taxa_base"]:
            print(
                "  AVISO: a acuracia nao supera a taxa base. Com esta amostra o "
                "modelo ainda nao demonstrou poder preditivo."
            )
    else:
        print(chr(10) + "validacao insuficiente: " + validacao["motivo"])

    print(chr(10) + "forcas mais altas:")
    for equipe in ranking(jogo=args.jogo)[:8]:
        print(
            f"  {equipe.nome[:28]:<30} {equipe.forca:+.3f}  "
            f"{equipe.vitorias}/{equipe.partidas} ({equipe.winrate:.0f}%)"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = get_settings()
    configurar_logging(settings.log_level, settings.log_format)

    if args.comando == "init-db":
        return _cmd_init_db()
    if args.comando == "collect":
        return _cmd_collect(args)
    if args.comando == "stats":
        return _cmd_stats()
    if args.comando == "seed-jogos":
        return _cmd_seed_jogos()
    if args.comando == "train-sentimento":
        return _cmd_train_sentimento(args)
    if args.comando == "train-confronto":
        return _cmd_train_confronto(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
