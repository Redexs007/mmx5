"""Deteccao de placas de video e variaveis de ambiente para escolher qual renderiza o jogo.

Sem dependencias externas: le /sys/class/drm; usa lspci/glxinfo/vulkaninfo so' se existirem.
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
from pathlib import Path

VENDORS = {0x10DE: "NVIDIA", 0x1002: "AMD", 0x8086: "Intel", 0x1AF4: "Virtio", 0x15AD: "VMware"}

# todas as variaveis que o launcher pode criar para escolher a GPU (para limpar ao trocar)
GPU_ENV_KEYS = ["DRI_PRIME", "MESA_VK_DEVICE_SELECT", "__NV_PRIME_RENDER_OFFLOAD", "__GLX_VENDOR_LIBRARY_NAME",
                "__VK_LAYER_NV_optimus", "LIBGL_ALWAYS_SOFTWARE", "GALLIUM_DRIVER", "MMX5_GPU"]


def _read(p: Path) -> str:
    try:
        return p.read_text().strip()
    except OSError:
        return ""


def _lspci_name(addr: str) -> str:
    if not shutil.which("lspci"):
        return ""
    try:
        out = subprocess.run(["lspci", "-s", addr, "-mm"], capture_output=True, text=True, timeout=4).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    parts = re.findall(r'"([^"]*)"', out)          # slot "classe" "fabricante" "dispositivo" ...
    if len(parts) >= 3:
        vendor = (parts[1].replace("Corporation", "").replace("[AMD/ATI]", "AMD")
                  .replace("Advanced Micro Devices, Inc.", "AMD").strip())
        return f"{vendor} {parts[2]}".strip()
    return ""


def list_gpus() -> list[dict]:
    """Uma entrada por GPU: id (endereco PCI), name, vendor_id, device_id, driver, primary, kind."""
    gpus = []
    for card in sorted(glob.glob("/sys/class/drm/card[0-9]*")):
        if "-" in os.path.basename(card):          # card0-DP-1 etc. (conectores)
            continue
        dev = Path(card) / "device"
        try:
            addr = dev.resolve().name               # 0000:01:00.0
        except OSError:
            continue
        v, d = _read(dev / "vendor"), _read(dev / "device")
        if not v or not d:
            continue
        vid, did = int(v, 16), int(d, 16)
        drv = ""
        try:
            drv = (dev / "driver").resolve().name
        except OSError:
            pass
        name = _lspci_name(addr) or f"{VENDORS.get(vid, f'Fornecedor {vid:04x}')} [{vid:04x}:{did:04x}]"
        gpus.append(dict(id=addr, name=name, vendor_id=vid, device_id=did, driver=drv,
                         primary=_read(dev / "boot_vga") == "1", kind=""))
    if len(gpus) == 1:
        gpus[0]["kind"] = "única"
    else:                                           # com 2+ placas: a que nao e' boot_vga e' a dedicada
        for g in gpus:
            g["kind"] = "integrada" if g["primary"] else "dedicada"
    return gpus


def gpu_env(choice: str, gpus: list[dict] | None = None) -> dict[str, str]:
    """Variaveis de ambiente para a escolha: 'auto' | 'cpu' | <endereco PCI da GPU>."""
    if choice in ("", "auto"):
        return {}
    if choice == "cpu":
        return {"LIBGL_ALWAYS_SOFTWARE": "1", "GALLIUM_DRIVER": "llvmpipe", "MMX5_GPU": "cpu"}
    g = next((x for x in (gpus if gpus is not None else list_gpus()) if x["id"] == choice), None)
    if not g:
        return {}
    env = {"MMX5_GPU": choice}
    if g["driver"] == "nvidia":                   # driver proprietario: PRIME render offload
        env.update({"__NV_PRIME_RENDER_OFFLOAD": "1", "__GLX_VENDOR_LIBRARY_NAME": "nvidia",
                    "__VK_LAYER_NV_optimus": "NVIDIA_only"})
    else:                                         # Mesa (AMD / Intel / nouveau)
        env["DRI_PRIME"] = "pci-" + choice.replace(":", "_").replace(".", "_")
        env["MESA_VK_DEVICE_SELECT"] = f"{g['vendor_id']:04x}:{g['device_id']:04x}"
    return env


def vulkan_available() -> tuple[bool, str]:
    """(ok, detalhe): ha' loader do Vulkan e pelo menos um driver (ICD) instalado?"""
    loader = any(glob.glob(p) for p in ("/usr/lib*/libvulkan.so.1", "/usr/lib/*/libvulkan.so.1",
                                        "/lib/*/libvulkan.so.1", "/usr/lib64/libvulkan.so.1"))
    icds = glob.glob("/usr/share/vulkan/icd.d/*.json") + glob.glob("/etc/vulkan/icd.d/*.json") + \
        glob.glob(os.path.expanduser("~/.local/share/vulkan/icd.d/*.json"))
    if not loader:
        return False, "libvulkan.so.1 não encontrada (instale vulkan-loader / libvulkan1)"
    if not icds:
        return False, "nenhum driver Vulkan (ICD) instalado"
    return True, f"{len(icds)} driver(s) Vulkan"


def test_command(kind: str) -> list[str] | None:
    """Comando de diagnostico: 'gl' -> glxinfo/eglinfo; 'vk' -> vulkaninfo."""
    if kind == "gl":
        if shutil.which("glxinfo"):
            return ["glxinfo", "-B"]
        if shutil.which("eglinfo"):
            return ["eglinfo", "-B"]
        return None
    if shutil.which("vulkaninfo"):
        return ["vulkaninfo", "--summary"]
    return None


INSTALL_HINT = {
    "gl": "Instale 'mesa-utils' (Debian/Ubuntu) ou 'mesa-demos' (Fedora/Arch) para testar o OpenGL.",
    "vk": "Instale 'vulkan-tools' para testar o Vulkan.",
}
