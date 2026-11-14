"""Crea un diccionario {lenguaje natural -> código Wolfram} a partir de
"An Elementary Introduction to the Wolfram Language" (3.ª ed.).

Cada registro corresponde a un ejemplo de código del libro:
    intent_text : frase que describe el ejemplo (CodeCaption), para el embedding
    context     : párrafo explicativo (bodytext) que precede al ejemplo
    metadata    : código Wolfram real, capítulo y URLs de origen

Uso:
    python creacion_diccionario.py                 # todo el libro (48 capítulos)
    python creacion_diccionario.py --url URL       # solo un capítulo concreto
    python creacion_diccionario.py -o salida.json  # cambiar el fichero de salida
"""

import argparse
import json
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.wolfram.com/language/elementary-introduction/3rd-ed/"
URL_TEST = urljoin(BASE_URL, "02-introducing-functions.html")
HEADERS = {"User-Agent": "Mozilla/5.0"}  # Simulamos un navegador para evitar bloqueos básicos
TIMEOUT = 30
REINTENTOS = 4  # Intentos por descarga ante fallos puntuales de red
MAX_CONTEXTO = 1000  # Longitud máxima del contexto (en caracteres) para el embedding


def descargar(sesion, url, intentos=REINTENTOS):
    """Devuelve el texto de la URL o None si falla tras varios intentos."""
    for intento in range(1, intentos + 1):
        try:
            respuesta = sesion.get(url, headers=HEADERS, timeout=TIMEOUT)
            respuesta.raise_for_status()
            respuesta.encoding = "utf-8"
            return respuesta.text
        except requests.RequestException as error:
            if intento == intentos:
                print(f"Error de conexión en {url} (tras {intentos} intentos): {error}")
                return None
            espera = 2 ** intento  # 2 s, 4 s, ...
            print(f"  Fallo al descargar {url} ({error}); reintento en {espera} s")
            time.sleep(espera)


def texto_limpio(elemento):
    """Texto del elemento sin espacios artificiales alrededor del código en línea."""
    # get_text(" ") metería espacios entre etiquetas ("Plus [2, 2] ."); unimos sin
    # separador y solo normalizamos los espacios reales del HTML.
    return re.sub(r"\s+", " ", elemento.get_text("")).strip()


INICIO_CAJA, ABRE, CIERRA = "\\!\\(", "\\(", "\\)"
MAX_CAJA = 300  # Las cajas más cortas (p. ej. un círculo) se dejan tal cual


def tipo_caja(caja):
    """Nombre del marcador según el contenido de la caja incrustada."""
    if "RasterBox" in caja:
        return "imagen"
    if "NetworkGraphics" in caja:
        return "grafo"
    return "grafico"


def reemplazar_cajas(codigo):
    """Sustituye las imágenes/gráficos incrustados (\\!\\(\\*GraphicsBox[...]\\)) por un
    símbolo legible. Algunas pueden pesar varios MB de CompressedData.

    Devuelve (código limpio, lista de marcadores usados)."""
    partes, marcadores, i = [], [], 0
    while (inicio := codigo.find(INICIO_CAJA, i)) >= 0:
        # Buscamos el \) que cierra, teniendo en cuenta los \( \) anidados
        k, nivel = inicio + len(INICIO_CAJA), 1
        while nivel and k < len(codigo):
            if codigo.startswith(ABRE, k):
                nivel, k = nivel + 1, k + 2
            elif codigo.startswith(CIERRA, k):
                nivel, k = nivel - 1, k + 2
            else:
                k += 1
        caja = codigo[inicio:k]
        partes.append(codigo[i:inicio])
        if len(caja) > MAX_CAJA:
            marcador = tipo_caja(caja)
            marcadores.append(marcador)
            partes.append(marcador)
        else:
            partes.append(caja)
        i = k
    partes.append(codigo[i:])
    return "".join(partes), marcadores


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
    # El título separa número y nombre en celdas distintas, aquí sí queremos el espacio
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
            contexto = texto_limpio(bloque)
        elif "CodeCaption" in clases:
            leyenda = texto_limpio(bloque).rstrip(":").strip()
        elif "copyexpr" in clases:
            # El código está como imagen; el texto real está en el fichero data-c2c-file
            tabla = bloque.select_one("[data-c2c-file]")
            if tabla is None:
                continue
            url_codigo = urljoin(url, tabla["data-c2c-file"])
            codigo = descargar(sesion, url_codigo)
            if not codigo:
                continue
            codigo, marcadores = reemplazar_cajas(codigo.strip())
            intent = leyenda or recortar(contexto)
            contexto_corto = recortar(contexto)
            registros.append({
                "intent_text": intent,
                "context": contexto_corto,
                # Texto recomendado para el embedding: la leyenda sola a veces es pobre
                # ("The maximum of these numbers is 7"), el contexto aporta el significado.
                "embedding_text": intent if intent == contexto_corto else f"{intent}. {contexto_corto}",
                "metadata": {
                    "example_code": codigo,
                    # Objetos incrustados sustituidos por un marcador (el original está en code_url)
                    "embedded_objects": marcadores,
                    "chapter": capitulo,
                    "source_url": url,
                    "code_url": url_codigo,
                },
            })
            leyenda = ""  # Cada leyenda describe solo al ejemplo siguiente
    return registros


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", help="Procesa solo este capítulo (por defecto, todo el libro)")
    parser.add_argument("-o", "--salida", default="diccionario_wolfram.json", help="Fichero JSON de salida")
    parser.add_argument("--pausa", type=float, default=0.5, help="Segundos entre capítulos (cortesía con el servidor)")
    args = parser.parse_args()

    with requests.Session() as sesion:
        urls = [args.url] if args.url else obtener_capitulos(sesion)
        if not urls:
            print("No se pudo obtener el índice de capítulos.")
            return
        datos, fallidos = [], []
        for i, url in enumerate(urls, 1):
            registros = extraer_capitulo(sesion, url)
            print(f"[{i}/{len(urls)}] {len(registros):3d} ejemplos - {url}")
            if not registros:
                fallidos.append(url)
            datos.extend(registros)
            if i < len(urls):
                time.sleep(args.pausa)

    # Marcamos los códigos que ya aparecieron antes (p. ej. RandomInteger[100] dos veces)
    vistos = {}
    for indice, registro in enumerate(datos):
        codigo = registro["metadata"]["example_code"]
        registro["metadata"]["duplicate_of"] = vistos.get(codigo)  # índice del primero o None
        vistos.setdefault(codigo, indice)

    with open(args.salida, "w", encoding="utf-8") as fichero:
        json.dump(datos, fichero, ensure_ascii=False, indent=2)
    print(f"Guardados {len(datos)} registros en {args.salida}")
    if fallidos:
        print(f"AVISO: {len(fallidos)} capítulo(s) sin ejemplos, revísalos o vuelve a ejecutar:")
        for url in fallidos:
            print(f"  - {url}")


if __name__ == "__main__":
    main()
