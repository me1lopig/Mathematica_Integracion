import logging
import os
from pathlib import Path
from typing import Optional

from wolframclient.evaluation import WolframLanguageSession
from wolframclient.exception import (
    SocketException,
    WolframKernelException,
    WolframLanguageException,
)
from wolframclient.language import wl, wlexpr
from wolframclient.language.expression import WLSymbol

# Configuración del logger de aplicación en Python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("WolframArch")

# Ruta configurable por variable de entorno con fallback explícito en Linux
DEFAULT_KERNEL_PATH = os.getenv("WOLFRAM_KERNEL_PATH", "/usr/bin/WolframKernel")


def construir_expresion_superficie(image_size: int = 600):
    """
    Construye la expresión simbólica del gráfico 3D en Wolfram Language.
    Se emplea SunsetColors para compatibilidad universal entre versiones del motor.
    """
    codigo_plot = f"""
    Plot3D[
        Sin[x] Cos[y], {{x, -Pi, Pi}}, {{y, -Pi, Pi}},
        ColorFunction -> "SunsetColors",
        Mesh -> None,
        AxesLabel -> {{"x", "y", "z"}},
        PlotTheme -> "Scientific",
        ImageSize -> {image_size}
    ]
    """
    return wlexpr(codigo_plot)


def exportar_grafico_escritorio(
    ruta_salida: Path,
    formato: str = "JPEG",
    kernel_path: Optional[str] = DEFAULT_KERNEL_PATH,
    timeout_seg: float = 15.0,
    startup_timeout: int = 20,
) -> Path:
    """
    Evalúa y exporta un gráfico 3D directamente desde WolframKernel a disco.
    """
    ruta_absoluta = ruta_salida.resolve()
    ruta_absoluta.parent.mkdir(parents=True, exist_ok=True)

    # Construcción híbrida: wlexpr para opciones gráficas + wl.* para I/O y TimeConstrained
    plot_expr = construir_expresion_superficie(image_size=600)
    export_expr = wl.Export(str(ruta_absoluta), plot_expr, formato.upper())
    expr_protegida = wl.TimeConstrained(export_expr, timeout_seg, wl.Symbol("$Aborted"))

    logger.info(f"Iniciando WolframKernel desde: {kernel_path}")

    try:
        # IMPORTANTE: kernel_loglevel requiere constantes numéricas de `logging` (ej. logging.WARNING)
        with WolframLanguageSession(
            kernel=kernel_path,
            startup_timeout=startup_timeout,
            kernel_loglevel=logging.WARNING,
        ) as session:
            logger.info(
                f"Evaluando superficie y exportando a {formato.upper()} (timeout={timeout_seg}s)..."
            )

            # evaluate_wrap captura mensajes de advertencia internos del kernel
            evaluacion = session.evaluate_wrap(expr_protegida)

            if evaluacion.messages:
                for msg in evaluacion.messages:
                    logger.warning(f"[Mensaje interno de WolframKernel]: {msg}")

            resultado = evaluacion.get()

            if resultado == WLSymbol("$Aborted") or str(resultado) == "$Aborted":
                raise TimeoutError(
                    f"El renderizado en Wolfram superó el límite de {timeout_seg} segundos."
                )

            if not isinstance(resultado, str) or not Path(resultado).is_file():
                raise RuntimeError(
                    f"Wolfram no devolvió una ruta de archivo válida. Respuesta: {resultado}"
                )

            logger.info(f"Éxito: Imagen generada y validada en: {resultado}")
            return Path(resultado)

    except WolframKernelException as e:
        logger.error(f"Error crítico de inicialización o licencia del Kernel: {e}")
        raise
    except SocketException as e:
        logger.error(f"Fallo de comunicación en el socket ZeroMQ: {e}")
        raise
    except WolframLanguageException as e:
        logger.error(f"Excepción general en Wolfram Language: {e}")
        raise


if __name__ == "__main__":
    destino_jpg = Path.cwd() / "funcion_matematica_python.jpg"
    exportar_grafico_escritorio(
        ruta_salida=destino_jpg,
        formato="JPEG",
        kernel_path=DEFAULT_KERNEL_PATH,
    )