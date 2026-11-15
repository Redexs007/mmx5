#!/usr/bin/env python3
"""Amplia texturas capturadas pelo mod "HD Texturas" (formato DuckStation).

  <pacote>/dumps/**/*.png   ->   <pacote>/replacements/**/*.png   (MESMO nome de arquivo!)

Regras do runtime que este script respeita:
  * o nome do arquivo identifica a textura original (hash): nunca renomeie;
  * qualquer tamanho serve (2x, 3x, 4x...);
  * alpha: 0 = transparente, 143 = semitransparente (texel STP), 255 = opaco. Os valores de alpha
    sao ampliados e depois "encaixados" nos valores que ja existiam na imagem original.

Metodos:  esrgan (IA, Real-ESRGAN via Vulkan)  |  scale2x (pixel art, bordas limpas)  |  lanczos (suave)
"""
from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

ESRGAN_URL = ("https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
              "realesrgan-ncnn-vulkan-20220424-ubuntu.zip")
TOOLS = Path(__file__).resolve().parent
ESRGAN_DIR = TOOLS / "realesrgan"
GAME_ID = "SLUS-01334"


def log(msg: str) -> None:
    print(msg, flush=True)


# ------------------------------------------------------------------ pre/pos processamento
def bleed_rgb(rgba: np.ndarray, iterations: int = 24) -> np.ndarray:
    """Preenche a cor dos pixels transparentes com a dos vizinhos (evita halos escuros)."""
    rgb = rgba[..., :3].astype(np.float32).copy()
    known = rgba[..., 3] > 0
    if known.all() or not known.any():
        return rgb
    for _ in range(iterations):
        if known.all():
            break
        k = known.astype(np.float32)
        pr = np.pad(rgb * k[..., None], ((1, 1), (1, 1), (0, 0)))
        pk = np.pad(k, 1)
        h, w = known.shape
        s = np.zeros_like(rgb)
        c = np.zeros((h, w), np.float32)
        for dy in (0, 1, 2):
            for dx in (0, 1, 2):
                if dy == 1 and dx == 1:
                    continue
                s += pr[dy:dy + h, dx:dx + w]
                c += pk[dy:dy + h, dx:dx + w]
        new = (~known) & (c > 0)
        rgb[new] = s[new] / c[new][:, None]
        known |= new
    return rgb


def snap_alpha(alpha: np.ndarray, size: tuple[int, int], classes: np.ndarray) -> np.ndarray:
    big = np.asarray(Image.fromarray(alpha).resize(size, Image.BICUBIC)).astype(np.int16)
    idx = np.abs(big[..., None] - classes[None, None, :].astype(np.int16)).argmin(-1)
    return classes[idx].astype(np.uint8)


# ------------------------------------------------------------------ metodos
def m_lanczos(rgba: np.ndarray, scale: int) -> np.ndarray:
    h, w = rgba.shape[:2]
    size = (w * scale, h * scale)
    rgb = np.clip(bleed_rgb(rgba), 0, 255).astype(np.uint8)
    up = np.asarray(Image.fromarray(rgb).resize(size, Image.LANCZOS))
    a = snap_alpha(rgba[..., 3], size, np.unique(rgba[..., 3]))
    return np.dstack([up, a])


def _eq(a, b):
    return (a == b).all(-1)


def _neigh(img):
    p = np.pad(img, ((1, 1), (1, 1), (0, 0)), mode="edge")
    h, w = img.shape[:2]
    g = lambda dy, dx: p[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
    return {k: g(*v) for k, v in dict(A=(-1, -1), B=(-1, 0), C=(-1, 1), D=(0, -1), E=(0, 0), F=(0, 1),
                                      G=(1, -1), H=(1, 0), I=(1, 1)).items()}


def scale2x(img: np.ndarray) -> np.ndarray:
    n = _neigh(img)
    B, D, E, F, H = n["B"], n["D"], n["E"], n["F"], n["H"]
    cond = (~_eq(B, H)) & (~_eq(D, F))
    e0 = np.where((cond & _eq(D, B))[..., None], D, E)
    e1 = np.where((cond & _eq(B, F))[..., None], F, E)
    e2 = np.where((cond & _eq(D, H))[..., None], D, E)
    e3 = np.where((cond & _eq(H, F))[..., None], F, E)
    h, w = img.shape[:2]
    out = np.empty((h * 2, w * 2, img.shape[2]), img.dtype)
    out[0::2, 0::2], out[0::2, 1::2], out[1::2, 0::2], out[1::2, 1::2] = e0, e1, e2, e3
    return out


def scale3x(img: np.ndarray) -> np.ndarray:
    n = _neigh(img)
    A, B, C, D, E, F, G, H, I = (n[k] for k in "ABCDEFGHI")
    eq, ne = _eq, lambda x, y: ~_eq(x, y)
    sel = lambda c, v: np.where(c[..., None], v, E)
    e0 = sel(eq(D, B) & ne(B, F) & ne(D, H), D)
    e1 = sel((eq(D, B) & ne(B, F) & ne(D, H) & ne(E, C)) | (eq(B, F) & ne(B, D) & ne(F, H) & ne(E, A)), B)
    e2 = sel(eq(B, F) & ne(B, D) & ne(F, H), F)
    e3 = sel((eq(D, B) & ne(B, F) & ne(D, H) & ne(E, G)) | (eq(D, H) & ne(D, B) & ne(H, F) & ne(E, A)), D)
    e5 = sel((eq(B, F) & ne(B, D) & ne(F, H) & ne(E, I)) | (eq(H, F) & ne(D, H) & ne(B, F) & ne(E, C)), F)
    e6 = sel(eq(D, H) & ne(D, B) & ne(H, F), D)
    e7 = sel((eq(D, H) & ne(D, B) & ne(H, F) & ne(E, I)) | (eq(H, F) & ne(D, H) & ne(B, F) & ne(E, G)), H)
    e8 = sel(eq(H, F) & ne(D, H) & ne(B, F), F)
    h, w = img.shape[:2]
    out = np.empty((h * 3, w * 3, img.shape[2]), img.dtype)
    for (dy, dx), v in {(0, 0): e0, (0, 1): e1, (0, 2): e2, (1, 0): e3, (1, 1): E, (1, 2): e5,
                        (2, 0): e6, (2, 1): e7, (2, 2): e8}.items():
        out[dy::3, dx::3] = v
    return out


def m_scale2x(rgba: np.ndarray, scale: int) -> np.ndarray:
    if scale == 2:
        return scale2x(rgba)
    if scale == 3:
        return scale3x(rgba)
    return scale2x(scale2x(rgba))          # 4x


# ------------------------------------------------------------------ Real-ESRGAN
def find_esrgan() -> Path | None:
    env = os.environ.get("MMX5_ESRGAN_BIN")
    if env and Path(env).exists():
        return Path(env)
    p = ESRGAN_DIR / "realesrgan-ncnn-vulkan"
    return p if p.exists() else None


def ensure_esrgan() -> Path | None:
    p = find_esrgan()
    if p:
        return p
    log("Baixando o Real-ESRGAN (47 MB, so' na primeira vez)...")
    try:
        ESRGAN_DIR.mkdir(parents=True, exist_ok=True)
        zpath = ESRGAN_DIR / "esrgan.zip"
        urllib.request.urlretrieve(ESRGAN_URL, zpath)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(ESRGAN_DIR)
        zpath.unlink()
        b = ESRGAN_DIR / "realesrgan-ncnn-vulkan"
        b.chmod(b.stat().st_mode | stat.S_IEXEC)
        return b
    except Exception as e:                         # noqa: BLE001
        log(f"Nao consegui baixar o Real-ESRGAN: {e}")
        return None


def run_esrgan(binary: Path, items: list[tuple[Path, np.ndarray]], scale: int, model: str) -> list[np.ndarray] | None:
    with tempfile.TemporaryDirectory(prefix="mmx5up_") as td:
        tin, tout = Path(td, "in"), Path(td, "out")
        tin.mkdir()
        tout.mkdir()
        for i, (_p, rgba) in enumerate(items):
            rgb = np.clip(bleed_rgb(rgba), 0, 255).astype(np.uint8)
            Image.fromarray(rgb).save(tin / f"{i:06d}.png")
        cmd = [str(binary), "-i", str(tin), "-o", str(tout), "-n", model, "-s", str(scale), "-f", "png",
               "-m", str(binary.parent / "models")]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            log("Real-ESRGAN falhou: " + (r.stderr or r.stdout).strip()[-400:])
            return None
        outs = []
        for i, (_p, rgba) in enumerate(items):
            f = tout / f"{i:06d}.png"
            if not f.exists():
                return None
            up = np.asarray(Image.open(f).convert("RGB"))
            a = snap_alpha(rgba[..., 3], (up.shape[1], up.shape[0]), np.unique(rgba[..., 3]))
            outs.append(np.dstack([up, a]))
        return outs


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pack", type=Path, help="pasta do pacote (com dumps/ e replacements/)")
    ap.add_argument("--scale", type=int, default=4, choices=(2, 3, 4))
    ap.add_argument("--mode", default="auto", choices=("auto", "esrgan", "scale2x", "lanczos"))
    ap.add_argument("--model", default="realesr-animevideov3",
                    help="realesr-animevideov3 | realesrgan-x4plus-anime | realesrgan-x4plus")
    ap.add_argument("--force", action="store_true", help="refazer mesmo se a substituta ja existir")
    ap.add_argument("--limit", type=int, default=0, help="processar no maximo N texturas (teste)")
    ap.add_argument("--batch", type=int, default=150)
    a = ap.parse_args()

    pack = a.pack or (TOOLS.parent / "mods" / "hd-texturas")
    src, dst = pack / "dumps", pack / "replacements"
    if not src.is_dir():
        log(f"Pasta de capturas nao encontrada: {src}\nJogue com 'Capturar texturas originais' ligado e feche o jogo.")
        return 2
    files = sorted(p for p in src.rglob("*") if p.suffix.lower() in (".png",))
    todo = []
    for f in files:
        out = dst / f.relative_to(src).with_suffix(".png")
        if a.force or not out.exists():
            todo.append((f, out))
    if a.limit:
        todo = todo[:a.limit]
    log(f"{len(files)} texturas capturadas; {len(todo)} para ampliar ({a.scale}x).")
    if not todo:
        log("Nada novo para ampliar.")
        return 0

    mode, binary = a.mode, None
    if mode in ("auto", "esrgan"):
        binary = ensure_esrgan()
        if binary is None:
            if mode == "esrgan":
                return 3
            mode = "scale2x"
            log("Usando 'scale2x' no lugar da IA.")
        else:
            mode = "esrgan"
    log(f"Metodo: {mode}")

    done = 0
    for i in range(0, len(todo), a.batch):
        chunk = todo[i:i + a.batch]
        imgs = [(f, np.asarray(Image.open(f).convert("RGBA"))) for f, _ in chunk]
        outs = None
        if mode == "esrgan":
            outs = run_esrgan(binary, imgs, a.scale, a.model)
            if outs is None:
                log("Trocando para 'scale2x' neste lote.")
        if outs is None:
            fn = m_lanczos if mode == "lanczos" else m_scale2x
            outs = [fn(arr, a.scale) for _f, arr in imgs]
        for (_f, out), arr in zip(chunk, outs):
            out.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(arr, "RGBA").save(out)
            done += 1
        log(f"[{done}/{len(todo)}] ok")
    log(f"Pronto: {done} texturas em {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
