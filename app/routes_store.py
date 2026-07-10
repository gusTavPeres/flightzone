"""
Leitura/escrita atômica do routes.json — usado pela web para adicionar/remover
consultas. A escrita é atômica (tmp + os.replace) para o monitor nunca ler um
arquivo pela metade enquanto recarrega.
"""
import json
import os
import tempfile


def load(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save(path, routes):
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(routes, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)  # atômico
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _key(r):
    return (
        str(r.get("from") or r.get("origin") or "").upper(),
        str(r.get("to") or r.get("destination") or "").upper(),
        str(r.get("date") or ""),
        str(r.get("trip") or "oneway"),
        str(r.get("return_date") or r.get("return") or ""),
    )


def add(path, route):
    """Adiciona uma rota se ainda não existir. Retorna (ok, msg)."""
    routes = load(path)
    if any(_key(r) == _key(route) for r in routes):
        return False, "Essa consulta já existe."
    routes.append(route)
    save(path, routes)
    return True, "Consulta adicionada."


def remove_index(path, i):
    """Remove a rota na posição i. Retorna (ok, msg)."""
    routes = load(path)
    if 0 <= i < len(routes):
        r = routes.pop(i)
        save(path, routes)
        o = r.get("from") or r.get("origin")
        d = r.get("to") or r.get("destination")
        return True, f"Removida {o}->{d} {r.get('date','')}."
    return False, "Índice inválido."
