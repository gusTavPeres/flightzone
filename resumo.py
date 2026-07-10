"""
Resumo do monitor: menor preço por data + a combinação ida/volta mais barata.

Ex.:  ./.venv/bin/python resumo.py --origin GYN --dest JPA
"""
import argparse
import os
import sqlite3


def fmt(v):
    return f"R$ {v:.0f}" if v is not None else "—"


def main():
    ap = argparse.ArgumentParser(description="Resumo de preços do monitor")
    ap.add_argument("--origin", required=True, help="IATA de origem (ex: GYN)")
    ap.add_argument("--dest", required=True, help="IATA de destino (ex: JPA)")
    ap.add_argument("--db", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                 "data", "flights.db"))
    args = ap.parse_args()
    o, d = args.origin.upper(), args.dest.upper()
    c = sqlite3.connect(args.db)

    def legs(frm, to):
        return c.execute(
            """SELECT departure_date, MIN(cheapest_price), COUNT(*), MAX(checked_at)
               FROM price_history WHERE origin=? AND destination=?
               GROUP BY departure_date ORDER BY departure_date""",
            (frm, to),
        ).fetchall()

    ida, volta = legs(o, d), legs(d, o)

    print(f"\n  IDA  {o} -> {d}   (menor preço já registrado por data)")
    for dt, mn, n, last in ida:
        print(f"    {dt}   {fmt(mn):>10}   ({n} checagens)")
    if not ida:
        print("    (sem dados ainda)")

    print(f"\n  VOLTA  {d} -> {o}")
    for dt, mn, n, last in volta:
        print(f"    {dt}   {fmt(mn):>10}   ({n} checagens)")
    if not volta:
        print("    (sem dados ainda)")

    if ida and volta:
        bi = min(ida, key=lambda r: r[1])
        bv = min(volta, key=lambda r: r[1])
        print("\n  ╔══════════════ COMBINAÇÃO MAIS BARATA ATÉ AGORA ══════════════╗")
        print(f"    IDA    {bi[0]}   {fmt(bi[1])}")
        print(f"    VOLTA  {bv[0]}   {fmt(bv[1])}")
        print(f"    TOTAL  {fmt(bi[1] + bv[1])}")
        print("  ╚══════════════════════════════════════════════════════════════╝\n")


if __name__ == "__main__":
    main()
