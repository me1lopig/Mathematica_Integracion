"""Valida la calidad de diccionario_wolfram.json.

Uso:
    python validar_diccionario.py                       # comprobaciones locales
    python validar_diccionario.py --online 20           # + comprueba 20 code_url al azar contra la web
    python validar_diccionario.py -f otro.json

Código de salida: 0 si no hay ERRORES (los AVISOS no lo cambian), 1 si hay errores.
"""

import argparse
import collections
import json
import random
import re
import sys

CAMPOS = {"intent_text", "context", "embedding_text", "metadata"}
CAMPOS_META = {"example_code", "embedded_objects", "chapter", "source_url", "code_url", "duplicate_of"}
CAPITULOS_ESPERADOS = 48
MAX_CODIGO = 2000
PARES = {"[": "]", "{": "}", "(": ")"}
CIERRES = set(PARES.values())
RE_CADENA = re.compile(r'"(?:[^"\\]|\\.)*"')
RE_COMENTARIO = re.compile(r"\(\*.*?\*\)", re.S)
RE_PUA = re.compile(r"[-]")


def equilibrado(codigo):
    """True si [] {} () están balanceados (ignorando cadenas y comentarios)."""
    codigo = RE_COMENTARIO.sub("", RE_CADENA.sub('""', codigo))
    codigo = codigo.replace("\\[", "").replace("\\]", "")  # \[Alpha], \[Degree]...
    pila = []
    for c in codigo:
        if c in PARES:
            pila.append(PARES[c])
        elif c in CIERRES:
            if not pila or pila.pop() != c:
                return False
    return not pila


def validar(datos):
    errores, avisos = [], []
    err = lambda i, m: errores.append(f"#{i}: {m}")
    avi = lambda i, m: avisos.append(f"#{i}: {m}")

    if not isinstance(datos, list) or not datos:
        return ["El JSON debe ser una lista no vacía"], []

    for i, r in enumerate(datos):
        if not isinstance(r, dict) or set(r) != CAMPOS:
            err(i, f"campos incorrectos: {sorted(r) if isinstance(r, dict) else type(r)}")
            continue
        m = r["metadata"]
        if not isinstance(m, dict) or set(m) != CAMPOS_META:
            err(i, "metadata con campos incorrectos")
            continue
        for campo in ("intent_text", "context", "embedding_text"):
            if not isinstance(r[campo], str) or not r[campo].strip():
                err(i, f"{campo} vacío")
        for campo in ("example_code", "chapter", "source_url", "code_url"):
            if not isinstance(m[campo], str) or not m[campo].strip():
                err(i, f"metadata.{campo} vacío")
        if errores and errores[-1].startswith(f"#{i}:"):
            continue

        codigo = m["example_code"]
        if not m["source_url"].startswith("https://www.wolfram.com/language/elementary-introduction/"):
            err(i, f"source_url inesperada: {m['source_url']}")
        if not m["code_url"].startswith("https://") or not m["code_url"].endswith(".txt.en"):
            err(i, f"code_url inesperada: {m['code_url']}")
        if r["intent_text"] not in r["embedding_text"]:
            err(i, "embedding_text no contiene intent_text")
        if "\\!\\(" in codigo and len(codigo) > 300:
            err(i, "queda una caja incrustada sin sustituir")
        if not equilibrado(codigo):
            avi(i, f"corchetes/llaves desbalanceados: {codigo[:60]!r}")
        if len(codigo) > MAX_CODIGO:
            avi(i, f"código muy largo ({len(codigo)} caracteres)")
        if "CompressedData[" in codigo:
            avi(i, "contiene CompressedData sin sustituir")
        if RE_PUA.search(codigo + r["context"] + r["intent_text"]):
            avi(i, "caracteres privados (iconos) en el texto")
        if re.search(r" [,.;:]", r["context"]) or "  " in r["context"]:
            avi(i, "espaciado raro en el contexto (¿icono perdido?)")
        if r["intent_text"] == r["context"]:
            avi(i, "sin frase propia (intent_text = context)")

        # Coherencia de los marcadores y duplicados
        usados = [x for x in ("imagen", "grafico", "grafo") if re.search(rf"\b{x}\b", codigo)]
        if m["embedded_objects"] and not usados:
            err(i, "embedded_objects no aparece en el código")
        d = m["duplicate_of"]
        if d is not None:
            if not isinstance(d, int) or not (0 <= d < i):
                err(i, f"duplicate_of inválido: {d}")
            elif datos[d]["metadata"]["example_code"] != codigo:
                err(i, f"duplicate_of apunta a un código distinto (#{d})")

    # Duplicados no marcados
    primeros = {}
    for i, r in enumerate(datos):
        c = r["metadata"]["example_code"] if isinstance(r.get("metadata"), dict) else None
        if c is None:
            continue
        if c in primeros and r["metadata"].get("duplicate_of") != primeros[c]:
            err(i, f"código repetido sin marcar (primero en #{primeros[c]})")
        primeros.setdefault(c, i)

    # Cobertura de capítulos
    caps = {r["metadata"]["source_url"] for r in datos if isinstance(r.get("metadata"), dict)}
    if len(caps) != CAPITULOS_ESPERADOS:
        err("global", f"{len(caps)} capítulos en lugar de {CAPITULOS_ESPERADOS}")
    return errores, avisos


def comprobar_online(datos, n):
    import requests
    errores = []
    for i in random.sample(range(len(datos)), min(n, len(datos))):
        m = datos[i]["metadata"]
        try:
            r = requests.get(m["code_url"], headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            r.raise_for_status()
        except requests.RequestException as e:
            errores.append(f"#{i}: code_url no accesible ({e})")
            continue
        original = r.content.decode("utf-8", "replace").strip()
        if "\\!\\(" not in original and original != m["example_code"]:
            errores.append(f"#{i}: el código no coincide con la web: {m['example_code'][:50]!r}")
    return errores


def resumen(datos):
    print("\n── Estadísticas ──")
    print(f"Registros: {len(datos)} · capítulos: {len({r['metadata']['source_url'] for r in datos})}")
    L = sorted(len(r["metadata"]["example_code"]) for r in datos)
    print(f"Longitud del código: mín {L[0]} · mediana {L[len(L)//2]} · máx {L[-1]}")
    print(f"Con objetos sustituidos: {sum(bool(r['metadata']['embedded_objects']) for r in datos)}")
    print(f"Duplicados marcados: {sum(r['metadata']['duplicate_of'] is not None for r in datos)}")
    c = collections.Counter(r["metadata"]["chapter"] for r in datos)
    print("Capítulos con menos ejemplos:", ", ".join(f"{k} ({v})" for k, v in sorted(c.items(), key=lambda x: x[1])[:3]))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-f", "--fichero", default="diccionario_wolfram.json")
    p.add_argument("--online", type=int, metavar="N", help="Comprueba N code_url al azar contra la web")
    a = p.parse_args()

    with open(a.fichero, encoding="utf-8") as f:
        datos = json.load(f)
    errores, avisos = validar(datos)
    if a.online:
        errores += comprobar_online(datos, a.online)

    if isinstance(datos, list) and datos and all(isinstance(r, dict) and isinstance(r.get("metadata"), dict) and CAMPOS_META <= set(r["metadata"]) for r in datos):
        resumen(datos)
    print(f"\n❌ {len(errores)} error(es)" if errores else "\n✅ Sin errores")
    for e in errores[:30]:
        print("  ERROR ", e)

    # Avisos agrupados por tipo: "#12: mensaje" -> mensaje (sin el detalle variable tras ':')
    grupos = collections.defaultdict(list)
    for v in avisos:
        indice, mensaje = v.split(": ", 1)
        grupos[mensaje.split(":")[0].split("(")[0].strip()].append(indice)
    print(f"\n⚠️  {len(avisos)} aviso(s) en {len(grupos)} tipo(s)")
    for tipo, indices in sorted(grupos.items(), key=lambda x: -len(x[1])):
        print(f"  {len(indices):4d} × {tipo}   (p. ej. {', '.join(indices[:4])})")
    sys.exit(1 if errores else 0)


if __name__ == "__main__":
    main()
