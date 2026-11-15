#!/usr/bin/env wolframscript
(* ::Package:: *)

Print["Iniciando renderizado matemático en Wolfram Engine..."];

(* 1. Construcción de la expresión gráfica paramétrica *)
(* Se sustituye Viridis por SunsetColors para garantizar compatibilidad *)
superficie = Plot3D[
  Sin[x] Cos[y], {x, -Pi, Pi}, {y, -Pi, Pi},
  ColorFunction -> "SunsetColors",
  Mesh -> None,
  AxesLabel -> {"x", "y", "z"},
  ImageSize -> 600
];

(* 2. Definición de la ruta de salida relativa al directorio de ejecución *)
rutaSalida = FileNameJoin[{Directory[], "funcion_matematica_1.jpg"}];

(* 3. Exportación directa al sistema de archivos *)
resultado = Export[rutaSalida, superficie, "JPEG"];

(* 4. Validación del ciclo de I/O *)
If[StringQ[resultado],
  Print["Éxito: Imagen exportada en ", resultado],
  Print["Error crítico: Fallo al exportar la imagen."]
];