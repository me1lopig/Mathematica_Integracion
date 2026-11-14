"""Crea un diccionario {lenguaje natural -> código Wolfram} a partir de
"An Elementary Introduction to the Wolfram Language" (3.ª ed.).

Cada registro corresponde a un ejemplo de código del libro:
    intent_text : frase que describe el ejemplo (CodeCaption), para el embedding
    context     : párrafo explicativo (bodytext) que precede al ejemplo
    metadata    : código Wolfram real, capítulo y URLs de origen

Uso:
    python creacion_diccionario.py                 # solo el capítulo de prueba
    python creacion_diccionario.py --todos         # todos los capítulos del índice
    python creacion_diccionario.py --url URL -o salida.json
"""

import argparse
import json
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.wolfram.com/language/elementary-introduction/3rd-ed/"
URL_TEST = urljoin(BASE_URL, "02-introducing-functions.html")
HEADERS = {"User-Agent": "Mozilla/5.0"}  # Simulamos un navegador para evitar bloqueos básicos
TIMEOUT = 30
MAX_CONTEXTO = 1000  # Longitud máxima del contexto (en caracteres) para el embedding


def descargar(sesion, url):
    """Devuelve el texto de la URL o None si falla."""
    try:
        respuesta = sesion.get(url, headers=HEADERS, timeout=TIMEOUT)
        respuesta.raise_for_status()
    except requests.RequestException as error:
        print(f"Error de conexión en {url}: {error}")
        return None
    respuesta.encoding = "utf-8"
    return respuesta.text


def recortar(texto, limite=MAX_CONTEXTO):
    """Recorta el texto sin partir palabras."""
    if len(texto) <= limite:
        return texto
    return texto[:limite].rsplit(" ", 1)[0] + "…"


def obtener_capitulos(sesion, url_indice=URL_TEST):
    """Lista de URLs de todos los capítulos, tomadas del índice lateral (tocChapterLink)."""
    html = descargar(sesion, url_indice)
    if html is None:
        return []
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    for enlace in soup.select("a.tocChapterLink[href]"):
        url = urljoin(url_indice, enlace["href"])
        if url not in urls:
            urls.append(url)
    return urls


def extraer_capitulo(sesion, url):
    """Extrae un registro por cada ejemplo de código del capítulo."""
    html = descargar(sesion, url)
    if html is None:
        return []
    soup = BeautifulSoup(html, "html.parser")

    titulo = soup.select_one("table.SectionTitleTable")
    capitulo = titulo.get_text(" ", strip=True) if titulo else ""

    contenido = soup.select_one(".wlsite-tb-body-copy")
    if contenido is None:
        print(f"No se encontró el contenido del capítulo en: {url}")
        return []

    registros = []
    contexto = ""   # Último párrafo explicativo visto
    leyenda = ""    # Última frase CodeCaption vista
    # Recorremos los bloques en orden del documento para emparejar texto y código
    for bloque in contenido.select("div.bodytext, div.CodeCaption, div.copyexpr"):
        clases = bloque.get("class", [])
        if "bodytext" in clases:
            contexto = bloque.get_text(" ", strip=True)
        elif "CodeCaption" in clases:
            leyenda = bloque.get_text(" ", strip=True).rstrip(":").strip()
        elif "copyexpr" in clases:
            # El código está como imagen; el texto real está en el fichero data-c2c-file
            tabla = bloque.select_one("[data-c2c-file]")
            if tabla is None:
                continue
            url_codigo = urljoin(url, tabla["data-c2c-file"])
            codigo = descargar(sesion, url_codigo)
            if not codigo:
                continue
            registros.append({
                "intent_text": leyenda or recortar(contexto),
                "context": recortar(contexto),
                "metadata": {
                    "example_code": codigo.strip(),
                    "chapter": capitulo,
                    "source_url": url,
                    "code_url": url_codigo,
                },
            })
            leyenda = ""  # Cada leyenda describe solo al ejemplo siguiente
    return registros


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=URL_TEST, help="URL de un capítulo concreto")
    parser.add_argument("--todos", action="store_true", help="Procesa todos los capítulos del índice")
    parser.add_argument("-o", "--salida", default="diccionario_wolfram.json", help="Fichero JSON de salida")
    parser.add_argument("--pausa", type=float, default=0.5, help="Segundos entre capítulos (cortesía con el servidor)")
    args = parser.parse_args()

    with requests.Session() as sesion:
        urls = obtener_capitulos(sesion) if args.todos else [args.url]
        datos = []
        for i, url in enumerate(urls, 1):
            registros = extraer_capitulo(sesion, url)
            print(f"[{i}/{len(urls)}] {len(registros):3d} ejemplos - {url}")
            datos.extend(registros)
            if i < len(urls):
                time.sleep(args.pausa)

    with open(args.salida, "w", encoding="utf-8") as fichero:
        json.dump(datos, fichero, ensure_ascii=False, indent=2)
    print(f"Guardados {len(datos)} registros en {args.salida}")


if __name__ == "__main__":
    main()
